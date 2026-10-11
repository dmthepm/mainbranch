"""OAuth building blocks for ``mb connect google`` (read-only Search Console and GA4).

Standard library only. This module has no CLI and stores nothing; the bootstrap
command (``mb connect google --oauth``) and read-time minting build on it.

Google's installed-app flow, as used here
(https://developers.google.com/identity/protocols/oauth2/native-app):

- PKCE with ``S256``: the verifier is 43-128 unreserved characters and the
  challenge is the unpadded base64url SHA-256 of the verifier.
- The redirect is a loopback ``http://127.0.0.1:<port>``. The receiver binds
  127.0.0.1 only and closes after the one redirect on ``/``. A request on any
  other path or with another method gets 404/405 and the wait goes on, all
  under one absolute deadline that also bounds slow (trickled) reads.
- The authorization request carries ``client_id``, ``redirect_uri``,
  ``response_type=code``, ``scope``, ``code_challenge``,
  ``code_challenge_method`` and ``state``. Refresh tokens are always returned
  for installed apps, so ``access_type`` and ``prompt`` are not sent.
- Token calls are form POSTs to ``https://oauth2.googleapis.com/token``.
  ``client_secret`` is optional there; it is sent only when the client has one.

Secret handling: the authorization code, PKCE verifier, client secret, refresh
token and access token never appear in an exception message, a log line, the
loopback response page or the share-safe ``upstream`` record. Exceptions carry
fixed text chosen by a stable ``rule``; OAuth errors are classified by the
``error`` code and ``error_subtype`` only, never by ``error_description``.
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import hmac
import http.client
import http.server
import io
import json
import re
import secrets
import socket
import socketserver
import sys
import time
import urllib.parse
from collections.abc import Callable, Iterator, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, TextIO

from mb import http_safe

SCOPE_SEARCH_CONSOLE = "https://www.googleapis.com/auth/webmasters.readonly"
SCOPE_ANALYTICS = "https://www.googleapis.com/auth/analytics.readonly"
SCOPES: tuple[str, ...] = (SCOPE_SEARCH_CONSOLE, SCOPE_ANALYTICS)
SCOPE_LABELS: dict[str, str] = {
    SCOPE_SEARCH_CONSOLE: "search_console",
    SCOPE_ANALYTICS: "ga4",
}

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
LOOPBACK_HOST = "127.0.0.1"
CALLBACK_PATH = "/"

TOKEN_TIMEOUT_SECONDS = 8.0
DEFAULT_CALLBACK_TIMEOUT_SECONDS = 300.0
RESPONSE_MAX_BYTES = 65536

PKCE_VERIFIER_MIN = 43
PKCE_VERIFIER_MAX = 128
_PKCE_VERIFIER_RE = re.compile(r"[A-Za-z0-9\-._~]+")
_OAUTH_CODE_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
# Token-endpoint answers that are transient whatever their body says.
TRANSIENT_HTTP_STATUSES = frozenset({408, 429})

# Request fields whose values are secrets; the POST helper redacts each one
# it sends from everything it hands back.
SECRET_FIELDS: tuple[str, ...] = ("refresh_token", "client_secret", "code", "code_verifier")
TOKEN_FIELDS: tuple[str, ...] = (
    "access_token",
    "expires_in",
    "scope",
    "token_type",
    "refresh_token",
    "refresh_token_expires_in",
)

# States, shared with ``mb connect`` status vocabulary.
STATE_REAUTH_REQUIRED = "reauth_required"
STATE_INVALID = "invalid"
STATE_UNVALIDATED = "unvalidated"
STATE_CONSENT_DENIED = "consent_denied"
STATE_BOOTSTRAP_TIMEOUT = "bootstrap_timeout"

REPAIRS: dict[str, str] = {
    STATE_REAUTH_REQUIRED: "mb connect google --oauth --reauth",
    STATE_INVALID: "Re-run the Google sign-in with the current OAuth client file.",
    STATE_UNVALIDATED: "Check the network and try again.",
    STATE_CONSENT_DENIED: "Re-run the Google sign-in and allow read-only access.",
    STATE_BOOTSTRAP_TIMEOUT: "Re-run the Google sign-in and finish it in the browser sooner.",
}

# Fixed, value-free messages by rule. Nothing from a request, a response or
# the redirect is ever interpolated.
_RULE_MESSAGES: dict[str, str] = {
    "pkce_verifier_format": "The PKCE verifier must be 43-128 unreserved characters.",
    "redirect_uri_not_loopback": "The redirect URI must be http://127.0.0.1:<port>.",
    "client_id_missing": "The OAuth client id is missing.",
    "state_mismatch": "The sign-in response did not match this sign-in attempt.",
    "code_missing": "The sign-in response carried no authorization code.",
    "redirect_ambiguous": "The sign-in response carried more than one code or state.",
    "redirect_host": "The pasted URL is not the 127.0.0.1 sign-in redirect.",
    "consent_denied": "Google sign-in was declined.",
    "authorization_error": "Google returned an error instead of an authorization code.",
    "bootstrap_timeout": "Timed out waiting for the Google sign-in to finish.",
    "paste_needs_tty": "Paste mode needs an interactive terminal; run it in a normal terminal.",
    "paste_empty": "No sign-in URL was pasted.",
    "token_request_failed": "Google's token endpoint refused the request.",
    # The code exchange at sign-in, by the OAuth `error` code (never its text).
    "oauth_client_rejected": (
        "Google refused the OAuth client (invalid_client): it was deleted, or the client "
        "file is out of date."
    ),
    "oauth_client_unauthorized": (
        "Google says this OAuth client may not be used for this sign-in "
        "(unauthorized_client); check that it is a Desktop app client."
    ),
    "oauth_scope_rejected": (
        "Google refused the read-only Search Console and Analytics scopes (invalid_scope)."
    ),
    "authorization_code_rejected": (
        "Google refused the authorization code (invalid_grant): it expired, was already "
        "used, came from another sign-in attempt, or did not match the sign-in request."
    ),
    "token_unreachable": "Google's token endpoint could not be reached.",
    "token_response_malformed": "Google's token endpoint returned an unreadable response.",
    "token_unexpected_redirect": (
        "Google's token endpoint answered with a redirect, which is never followed."
    ),
}


class GoogleOAuthError(RuntimeError):
    """Fixed-text failure with a stable ``rule`` and a connect ``state``."""

    def __init__(
        self,
        rule: str,
        state: str = STATE_INVALID,
        *,
        upstream: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(_RULE_MESSAGES.get(rule, "Google sign-in failed."))
        self.rule = rule
        self.state = state
        self.repair = REPAIRS.get(state, "")
        self.upstream: dict[str, Any] = dict(upstream or {})


def _redact(text: str, secret_values: tuple[str, ...]) -> str:
    # Lazy import: connect.py will import this module for read-time minting.
    from mb.connect import _redact_sensitive_text

    return _redact_sensitive_text(text, secret_values)


# --- PKCE and state ---------------------------------------------------------


def new_code_verifier() -> str:
    """A fresh PKCE verifier (86 urlsafe characters, inside 43-128)."""

    return secrets.token_urlsafe(64)


def code_challenge(verifier: str) -> str:
    """The ``S256`` challenge for ``verifier``."""

    if not (
        PKCE_VERIFIER_MIN <= len(verifier) <= PKCE_VERIFIER_MAX
    ) or not _PKCE_VERIFIER_RE.fullmatch(verifier):
        raise GoogleOAuthError("pkce_verifier_format")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def new_state() -> str:
    return secrets.token_urlsafe(32)


def states_match(expected: str, received: str) -> bool:
    return bool(expected) and hmac.compare_digest(
        expected.encode("utf-8"), received.encode("utf-8")
    )


# --- Authorization URL ------------------------------------------------------


def loopback_redirect_uri(port: int) -> str:
    return f"http://{LOOPBACK_HOST}:{int(port)}"


def _is_loopback_redirect(uri: str) -> bool:
    parsed = urllib.parse.urlsplit(uri)
    return (
        parsed.scheme == "http"
        and parsed.hostname == LOOPBACK_HOST
        and parsed.port is not None
        and parsed.path in {"", CALLBACK_PATH}
        and not parsed.query
        and not parsed.fragment
    )


def build_auth_url(
    *,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
    scopes: tuple[str, ...] = SCOPES,
    login_hint: str | None = None,
) -> str:
    """The consent URL. It carries no client secret, code or verifier."""

    if not client_id:
        raise GoogleOAuthError("client_id_missing")
    if not _is_loopback_redirect(redirect_uri):
        raise GoogleOAuthError("redirect_uri_not_loopback")
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"{AUTH_ENDPOINT}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"


# --- Redirect parsing (loopback and paste) ----------------------------------


def parse_redirect_query(query: str, expected_state: str) -> str:
    """Return the authorization code from a redirect query string.

    ``state`` is checked before anything else, so a stray or forged redirect
    is rejected as ``state_mismatch`` whatever else it carries.
    """

    fields = urllib.parse.parse_qs(query, keep_blank_values=True)
    states = fields.get("state", [])
    codes = fields.get("code", [])
    if len(states) > 1 or len(codes) > 1:
        raise GoogleOAuthError("redirect_ambiguous")
    if not states or not states_match(expected_state, states[0]):
        raise GoogleOAuthError("state_mismatch")
    errors = fields.get("error", [])
    if errors:
        if errors[0] == "access_denied":
            raise GoogleOAuthError("consent_denied", STATE_CONSENT_DENIED)
        raise GoogleOAuthError(
            "authorization_error", STATE_INVALID, upstream={"error_code": _safe_code(errors[0])}
        )
    if not codes or not codes[0]:
        raise GoogleOAuthError("code_missing")
    return codes[0]


def parse_pasted_redirect(text: str, expected_state: str) -> str:
    """Accept the whole redirect URL or just its query (``code=...&state=...``)."""

    pasted = text.strip()
    if not pasted:
        raise GoogleOAuthError("paste_empty")
    if "://" in pasted:
        parsed = urllib.parse.urlsplit(pasted)
        if parsed.scheme != "http" or parsed.hostname != LOOPBACK_HOST:
            raise GoogleOAuthError("redirect_host")
        query = parsed.query
    else:
        query = pasted.split("?", 1)[1] if pasted.startswith(("?", "/?")) else pasted
    return parse_redirect_query(query, expected_state)


def read_pasted_redirect(
    expected_state: str,
    *,
    stdin: TextIO | None = None,
    reader: Callable[[str], str] | None = None,
) -> str:
    """Read the pasted redirect without echo; refuse when stdin is not a TTY.

    ``getpass`` reads from ``/dev/tty`` with echo off, so the code never shows
    on screen or in scrollback, and a pipe or an agent cannot feed it.
    """

    stream = stdin if stdin is not None else sys.stdin
    try:
        interactive = bool(stream.isatty())
    except (AttributeError, ValueError, OSError):
        interactive = False
    if not interactive:
        raise GoogleOAuthError("paste_needs_tty")
    read = reader if reader is not None else getpass.getpass
    pasted = read("Paste the full 127.0.0.1 URL from the browser (hidden): ")
    return parse_pasted_redirect(pasted, expected_state)


# --- Loopback receiver ------------------------------------------------------

_SUCCESS_PAGE = (
    b"<!doctype html><meta charset=utf-8><title>Main Branch</title>"
    b"<p>Google sign-in finished. You can close this tab and return to the terminal.</p>"
)
_FAILURE_PAGE = (
    b"<!doctype html><meta charset=utf-8><title>Main Branch</title>"
    b"<p>Google sign-in did not finish. Return to the terminal for next steps.</p>"
)


@dataclass
class _Outcome:
    code: str | None = field(default=None, repr=False)
    error: GoogleOAuthError | None = None


class _DeadlineSocketIO(io.RawIOBase):
    """Socket reads that share one absolute deadline.

    A socket timeout applies to each ``recv`` on its own, so a client that
    trickles one header byte at a time could hold a plain handler for as long
    as it likes. Re-arming the timeout from a fixed deadline before every
    ``recv`` bounds the whole request read instead.
    """

    def __init__(self, sock: socket.socket, deadline: float) -> None:
        super().__init__()
        self._sock = sock
        self._deadline = deadline

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        left = self._deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError("loopback read deadline")
        self._sock.settimeout(left)
        return self._sock.recv_into(buffer)


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    server: _CallbackServer
    server_version = "mb"
    sys_version = ""
    # Longest one connection may take to send its request. An idle socket (a
    # browser preconnect) or a trickled request is cut off after this, or at
    # the wait's own deadline if that comes first.
    timeout = 5

    def setup(self) -> None:
        super().setup()
        budget = max(0.0, min(float(self.timeout), self.server.read_budget))
        self.rfile = io.BufferedReader(
            _DeadlineSocketIO(self.connection, time.monotonic() + budget)
        )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # The default writes the request line, which carries ?code=, to stderr.
        return

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        # The default error page quotes the request line or method back.
        self.close_connection = True
        with suppress(OSError):
            self._reply(code, _FAILURE_PAGE)

    def _reply(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        split = urllib.parse.urlsplit(self.path)
        if split.path != CALLBACK_PATH:
            # Not the redirect (a favicon, a probe): answer and keep waiting.
            self._reply(404, _FAILURE_PAGE)
            return
        try:
            code = parse_redirect_query(split.query, self.server.expected_state)
        except GoogleOAuthError as exc:
            self.server.outcome = _Outcome(error=exc)
            self._reply(400, _FAILURE_PAGE)
            return
        self.server.outcome = _Outcome(code=code)
        self._reply(200, _SUCCESS_PAGE)

    def _reject_method(self) -> None:
        self._reply(405, _FAILURE_PAGE)

    do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _reject_method  # noqa: N815


class _CallbackServer(socketserver.TCPServer):
    # TCPServer, not HTTPServer: HTTPServer.server_bind does a reverse lookup.
    allow_reuse_address = False

    def __init__(self, port: int, expected_state: str) -> None:
        self.expected_state = expected_state
        self.outcome: _Outcome | None = None
        # Seconds left on the wait when the current connection was accepted.
        self.read_budget = float(_CallbackHandler.timeout)
        super().__init__((LOOPBACK_HOST, port), _CallbackHandler)

    def handle_error(self, request: Any, client_address: Any) -> None:
        # The default prints a traceback to stderr; say nothing and keep waiting.
        return


class LoopbackReceiver:
    """Wait on ``http://127.0.0.1:<port>`` for the one redirect.

    ``port=0`` picks a free port. ``clock`` is injectable so tests can expire
    the timeout without waiting. A GET on ``/`` ends the wait: a correct
    redirect returns the code, a wrong ``state`` or an error raises. Any other
    path or method is answered 404/405 and the wait goes on. The timeout is
    absolute: a connection that trickles its request is cut off at it.
    """

    POLL_SECONDS = 0.25

    def __init__(
        self,
        expected_state: str,
        *,
        port: int = 0,
        timeout: float = DEFAULT_CALLBACK_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._server = _CallbackServer(port, expected_state)
        self._timeout = float(timeout)
        self._clock = clock
        self._closed = False

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def redirect_uri(self) -> str:
        return loopback_redirect_uri(self.port)

    def wait(self) -> str:
        deadline = self._clock() + self._timeout
        try:
            while self._server.outcome is None:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    raise GoogleOAuthError("bootstrap_timeout", STATE_BOOTSTRAP_TIMEOUT)
                self._server.timeout = min(self.POLL_SECONDS, remaining)
                self._server.read_budget = remaining
                self._server.handle_request()
            outcome = self._server.outcome
        finally:
            self.close()
        if outcome.error is not None:
            raise outcome.error
        if outcome.code is None:
            raise GoogleOAuthError("code_missing")
        return outcome.code

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._server.server_close()

    def __enter__(self) -> LoopbackReceiver:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# --- Token endpoint ---------------------------------------------------------

Sender = Callable[[str, bytes, Mapping[str, str], float], tuple[int, bytes]]


def _urllib_sender(
    url: str,
    body: bytes,
    headers: Mapping[str, str],
    timeout: float,
    *,
    method: str = "POST",
    max_bytes: int = RESPONSE_MAX_BYTES,
) -> tuple[int, bytes]:
    """The one HTTPS path for Google calls. ``mb google`` reads pass ``method="GET"``
    (with no body) and a larger ``max_bytes`` for report answers."""
    import urllib.error
    import urllib.request

    data = body if method == "POST" else None
    request = urllib.request.Request(url, data=data, headers=dict(headers), method=method)
    try:
        # The request carries a bearer token or a form body with secrets, so a
        # 3xx is never followed: it comes back as an ordinary non-ok answer.
        with http_safe.open_no_redirect(request, timeout=timeout) as response:
            return int(getattr(response, "status", 0) or 0), response.read(max_bytes)
    except urllib.error.HTTPError as exc:
        payload = b""
        try:
            payload = exc.read(RESPONSE_MAX_BYTES)
        except OSError:
            payload = b""
        return int(exc.code), payload


def _safe_code(value: Any) -> str:
    """An OAuth ``error``/``error_subtype`` value, or ``other`` if it is not one."""

    text = str(value or "")
    return text if _OAUTH_CODE_RE.fullmatch(text) else ("" if not text else "other")


def _secret_values(fields: Mapping[str, str], headers: Mapping[str, str]) -> tuple[str, ...]:
    found = [str(fields[name]) for name in SECRET_FIELDS if fields.get(name)]
    for key, value in headers.items():
        lowered = key.lower()
        if lowered == "authorization" or "token" in lowered or "secret" in lowered:
            found.append(str(value))
            parts = str(value).split()
            if len(parts) >= 2:
                found.append(parts[-1])
    return tuple(found)


@dataclass
class PostResult:
    """What a token POST hands back.

    ``payload`` (the parsed JSON body) stays in memory and out of ``repr``;
    ``upstream`` is share-safe: status, the OAuth error code and subtype only.
    """

    ok: bool
    state: str
    upstream: dict[str, Any]
    payload: dict[str, Any] = field(default_factory=dict, repr=False)


def http_post_form(
    url: str,
    fields: Mapping[str, str],
    *,
    headers: Mapping[str, str] | None = None,
    sender: Sender | None = None,
    timeout: float = TOKEN_TIMEOUT_SECONDS,
    endpoint_family: str = "google_oauth_token",
) -> PostResult:
    """POST ``fields`` form-encoded and classify the outcome without leaking.

    The redaction set is built from the secret fields in the body and any
    bearer or token header. Every string handed back passes through the
    redactor; the response body never enters ``upstream``.
    """

    send = sender if sender is not None else _urllib_sender
    sent_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        **dict(headers or {}),
    }
    secret_values = _secret_values(fields, sent_headers)
    body = urllib.parse.urlencode(dict(fields)).encode("ascii")
    upstream: dict[str, Any] = {
        "endpoint_family": endpoint_family,
        "http_status": None,
        "response_received": False,
        "error_code": "",
        "error_subtype": "",
        "safe_to_share": True,
    }
    try:
        status, raw = send(url, body, sent_headers, timeout)
    except (OSError, http.client.HTTPException):
        return PostResult(ok=False, state=STATE_UNVALIDATED, upstream=upstream)
    upstream["http_status"] = int(status)
    upstream["response_received"] = True
    payload: dict[str, Any] = {}
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, ValueError, RecursionError):
        # RecursionError: a hostile, deeply nested body reads as unreadable.
        parsed = {}
    if isinstance(parsed, dict):
        payload = parsed
    error_code = _safe_code(payload.get("error"))
    error_subtype = _safe_code(payload.get("error_subtype"))
    upstream["error_code"] = _redact(error_code, secret_values)
    upstream["error_subtype"] = _redact(error_subtype, secret_values)
    ok = 200 <= int(status) < 300 and not error_code
    state = (
        "ok"
        if ok
        else classify_error(
            error_code=error_code, error_subtype=error_subtype, http_status=int(status)
        )
    )
    return PostResult(ok=ok, state=state, upstream=upstream, payload=payload if ok else {})


def classify_error(
    *,
    error_code: str = "",
    error_subtype: str = "",
    http_status: int | None = None,
    network_failure: bool = False,
    timed_out: bool = False,
) -> str:
    """Map an OAuth failure to a connect state. ``error_description`` is never read."""

    if timed_out:
        return STATE_BOOTSTRAP_TIMEOUT
    if network_failure or (http_status is not None and http_status >= 500):
        return STATE_UNVALIDATED
    if http_status is not None and (
        http_status in TRANSIENT_HTTP_STATUSES
        or 300 <= http_status < 400
        or (http_status >= 400 and not error_code and not error_subtype)
    ):
        # A timeout, a rate limit, a redirect (never followed) or an error with
        # no OAuth code says nothing about the client or the grant.
        return STATE_UNVALIDATED
    if error_code == "invalid_grant" or error_subtype == "invalid_rapt":
        return STATE_REAUTH_REQUIRED
    if error_code == "access_denied":
        return STATE_CONSENT_DENIED
    # invalid_client and every other OAuth code: the request or client is wrong.
    return STATE_INVALID


class TokenResponse(Mapping[str, Any]):
    """The token fields Google returned, held so they never show by accident.

    A read-only mapping, not a ``dict`` or a dataclass: ``repr``, ``str`` and
    pretty printers that expand containers (rich ``show_locals``) see the
    field names only, never a token value.
    """

    __slots__ = ("_fields",)

    def __init__(self, fields: Mapping[str, Any]) -> None:
        self._fields = dict(fields)

    def __getitem__(self, key: str) -> Any:
        return self._fields[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._fields)

    def __len__(self) -> int:
        return len(self._fields)

    def __repr__(self) -> str:
        return f"TokenResponse(fields={sorted(self._fields)!r})"

    __str__ = __repr__


# Code-exchange refusals by the OAuth `error` code: (rule, state). The refresh
# grant keeps `token_request_failed`; `mb connect token` words those itself.
_EXCHANGE_REFUSALS: dict[str, tuple[str, str]] = {
    "invalid_client": ("oauth_client_rejected", STATE_INVALID),
    "unauthorized_client": ("oauth_client_unauthorized", STATE_INVALID),
    "invalid_scope": ("oauth_scope_rejected", STATE_INVALID),
    # At sign-in this is the one-time code, not a stored grant, so a new
    # sign-in (not `--reauth`) is the repair.
    "invalid_grant": ("authorization_code_rejected", STATE_INVALID),
}


def _token_call(
    fields: dict[str, str], sender: Sender | None, *, exchange: bool = False
) -> TokenResponse:
    result = http_post_form(TOKEN_ENDPOINT, fields, sender=sender)
    if not result.ok:
        status = result.upstream.get("http_status")
        state = result.state
        if not result.upstream["response_received"]:
            rule = "token_unreachable"
        elif isinstance(status, int) and 300 <= status < 400:
            rule = "token_unexpected_redirect"
        else:
            rule = "token_request_failed"
            code = str(result.upstream.get("error_code") or "")
            if exchange and state != STATE_UNVALIDATED and code in _EXCHANGE_REFUSALS:
                rule, state = _EXCHANGE_REFUSALS[code]
        raise GoogleOAuthError(rule, state, upstream=result.upstream)
    access_token = result.payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise GoogleOAuthError(
            "token_response_malformed", STATE_UNVALIDATED, upstream=result.upstream
        )
    return TokenResponse(
        {name: result.payload[name] for name in TOKEN_FIELDS if name in result.payload}
    )


def exchange_code(
    *,
    client_id: str,
    client_secret: str | None,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    sender: Sender | None = None,
) -> TokenResponse:
    """Exchange an authorization code; returns only the token fields."""

    fields = {
        "client_id": client_id,
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        fields["client_secret"] = client_secret
    return _token_call(fields, sender, exchange=True)


def refresh_access_token(
    *,
    client_id: str,
    client_secret: str | None,
    refresh_token: str,
    sender: Sender | None = None,
) -> TokenResponse:
    """Mint an access token from a refresh token; returns only the token fields."""

    fields = {
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    if client_secret:
        fields["client_secret"] = client_secret
    return _token_call(fields, sender)


def granted_labels(scope: str) -> list[str]:
    """Labels (``search_console``, ``ga4``) for the scopes Google actually granted."""

    granted = set(scope.split())
    return [label for scope_url, label in SCOPE_LABELS.items() if scope_url in granted]
