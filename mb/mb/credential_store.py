"""Bounded, platform-native credential storage for provider connections.

The public CLI talks to this module only. Native APIs run in a short-lived
helper process so a locked or wedged OS store cannot hang unattended work.
Secret values travel over stdin and stdout, never process arguments or error
messages.
"""

from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, NamedTuple

from mb.durable import atomic_write_text

SERVICE_NAME = "mainbranch"
CREDENTIAL_HELPER_TIMEOUT_SECONDS = 8
# Only `mb connect repair --keychain` runs the helper interactively: a human at
# a terminal needs time to answer a macOS dialog. Every other caller keeps the
# short deadline and never lets the helper show a dialog.
INTERACTIVE_CREDENTIAL_TIMEOUT_SECONDS = 60
KEYCHAIN_REPAIR_COMMAND = "mb connect repair --keychain"
KEYCHAIN_REPAIR_ALL_COMMAND = "mb connect repair --keychain --all"
HELPER_STATES = {
    "ready",
    "missing",
    "locked",
    "auth-failed",
    "prompt-pending",
    "unavailable",
    "not-checked",
}
# A read that starts with less budget left than this cannot finish (helper
# start-up, a keychain call and the helper's own exit headroom), so an
# aggregate command reports the item as not checked instead of letting it fail
# on the clock and read as a broken credential (#1151).
MIN_PROBE_SECONDS = 1.5
# A read given this much less than its full time by a shared budget counts as
# cut short by it (see `_run_helper`).
CLIP_SLACK_SECONDS = 2.0
HELPER_OUTPUT_LIMIT = 1024 * 1024
# The helper's own deadline ends this long before the parent stops waiting, so
# it can finish or undo a step and stop its `security` children first.
HELPER_EXIT_HEADROOM_SECONDS = 1.0
SUPPORTED_BACKENDS = {"auto", "macos-keychain", "secret-service", "keyring", "local-file"}

KEYCHAIN_RESET_WARNING = (
    "Do not reset or delete the login keychain — that destroys every credential "
    "already stored in it."
)
BACKEND_REPAIRS: dict[str, dict[str, str]] = {
    "keychain_locked": {
        "summary": "The macOS login Keychain is locked, so credentials cannot be read or written.",
        "repair": (
            "Unlock it interactively inside the reader's owning user security session, then "
            "rerun the command in that same session. A desktop unlock does not unlock every "
            "already-running remote session. "
            f"{KEYCHAIN_RESET_WARNING}"
        ),
        "repair_command": "security unlock-keychain ~/Library/Keychains/login.keychain-db",
    },
    "keychain_prompt_pending": {
        "summary": (
            "macOS is asking whether this mb install may read the stored credential "
            "(keychain prompt pending). Unattended runs do not wait on that dialog."
        ),
        "repair": (
            f"From a terminal in this hub, run `{KEYCHAIN_REPAIR_COMMAND}` and choose "
            "Always Allow (not Allow) when macOS asks. It moves the credential to the macOS "
            "security tool, so later Python or mb updates do not ask again. "
            f"{KEYCHAIN_RESET_WARNING}"
        ),
        "repair_command": KEYCHAIN_REPAIR_COMMAND,
    },
    "keychain_auth_failed": {
        "summary": (
            "The macOS login Keychain rejected credential access, so credentials "
            "cannot be read or written."
        ),
        "repair": (
            "If backend health is ready, approve the installed reader identity in this item's "
            "Access Control or reconnect from that stable installed mb. Otherwise unlock the "
            "login keychain inside the reader's owning security session. "
            f"{KEYCHAIN_RESET_WARNING}"
        ),
        "repair_command": "open -a 'Keychain Access'",
    },
    "keychain_unavailable": {
        "summary": "The macOS Keychain did not answer, so credentials cannot be read or written.",
        "repair": (
            "Run the reader as the logged-in user in its intended GUI launchd security session, "
            "check the login keychain there, then rerun the command. "
            f"{KEYCHAIN_RESET_WARNING}"
        ),
        "repair_command": "open -a 'Keychain Access'",
    },
    "secret_service_locked": {
        "summary": "The Linux Secret Service collection is locked.",
        "repair": (
            "Unlock the existing login collection in the desktop keyring application, then "
            "rerun the command. Main Branch will not open an unlock prompt during unattended work."
        ),
        "repair_command": "",
    },
    "secret_service_unavailable": {
        "summary": "The Linux Secret Service backend is unavailable.",
        "repair": (
            "Start or repair the desktop Secret Service and its existing default collection, "
            "then rerun the command."
        ),
        "repair_command": "",
    },
    "credential_store_timeout": {
        "summary": "The credential store did not answer before the safety deadline.",
        "repair": (
            "Check or unlock the operating-system credential store interactively, then rerun "
            "the command. Main Branch stopped the unattended attempt."
        ),
        "repair_command": "",
    },
    "backend_incompatible": {
        "summary": "The recorded credential backend is incompatible with this operating system.",
        "repair": (
            "Reconnect this provider on the current machine to its native credential store. "
            "Main Branch will not silently switch stores."
        ),
        "repair_command": "",
    },
    "local_file_corrupt": {
        "summary": "The explicit local credential file is malformed or unreadable.",
        "repair": (
            "Repair or restore the local credential file before reconnecting. Main Branch "
            "refused to overwrite it."
        ),
        "repair_command": "",
    },
    "local_file_unavailable": {
        "summary": "The explicit local credential file is unavailable.",
        "repair": "Check its directory and permissions, then rerun the command.",
        "repair_command": "",
    },
}


def backend_repair(reason: str) -> dict[str, str]:
    """Return sanitized operator guidance for one backend reason."""

    return BACKEND_REPAIRS.get(reason, BACKEND_REPAIRS["keychain_unavailable"])


def new_credential_deadline() -> float:
    """Return one monotonic deadline shared by an aggregate credential command."""

    return time.monotonic() + CREDENTIAL_HELPER_TIMEOUT_SECONDS


class CredentialStoreError(RuntimeError):
    """A sanitized credential-store failure safe to show to an operator."""

    def __init__(self, reason: str, message: str = "") -> None:
        detail = backend_repair(reason)
        super().__init__(message or f"{detail['summary']} {detail['repair']}")
        self.reason = reason


class SecretProbe(NamedTuple):
    """Result of reading one credential reference."""

    value: str
    present: bool
    backend_ok: bool
    reason: str
    # True when this read moved a legacy macOS item to /usr/bin/security.
    migrated: bool = False
    # macOS only: "security" when /usr/bin/security owns the item (Python
    # changes cannot prompt), "legacy" when a Python interpreter does.
    owner: str = ""
    # True when no read happened because the command's credential budget was
    # spent. Nothing is known about the item: it is neither present nor absent,
    # and the backend is not known to be unhealthy (#1151).
    not_checked: bool = False

    def __repr__(self) -> str:
        # The value is a secret: keep it out of repr, str and Rich's show_locals.
        extra = ", not_checked=True" if self.not_checked else ""
        return (
            f"SecretProbe(value=<{'set' if self.value else 'empty'}>, present={self.present!r}, "
            f"backend_ok={self.backend_ok!r}, reason={self.reason!r}, "
            f"migrated={self.migrated!r}, owner={self.owner!r}{extra})"
        )


def select_secret_backend(requested: str | None = None) -> str:
    """Select one backend without silently falling back to plaintext storage."""

    raw = requested
    if raw is None:
        raw = os.environ.get("MB_CONNECT_SECRET_BACKEND", "auto")
    choice = str(raw).strip().lower()
    if choice not in SUPPORTED_BACKENDS:
        supported = ", ".join(sorted(SUPPORTED_BACKENDS - {"keyring"}))
        raise ValueError(f"unknown credential backend {choice!r}; choose one of: {supported}")
    if choice == "local-file":
        return choice
    system = platform.system()
    if choice == "keyring":
        # Releases before #959 recorded the generic `keyring` name. The native
        # adapters address the same service/account records without retaining
        # keyring's unbounded, backend-dependent runtime behavior.
        if system == "Darwin":
            return "macos-keychain"
        if system == "Linux":
            return "secret-service"
        raise CredentialStoreError("backend_incompatible")
    if choice == "auto":
        if system == "Darwin":
            return "macos-keychain"
        if system == "Linux":
            return "secret-service"
        raise CredentialStoreError("backend_incompatible")
    if choice == "macos-keychain" and system != "Darwin":
        raise CredentialStoreError("backend_incompatible")
    if choice == "secret-service" and system != "Linux":
        raise CredentialStoreError("backend_incompatible")
    return choice


class SecretStore:
    """Credential-store facade used by connect, status, token, and doctor."""

    def __init__(self, backend: str | None = None) -> None:
        self.backend = select_secret_backend(backend)

    def set(
        self,
        ref: str,
        value: str,
        *,
        deadline: float | None = None,
        interactive: bool = False,
    ) -> None:
        if self.backend == "local-file":
            _local_set(ref, value)
            return
        result = _run_helper(
            self.backend,
            "set",
            ref=ref,
            value=value,
            deadline=deadline,
            interactive=interactive,
        )
        state = str(result.get("state") or "unavailable")
        if state != "ready":
            raise CredentialStoreError(_reason_for(self.backend, state))

    def get(self, ref: str) -> str:
        return self.probe(ref).value

    def probe(
        self,
        ref: str,
        *,
        deadline: float | None = None,
        interactive: bool = False,
        allow_not_checked: bool = False,
    ) -> SecretProbe:
        """Read one reference.

        ``allow_not_checked`` is for the status commands: when a shared
        ``deadline`` leaves too little time to read, they get a probe marked
        ``not_checked`` rather than a failure that looks like a broken backend.
        Every other caller gets the timeout failure it always got.
        """

        if not ref:
            return SecretProbe("", False, True, "")
        if self.backend == "local-file":
            try:
                data = _read_local_secrets()
            except CredentialStoreError as exc:
                return SecretProbe("", False, False, exc.reason)
            if ref not in data:
                return SecretProbe("", False, True, "")
            return SecretProbe(data[ref], True, True, "")
        result = _run_helper(
            self.backend, "get", ref=ref, deadline=deadline, interactive=interactive
        )
        state = str(result.get("state") or "unavailable")
        if state == "missing":
            return SecretProbe("", False, True, "")
        if state == "not-checked" and allow_not_checked:
            return SecretProbe("", False, True, "", not_checked=True)
        if state != "ready":
            return SecretProbe("", False, False, _reason_for(self.backend, state))
        value = result.get("value")
        if not isinstance(value, str):
            return SecretProbe("", False, False, _reason_for(self.backend, "unavailable"))
        owner = result.get("owner")
        return SecretProbe(
            value,
            True,
            True,
            "",
            result.get("migrated") is True,
            owner if owner in {"security", "legacy"} else "",
        )

    def health(self, *, deadline: float | None = None) -> dict[str, Any]:
        reason = ""
        if self.backend == "local-file":
            try:
                _read_local_secrets()
            except CredentialStoreError as exc:
                reason = exc.reason
        else:
            result = _run_helper(self.backend, "health", deadline=deadline)
            state = str(result.get("state") or "unavailable")
            if state != "ready":
                reason = _reason_for(self.backend, state)
        detail = backend_repair(reason) if reason else None
        return {
            "backend": self.backend,
            "ok": not reason,
            "state": reason or "ready",
            "summary": (
                detail["summary"]
                if detail is not None
                else f"Credential backend {self.backend} is ready."
            ),
            "repair": detail["repair"] if detail is not None else "",
            "repair_command": detail["repair_command"] if detail is not None else "",
            "safe_to_share": True,
        }

    def boundary(self) -> str:
        if self.backend == "macos-keychain":
            return "stored in the macOS login Keychain"
        if self.backend == "secret-service":
            return "stored in the Linux Secret Service default collection"
        return f"stored outside the repo in {_local_secret_path()}"

    def delete(self, ref: str) -> None:
        """Delete an exact reference; used for bounded synthetic native smoke cleanup."""

        if self.backend == "local-file":
            data = _read_local_secrets()
            if ref in data:
                del data[ref]
                _write_local_secrets(data)
            return
        result = _run_helper(self.backend, "delete", ref=ref)
        state = str(result.get("state") or "unavailable")
        if state not in {"ready", "missing"}:
            raise CredentialStoreError(_reason_for(self.backend, state))


class KeychainListing(NamedTuple):
    """Main Branch refs found in the macOS Keychain (attributes only)."""

    refs: list[str]
    # False unless the helper proved the listing whole: `found` equal to the
    # refs returned. A capped listing, or one from a helper that does not
    # report `found` (another mb version), is incomplete.
    complete: bool
    # Refs the helper found in all, when it said; None when it did not.
    found: int | None
    limit: int = 0


def list_keychain_refs(*, deadline: float | None = None) -> KeychainListing:
    """Every Main Branch ref in the macOS Keychain, staged copies included.

    The helper asks for item attributes only, never data, with keychain
    interaction off, so nothing is decrypted and no dialog can appear. Raises
    ``CredentialStoreError`` when the keychain cannot be listed.
    """

    backend = select_secret_backend("macos-keychain")
    result = _run_helper(backend, "list", deadline=deadline)
    state = str(result.get("state") or "unavailable")
    if state != "ready":
        raise CredentialStoreError(_reason_for(backend, state))
    refs = result.get("refs")
    if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
        raise CredentialStoreError(_reason_for(backend, "unavailable"))

    def count(key: str) -> int | None:
        value = result.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    found = count("found")
    if found is not None and found < len(refs):
        found = None
    return KeychainListing(
        list(refs),
        complete=found == len(refs) and result.get("truncated") is not True,
        found=found,
        limit=count("limit") or 0,
    )


def _reason_for(backend: str, state: str) -> str:
    if state in {"timed-out", "not-checked"}:
        return "credential_store_timeout"
    if state == "incompatible":
        return "backend_incompatible"
    if backend == "macos-keychain":
        if state == "locked":
            return "keychain_locked"
        if state == "prompt-pending":
            return "keychain_prompt_pending"
        if state == "auth-failed":
            return "keychain_auth_failed"
        return "keychain_unavailable"
    if backend == "secret-service":
        if state in {"locked", "auth-failed", "prompt-pending"}:
            return "secret_service_locked"
        return "secret_service_unavailable"
    return "local_file_unavailable"


def _run_helper(
    backend: str,
    action: str,
    *,
    ref: str = "",
    value: str | None = None,
    deadline: float | None = None,
    interactive: bool = False,
) -> dict[str, Any]:
    # The helper treats anything but an explicit true as non-interactive.
    payload: dict[str, Any] = {"ref": ref, "interactive": interactive is True}
    clipped = False
    if value is not None:
        payload["value"] = value
    timeout = float(
        INTERACTIVE_CREDENTIAL_TIMEOUT_SECONDS
        if interactive is True
        else CREDENTIAL_HELPER_TIMEOUT_SECONDS
    )
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if action == "get" and remaining < MIN_PROBE_SECONDS:
            # Too little left to read: nothing was asked of the store.
            return {"state": "not-checked"}
        if remaining <= 0:
            return {"state": "timed-out"}
        if remaining < timeout:
            # Only a read the shared budget cut well short is "clipped". The
            # slack covers the repo and git work an aggregate command does
            # before its first read, so a read that had essentially its full
            # time and still hung is the store's own timeout, not starvation.
            clipped = action == "get" and remaining < timeout - CLIP_SLACK_SECONDS
            timeout = remaining
    # An absolute wall-clock deadline: the helper refuses to start a move it
    # cannot finish, and stops its own `security` calls, before this process
    # gives up on it. A pending dialog is then reported as such.
    payload["deadline_epoch"] = time.time() + timeout - HELPER_EXIT_HEADROOM_SECONDS
    try:
        returncode, stdout = _invoke_helper(
            [sys.executable, "-m", "mb._credential_helper", backend, action],
            json.dumps(payload),
            timeout,
        )
    except subprocess.TimeoutExpired:
        if clipped:
            return _run_helper(backend, action, ref=ref, value=value, interactive=interactive)
        return {"state": "timed-out"}
    except (OSError, subprocess.SubprocessError):
        return {"state": "unavailable"}
    if len(stdout) > HELPER_OUTPUT_LIMIT:
        return {"state": "unavailable"}
    try:
        result = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return {"state": "unavailable"}
    if not isinstance(result, dict):
        return {"state": "unavailable"}
    state = result.get("state")
    if state not in HELPER_STATES:
        return {"state": "unavailable"}
    if returncode != (0 if state in {"ready", "missing"} else 1):
        return {"state": "unavailable"}
    if state == "not-checked":
        # The helper ran out of time after the parent had launched it, so the
        # read did start. Exec reports that as a store timeout; a read the
        # shared budget cut short gets one more try with a full budget first.
        if not clipped:
            return {"state": "timed-out"}
        return _run_helper(backend, action, ref=ref, value=value, interactive=interactive)
    return result


def _helper_cwd() -> str:
    """The directory that holds this ``mb`` package.

    ``python -m`` puts the working directory first on ``sys.path``. Starting
    the helper here makes ``mb._credential_helper`` resolve to this package,
    whatever directory the command was run from.
    """

    return str(Path(__file__).resolve().parent.parent)


def _invoke_helper(args: list[str], stdin: str, timeout: float) -> tuple[int, str]:
    """Run the helper in its own process group; on timeout kill the whole group.

    Killing only the helper could leave a `security` child it started running
    (and, in the worst case, holding a dialog). The group takes them all.
    """

    process = subprocess.Popen(
        args,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
        cwd=_helper_cwd(),
    )
    try:
        stdout, _ = process.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group(process)
        raise
    return int(process.returncode or 0), stdout or ""


def _kill_group(process: Any) -> None:
    pid = getattr(process, "pid", None)
    if isinstance(pid, int) and pid > 1:
        with suppress(OSError):
            os.killpg(pid, signal.SIGKILL)
    with suppress(Exception):
        process.kill()
    with suppress(Exception):
        process.communicate(timeout=2)


def _local_secret_path() -> Path:
    home = Path(os.environ.get("MAINBRANCH_HOME", Path.home() / ".mainbranch")).expanduser()
    return home / "secrets" / "connect.json"


def _read_local_secrets() -> dict[str, str]:
    path = _local_secret_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CredentialStoreError("local_file_corrupt") from exc
    except OSError as exc:
        raise CredentialStoreError("local_file_unavailable") from exc
    if not isinstance(raw, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in raw.items()
    ):
        raise CredentialStoreError("local_file_corrupt")
    return dict(raw)


def _write_local_secrets(data: dict[str, str]) -> None:
    path = _local_secret_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with suppress(OSError):
            path.parent.chmod(0o700)
        atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n", mode=0o600)
        with suppress(OSError):
            path.chmod(0o600)
    except OSError as exc:
        raise CredentialStoreError("local_file_unavailable") from exc


def _local_set(ref: str, value: str) -> None:
    data = _read_local_secrets()
    data[ref] = value
    _write_local_secrets(data)
