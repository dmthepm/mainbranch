"""``mb fleet`` — read-only status of every site across an operator's hubs.

The hub list is a user-level file (``fleet.toml`` under the user's config
directory), never a repo file, because it names private repos and local paths.
Children come from each hub's ``core/operations/repo-topology.md``, then each
child's ``.mainbranch/repo.json`` and its ``sites`` list.

``refresh`` reads GitHub through ``gh`` and Cloudflare Pages through the hub's
``mb connect`` credential, and stores one snapshot in a SQLite cache under the
user's state directory. ``status`` reads only that cache.

Nothing here writes to a repo, a provider or an account. Tokens stay in memory:
they are never stored, logged or put in a result.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sqlite3
import subprocess
from collections.abc import Callable
from contextlib import closing, suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mb import http_safe, topology
from mb.credential_store import KEYCHAIN_REPAIR_COMMAND

FLEET_SCHEMA = "mb.fleet.v0"
CONFIG_FILENAME = "fleet.toml"
CACHE_FILENAME = "fleet.db"
KEEP_SNAPSHOTS = 10
CLOUDFLARE_API = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_TIMEOUT_SECONDS = 20
CLOUDFLARE_PROVIDERS = frozenset({"cloudflare-pages", "cloudflare"})
DEPENDABOT_LOGINS = frozenset({"dependabot[bot]", "app/dependabot"})
SEVERITIES = ("critical", "high", "medium", "low")
CI_FAILING = frozenset(
    {"failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"}
)
FRAMEWORK_PACKAGES: tuple[tuple[str, str], ...] = (
    ("astro", "astro"),
    ("next", "next"),
    ("@shopify/hydrogen", "hydrogen"),
    ("nuxt", "nuxt"),
    ("@sveltejs/kit", "sveltekit"),
    ("@remix-run/react", "remix"),
    ("gatsby", "gatsby"),
    ("vite", "vite"),
)
_HTTP_STATUS_RE = re.compile(r"\(HTTP (\d{3})\)")
_TAG_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


class FleetConfigError(ValueError):
    """``fleet.toml`` is missing, unreadable or invalid."""


# ---------------------------------------------------------------------------
# Locations and config
# ---------------------------------------------------------------------------


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "mainbranch" / CONFIG_FILENAME


def cache_path() -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base).expanduser() / "mainbranch" / CACHE_FILENAME


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Read and validate ``fleet.toml``.

    Shape, one table per hub::

        [[hubs]]
        name = "example-co"                  # optional label
        remote = "github:example-co/hub"     # required
        checkout = "~/src/example-co/hub"    # optional, local speed-up
        cloudflare = "cloudflare"            # optional mb connect id (needs checkout)
        connect_checkout = "~/src/..."       # optional: checkout holding that
                                             # connection, when not `checkout`
    """
    target = path or config_path()
    try:
        # Standard library from Python 3.11; mb fleet adds no dependency for 3.10.
        tomllib: Any = importlib.import_module("tomllib")
    except ImportError as exc:
        raise FleetConfigError("mb fleet reads fleet.toml and needs Python 3.11 or newer") from exc
    if not target.is_file():
        raise FleetConfigError(
            f"no hub list at {target}; create it with one [[hubs]] table per hub "
            "(see docs/fleet.md)"
        )
    try:
        raw = tomllib.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise FleetConfigError(f"{target} is not valid TOML: {exc}") from exc
    hubs_raw = raw.get("hubs")
    if not isinstance(hubs_raw, list) or not hubs_raw:
        raise FleetConfigError(f"{target} needs at least one [[hubs]] table")
    hubs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(hubs_raw):
        if not isinstance(entry, dict):
            raise FleetConfigError(f"hubs[{index}] must be a table")
        remote_full = topology.normalize_remote(entry.get("remote"))
        if not remote_full:
            raise FleetConfigError(f"hubs[{index}].remote must name a GitHub owner/repo")
        name = str(entry.get("name") or remote_full).strip()
        if name in seen:
            raise FleetConfigError(f"hubs[{index}].name {name!r} is listed twice")
        seen.add(name)
        checkout_raw = entry.get("checkout")
        checkout = Path(str(checkout_raw)).expanduser() if checkout_raw else None
        cloudflare = str(entry.get("cloudflare") or "").strip()
        connect_raw = entry.get("connect_checkout")
        connect_checkout = Path(str(connect_raw)).expanduser() if connect_raw else checkout
        if cloudflare and connect_checkout is None:
            raise FleetConfigError(
                f"hubs[{index}].cloudflare needs a checkout: mb connect credentials "
                "are resolved from the hub's local checkout"
            )
        hubs.append(
            {
                "name": name,
                "remote_full_name": remote_full,
                "checkout": checkout,
                "cloudflare": cloudflare,
                "connect_checkout": connect_checkout,
            }
        )
    return {"path": target, "hubs": hubs}


def hubs_list(path: Path | None = None) -> dict[str, Any]:
    config = load_config(path)
    return {
        "ok": True,
        "schema": FLEET_SCHEMA,
        "config": str(config["path"]),
        "hubs": [
            {
                "name": hub["name"],
                "remote_full_name": hub["remote_full_name"],
                "checkout": str(hub["checkout"]) if hub["checkout"] else "",
                "checkout_present": bool(hub["checkout"] and hub["checkout"].is_dir()),
                "cloudflare": hub["cloudflare"],
            }
            for hub in config["hubs"]
        ],
    }


# ---------------------------------------------------------------------------
# Readers (injectable so tests never touch the network)
# ---------------------------------------------------------------------------

GhRunner = Callable[[list[str]], tuple[int, str, str]]
HttpGet = Callable[[str, dict[str, str]], tuple[int, Any]]


def _run_gh(args: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return result.returncode, result.stdout, result.stderr


@dataclass
class GitHub:
    """GET-only GitHub reader over ``gh api``."""

    runner: GhRunner = _run_gh
    calls: int = 0

    def _call(self, args: list[str]) -> tuple[int, str]:
        self.calls += 1
        code, stdout, stderr = self.runner(["api", "--method", "GET", *args])
        if code == 0:
            return 200, stdout
        match = _HTTP_STATUS_RE.search(stderr or "")
        return (int(match.group(1)) if match else 0), ""

    def json(self, path: str, *, paginate: bool = False) -> tuple[int, Any]:
        args = ["--paginate", "--slurp", path] if paginate else [path]
        status, text = self._call(args)
        if status != 200:
            return status, None
        try:
            data = json.loads(text) if text.strip() else None
        except json.JSONDecodeError:
            return 0, None
        if paginate and isinstance(data, list):
            flat: list[Any] = []
            for page in data:
                flat.extend(page if isinstance(page, list) else [page])
            data = flat
        return 200, data

    def raw(self, path: str) -> tuple[int, str]:
        return self._call(["-H", "Accept: application/vnd.github.raw", path])


def _http_get(url: str, headers: dict[str, str]) -> tuple[int, Any]:
    import urllib.error
    import urllib.request

    request = urllib.request.Request(url, headers=headers)
    try:
        with http_safe.open_no_redirect(request, timeout=CLOUDFLARE_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", 200) or 200)
            body = response.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), None
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, None
    try:
        return status, json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return 0, None


@dataclass
class Cloudflare:
    """GET-only Cloudflare Pages reader. The token never leaves this object."""

    http_get: HttpGet = _http_get
    calls: int = 0

    def production_deployments(
        self, token: str, account_id: str
    ) -> tuple[dict[str, dict[str, Any]], str]:
        """Map project name to its current production deployment facts.

        Returns ``(projects, error)``. Any failed page, an unsuccessful envelope
        (``success`` not true, whatever the HTTP status) or a malformed body is
        an error, and then no projects are returned: a partial list would turn
        real projects into ``project_not_found``.

        Keeps only the commit hash, dirty flag, branch, time and domains: a
        deployment object also carries build environment variables, which must
        never reach the cache.
        """
        projects: dict[str, dict[str, Any]] = {}
        page = 1
        while True:
            self.calls += 1
            url = f"{CLOUDFLARE_API}/accounts/{account_id}/pages/projects?per_page=10&page={page}"
            status, payload = self.http_get(url, {"Authorization": f"Bearer {token}"})
            if status != 200:
                return {}, f"cloudflare pages read failed (HTTP {status or 'error'})"
            if not isinstance(payload, dict):
                return {}, "cloudflare pages read failed: malformed response (HTTP 200)"
            if payload.get("success") is not True:
                return {}, (
                    "cloudflare pages read failed: unsuccessful response"
                    f"{_cloudflare_codes(payload)} (HTTP 200)"
                )
            result = payload.get("result")
            info = payload.get("result_info")
            info = info if isinstance(info, dict) else {}
            try:
                total_pages = int(info.get("total_pages") or 1)
            except (TypeError, ValueError):
                total_pages = 0
            if not isinstance(result, list) or total_pages < 1:
                return {}, "cloudflare pages read failed: malformed response (HTTP 200)"
            for project in result:
                if not isinstance(project, dict) or not project.get("name"):
                    continue
                projects[str(project["name"])] = _deployment_facts(project)
            if page >= total_pages:
                return projects, ""
            page += 1


def _cloudflare_codes(payload: dict[str, Any]) -> str:
    """Cloudflare's numeric error codes only; messages are not repeated."""
    errors = payload.get("errors")
    codes = [
        str(item["code"])
        for item in (errors if isinstance(errors, list) else [])
        if isinstance(item, dict) and isinstance(item.get("code"), int)
    ]
    return f", codes {', '.join(codes)}" if codes else ""


def _deployment_facts(project: dict[str, Any]) -> dict[str, Any]:
    deployment = project.get("canonical_deployment")
    deployment = deployment if isinstance(deployment, dict) else {}
    trigger = deployment.get("deployment_trigger")
    trigger = trigger if isinstance(trigger, dict) else {}
    metadata = trigger.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    dirty = metadata.get("commit_dirty")
    domains = project.get("domains") if isinstance(project.get("domains"), list) else []
    return {
        "project": str(project.get("name") or ""),
        "domains": [str(domain) for domain in domains or []],
        "production_branch": str(project.get("production_branch") or ""),
        "has_deployment": bool(deployment),
        "deployment_id": str(deployment.get("short_id") or ""),
        "deployed_at": str(deployment.get("created_on") or ""),
        "commit_hash": str(metadata.get("commit_hash") or ""),
        "commit_dirty": dirty if isinstance(dirty, bool) else None,
        "branch": str(metadata.get("branch") or ""),
        "trigger": str(trigger.get("type") or ""),
    }


def _cloudflare_credentials(connection: str, checkout: Path, hub: str = "") -> tuple[str, str, str]:
    """Return (token, account_id, error). The token is for in-memory use only.

    Each call reads with its own credential deadline, so one slow hub cannot
    use up another hub's time.
    """
    from mb import connect

    try:
        token_result = connect.read_token(connection, checkout)
        metadata = connect.read_metadata(connection, checkout)
    except (ValueError, OSError) as exc:
        return "", "", f"cloudflare connection {connection!r} could not be read: {exc}"
    if not token_result.get("ok"):
        if token_result.get("backend_state") == "keychain_prompt_pending":
            where = f" in {hub}" if hub else ""
            return (
                "",
                "",
                f"cloudflare connection {connection!r}: keychain prompt pending; "
                f"run {KEYCHAIN_REPAIR_COMMAND}{where}",
            )
        return (
            "",
            "",
            (f"cloudflare connection {connection!r}: {token_result.get('error') or 'not ready'}"),
        )
    account_id = metadata.get("account_id", "")
    if not account_id:
        return "", "", f"cloudflare connection {connection!r} has no account_id metadata"
    return str(token_result.get("token") or ""), account_id, ""


# ---------------------------------------------------------------------------
# Package facts
# ---------------------------------------------------------------------------


def _version_from_spec(spec: str) -> str:
    match = re.search(r"\d+(?:\.\d+){0,2}", spec)
    return match.group(0) if match else ""


def framework_facts(package: dict[str, Any]) -> dict[str, str]:
    deps: dict[str, Any] = {}
    for key in ("devDependencies", "dependencies"):
        value = package.get(key)
        if isinstance(value, dict):
            deps.update(value)
    for package_name, label in FRAMEWORK_PACKAGES:
        spec = deps.get(package_name)
        if isinstance(spec, str):
            return {"name": label, "spec": spec, "version": _version_from_spec(spec)}
    return {"name": "", "spec": "", "version": ""}


def parse_pin(spec: str) -> dict[str, str]:
    """Classify a git or path dependency spec: tag, commit, branch, path or none."""
    if spec.startswith("file:") or spec.startswith("link:"):
        return {"kind": "path", "ref": spec.split(":", 1)[1], "repo": ""}
    body, _, ref = spec.partition("#")
    repo = topology.normalize_remote(body.removeprefix("git+").removeprefix("github:"))
    if not ref:
        return {"kind": "none", "ref": "", "repo": repo}
    if ref.startswith("semver:"):
        return {"kind": "other", "ref": ref, "repo": repo}
    if _TAG_RE.match(ref):
        return {"kind": "tag", "ref": ref, "repo": repo}
    if _SHA_RE.match(ref):
        return {"kind": "commit", "ref": ref, "repo": repo}
    return {"kind": "branch", "ref": ref, "repo": repo}


def _is_source_dependency(spec: str) -> bool:
    if spec.startswith(("file:", "link:", "github:", "git+", "git:", "git@")):
        return True
    return "#" in spec and "/" in spec


def engine_pins(package: dict[str, Any]) -> list[dict[str, str]]:
    """Dependencies installed from a git ref or a local path (an engine pin)."""
    pins: list[dict[str, str]] = []
    for key in ("dependencies", "devDependencies"):
        value = package.get(key)
        if not isinstance(value, dict):
            continue
        for name, spec in sorted(value.items()):
            if isinstance(spec, str) and _is_source_dependency(spec):
                pins.append({"package": str(name), "spec": spec, **parse_pin(spec)})
    return pins


def latest_tag(names: list[str]) -> str:
    best: tuple[tuple[int, int, int], str] | None = None
    for name in names:
        match = _TAG_RE.match(name)
        if not match:
            continue
        key = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if best is None or key > best[0]:
            best = (key, name)
    return best[1] if best else ""


# ---------------------------------------------------------------------------
# Per-repo reads
# ---------------------------------------------------------------------------


def _ci_state(check_runs: list[Any]) -> dict[str, Any]:
    runs = [run for run in check_runs if isinstance(run, dict)]
    failing = sorted(
        str(run.get("name") or "")
        for run in runs
        if run.get("status") == "completed" and run.get("conclusion") in CI_FAILING
    )
    pending = [run for run in runs if run.get("status") != "completed"]
    if not runs:
        state = "none"
    elif failing:
        state = "failure"
    elif pending:
        state = "pending"
    else:
        state = "success"
    return {"state": state, "total": len(runs), "failing": failing}


def _dependabot_alerts(github: GitHub, full: str) -> dict[str, Any]:
    status, alerts = github.json(
        f"repos/{full}/dependabot/alerts?state=open&per_page=100", paginate=True
    )
    if status != 200 or not isinstance(alerts, list):
        return {"state": "unavailable", "http_status": status, "open": None, "by_severity": {}}
    counts = dict.fromkeys(SEVERITIES, 0)
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        severity = ""
        for source in ("security_vulnerability", "security_advisory"):
            block = alert.get(source)
            if isinstance(block, dict) and block.get("severity"):
                severity = str(block["severity"]).lower()
                break
        if severity in counts:
            counts[severity] += 1
    return {"state": "ok", "http_status": 200, "open": len(alerts), "by_severity": counts}


def _dependabot_prs(github: GitHub, full: str, now: datetime) -> dict[str, Any]:
    status, pulls = github.json(f"repos/{full}/pulls?state=open&per_page=100", paginate=True)
    if status != 200 or not isinstance(pulls, list):
        return {"state": "unavailable", "http_status": status, "open": None, "oldest_days": None}
    created: list[datetime] = []
    for pull in pulls:
        if not isinstance(pull, dict):
            continue
        user = pull.get("user")
        login = str(user.get("login") or "") if isinstance(user, dict) else ""
        if login in DEPENDABOT_LOGINS:
            stamp = _parse_time(str(pull.get("created_at") or ""))
            if stamp:
                created.append(stamp)
    oldest = (now - min(created)).days if created else None
    return {"state": "ok", "http_status": 200, "open": len(created), "oldest_days": oldest}


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _read_file(github: GitHub, full: str, rel: str) -> dict[str, Any]:
    """Read one repo file and say why when it could not be read.

    ``state`` is ``ok``, ``absent`` (a confirmed 404), ``unavailable`` (denied,
    rate-limited or any other failed read) or ``malformed`` (not a JSON object).
    Only ``absent`` means the file is not there.
    """
    status, text = github.raw(f"repos/{full}/contents/{rel}")
    if status == 404:
        return {"path": rel, "state": "absent", "http_status": 404, "text": ""}
    if status != 200:
        return {"path": rel, "state": "unavailable", "http_status": status, "text": ""}
    return {"path": rel, "state": "ok", "http_status": 200, "text": text}


def _package(github: GitHub, full: str, rel: str) -> dict[str, Any]:
    read = _read_file(github, full, rel)
    data: Any = None
    if read["state"] == "ok":
        try:
            data = json.loads(read["text"])
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            read["state"] = "malformed"
            data = None
    return {
        "path": rel,
        "state": read["state"],
        "http_status": read["http_status"],
        "data": data,
    }


def _read_problem(read: dict[str, Any]) -> str:
    """Public-safe refresh error for a file read that failed, else ``""``."""
    if read["state"] == "unavailable":
        return f"{read['path']} not readable (HTTP {read['http_status'] or 'error'})"
    if read["state"] == "malformed":
        return f"{read['path']} is not a valid JSON object"
    return ""


def _check_runs(github: GitHub, full: str, sha: str) -> dict[str, Any]:
    """Aggregate every page of check runs; ``unknown`` if any page fails."""
    unknown = {"state": "unknown", "total": 0, "failing": []}
    status, pages = github.json(
        f"repos/{full}/commits/{sha}/check-runs?per_page=100", paginate=True
    )
    if status != 200 or not isinstance(pages, list) or not pages:
        return unknown
    runs: list[Any] = []
    expected = 0
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("check_runs"), list):
            return unknown
        runs.extend(page["check_runs"])
        total = page.get("total_count")
        if isinstance(total, int):
            expected = max(expected, total)
    if len(runs) < expected:
        return unknown
    return _ci_state(runs)


def read_repo(github: GitHub, full: str, now: datetime) -> dict[str, Any]:
    """Read one repo's facts through the GitHub API. Never raises on API errors."""
    facts: dict[str, Any] = {"repo": full, "errors": []}
    status, meta = github.json(f"repos/{full}")
    if status != 200 or not isinstance(meta, dict):
        facts["errors"].append(f"repo not readable (HTTP {status or 'error'})")
        facts["readable"] = False
        return facts
    facts["readable"] = True
    branch = str(meta.get("default_branch") or "main")
    facts["default_branch"] = branch
    facts["archived"] = bool(meta.get("archived"))
    status, branch_data = github.json(f"repos/{full}/branches/{branch}")
    commit = branch_data.get("commit") if isinstance(branch_data, dict) else None
    sha = str(commit.get("sha") or "") if isinstance(commit, dict) else ""
    facts["main_sha"] = sha
    committed_at = ""
    if isinstance(commit, dict):
        inner = commit.get("commit")
        if isinstance(inner, dict):
            committer = inner.get("committer")
            if isinstance(committer, dict):
                committed_at = str(committer.get("date") or "")
    facts["main_committed_at"] = committed_at
    if sha:
        facts["ci"] = _check_runs(github, full, sha)
        if facts["ci"]["state"] == "unknown":
            facts["errors"].append("check runs on the default branch not fully readable")
    else:
        facts["errors"].append(f"default branch {branch!r} not readable")
        facts["ci"] = {"state": "unknown", "total": 0, "failing": []}
    read = _read_file(github, full, topology.CHILD_REPO_RELATIVE_PATH.as_posix())
    descriptor = topology.parse_descriptor_text(read["text"]) if read["state"] == "ok" else None
    if descriptor is not None and descriptor.get("error"):
        read["state"] = "malformed"
    facts["descriptor"] = descriptor
    facts["descriptor_read"] = {"state": read["state"], "http_status": read["http_status"]}
    if read["state"] == "malformed":
        facts["errors"].append(f"{read['path']}: {descriptor.get('error') if descriptor else ''}")
    elif problem := _read_problem(read):
        facts["errors"].append(problem)
    facts["package"] = _package(github, full, "package.json")
    facts["site_packages"] = {}
    for site in (descriptor or {}).get("sites") or []:
        site_dir = str(site.get("dir") or ".")
        if site_dir != "." and site_dir not in facts["site_packages"]:
            facts["site_packages"][site_dir] = _package(github, full, f"{site_dir}/package.json")
    for package in [facts["package"], *facts["site_packages"].values()]:
        if problem := _read_problem(package):
            facts["errors"].append(problem)
    facts["dependabot_alerts"] = _dependabot_alerts(github, full)
    facts["dependabot_prs"] = _dependabot_prs(github, full, now)
    return facts


def _site_package(facts: dict[str, Any], site_dir: str) -> dict[str, Any]:
    """The package.json that holds a site's facts.

    The site's own ``dir`` first; the repo root only after the site's file is
    confirmed absent, so a denied or failed read never borrows the root's facts.
    """
    root: dict[str, Any] = facts.get("package") or {
        "path": "package.json",
        "state": "absent",
        "data": None,
    }
    own: dict[str, Any] | None = (facts.get("site_packages") or {}).get(site_dir)
    if own is None or own.get("state") == "absent":
        return root
    return own


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------


def _hub_registry(github: GitHub, hub: dict[str, Any]) -> tuple[dict[str, Any], str]:
    checkout = hub.get("checkout")
    if isinstance(checkout, Path) and (checkout / topology.REGISTRY_RELATIVE_PATH).is_file():
        return topology.read_registry(checkout), "checkout"
    status, text = github.raw(
        f"repos/{hub['remote_full_name']}/contents/{topology.REGISTRY_RELATIVE_PATH}"
    )
    if status != 200:
        return {
            "found": False,
            "ok": False,
            "error": f"registry not readable (HTTP {status or 'error'})",
            "repos": [],
        }, "github"
    return topology.parse_registry_text(text), "github"


def _resolve_deploy(
    site: dict[str, Any] | None,
    entry: dict[str, Any],
    repo_name: str,
    hub_deploys: dict[str, Any],
) -> tuple[str, str, str, dict[str, Any] | None]:
    """Return (provider, project, source, deployment facts)."""
    declared = (site or {}).get("deploy") or {}
    provider = str(declared.get("provider") or "")
    project = str(declared.get("project") or "")
    projects: dict[str, dict[str, Any]] = hub_deploys.get("projects") or {}
    if project:
        if provider and provider not in CLOUDFLARE_PROVIDERS:
            return provider, project, "declared", None
        return provider or "cloudflare-pages", project, "declared", projects.get(project)
    if not projects:
        return provider, "", "", None
    for candidate in ((site or {}).get("slug"), repo_name):
        if candidate and candidate in projects:
            return "cloudflare-pages", str(candidate), "project_name_match", projects[candidate]
    domains = set((site or {}).get("domains") or [])
    if entry.get("domain"):
        domains.add(str(entry["domain"]))
    for name, facts in sorted(projects.items()):
        if domains & set(facts.get("domains") or []):
            return "cloudflare-pages", name, "domain_match", facts
    return provider, "", "", None


def _deploy_block(
    github: GitHub,
    full: str,
    main_sha: str,
    hub_deploys: dict[str, Any],
    provider: str,
    project: str,
    source: str,
    facts: dict[str, Any] | None,
    compare_cache: dict[tuple[str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    block: dict[str, Any] = {
        "provider": provider,
        "project": project,
        "project_source": source,
        "state": "",
        "deployed_sha": "",
        "dirty": None,
        "branch": "",
        "deployed_at": "",
        "matches_main": None,
        "compare": "",
        "behind_by": None,
    }
    if not project:
        block["state"] = "undeclared" if hub_deploys.get("state") == "ok" else "no_connection"
        if hub_deploys.get("state") == "error":
            block["state"] = "provider_error"
        return block
    if provider and provider not in CLOUDFLARE_PROVIDERS:
        block["state"] = "unsupported_provider"
        return block
    if hub_deploys.get("state") != "ok":
        block["state"] = (
            "no_connection" if hub_deploys.get("state") != "error" else "provider_error"
        )
        return block
    if facts is None:
        block["state"] = "project_not_found"
        return block
    if not facts.get("has_deployment"):
        block["state"] = "no_production_deployment"
        return block
    sha = str(facts.get("commit_hash") or "")
    block.update(
        {
            "state": "ok",
            "deployed_sha": sha,
            "dirty": facts.get("commit_dirty"),
            "branch": facts.get("branch") or "",
            "deployed_at": facts.get("deployed_at") or "",
        }
    )
    if not sha or not main_sha:
        block["state"] = "no_commit_hash" if not sha else "ok"
        return block
    block["matches_main"] = sha == main_sha or main_sha.startswith(sha)
    if block["matches_main"]:
        block["compare"] = "identical"
        block["behind_by"] = 0
        return block
    key = (full, sha, main_sha)
    if key not in compare_cache:
        status, data = github.json(f"repos/{full}/compare/{sha}...{main_sha}")
        if status == 200 and isinstance(data, dict):
            compare_cache[key] = {
                "compare": str(data.get("status") or ""),
                "behind_by": int(data.get("ahead_by") or 0),
            }
        else:
            compare_cache[key] = {"compare": "unknown_commit", "behind_by": None}
    block.update(compare_cache[key])
    return block


def _flags(row: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if (row.get("framework") or {}).get("state") in _UNREAD_STATES:
        flags.append("facts_unavailable")
    if row["ci"]["state"] == "failure":
        flags.append("ci_failing")
    deploy = row["deploy"]
    if deploy.get("dirty") is True:
        flags.append("deploy_dirty")
    if deploy.get("compare") in {"ahead", "diverged"}:
        flags.append("deploy_behind_main")
    elif deploy.get("matches_main") is False:
        flags.append("deploy_differs_from_main")
    pin = row.get("engine_pin")
    if pin:
        if pin["kind"] in {"path", "none", "branch"}:
            flags.append("engine_unpinned")
        elif pin.get("latest_tag") and pin.get("on_latest") is False:
            flags.append("engine_behind_latest")
    return flags


def _engine_pin(
    github: GitHub, package: dict[str, Any] | None, tags_cache: dict[str, list[str]]
) -> dict[str, Any] | None:
    if not package:
        return None
    pins = engine_pins(package)
    if not pins:
        return None
    pin: dict[str, Any] = dict(pins[0])
    repo = pin.get("repo") or ""
    if repo and pin["kind"] == "tag":
        if repo not in tags_cache:
            status, tags = github.json(f"repos/{repo}/tags?per_page=100", paginate=True)
            names = [
                str(tag.get("name") or "")
                for tag in (tags if status == 200 and isinstance(tags, list) else [])
                if isinstance(tag, dict)
            ]
            tags_cache[repo] = names
        newest = latest_tag(tags_cache[repo])
        pin["latest_tag"] = newest
        pin["on_latest"] = (pin["ref"] == newest) if newest else None
    else:
        pin["latest_tag"] = ""
        pin["on_latest"] = None
    if len(pins) > 1:
        pin["other_pins"] = [p["package"] for p in pins[1:]]
    return pin


_UNREAD_STATES = frozenset({"unavailable", "malformed"})


def _framework_field(package_read: dict[str, Any]) -> dict[str, Any]:
    facts: dict[str, Any] = framework_facts(package_read.get("data") or {})
    facts["state"] = package_read["state"]
    return facts


def _engine_pin_field(
    github: GitHub, package_read: dict[str, Any], tags_cache: dict[str, list[str]]
) -> dict[str, Any] | None:
    """The engine pin, ``None`` when there is none, or an unavailable marker."""
    if package_read["state"] in _UNREAD_STATES:
        return {
            "state": package_read["state"],
            "http_status": package_read.get("http_status"),
            "package": "",
            "spec": "",
            "kind": "",
            "ref": "",
            "repo": "",
            "latest_tag": "",
            "on_latest": None,
        }
    pin = _engine_pin(github, package_read.get("data"), tags_cache)
    if pin is not None:
        pin["state"] = "ok"
    return pin


def _unknown_deploy(descriptor_state: str) -> dict[str, Any]:
    return {
        "provider": "",
        "project": "",
        "project_source": "",
        "state": f"descriptor_{descriptor_state}",
        "deployed_sha": "",
        "dirty": None,
        "branch": "",
        "deployed_at": "",
        "matches_main": None,
        "compare": "",
        "behind_by": None,
    }


def refresh(
    *,
    config: Path | None = None,
    cache: Path | None = None,
    github: GitHub | None = None,
    cloudflare: Cloudflare | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Read every hub, child and site, then store one snapshot in the cache."""
    settings = load_config(config)
    gh = github or GitHub()
    cf = cloudflare or Cloudflare()
    started = now or datetime.now(timezone.utc)
    repo_cache: dict[str, dict[str, Any]] = {}
    tags_cache: dict[str, list[str]] = {}
    compare_cache: dict[tuple[str, str, str], dict[str, Any]] = {}
    hubs_out: list[dict[str, Any]] = []
    repos_out: list[dict[str, Any]] = []
    sites_out: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []

    for hub in settings["hubs"]:
        registry, registry_source = _hub_registry(gh, hub)
        hub_out: dict[str, Any] = {
            "name": hub["name"],
            "remote_full_name": hub["remote_full_name"],
            "registry_source": registry_source,
            "registry_ok": bool(registry.get("ok")),
            "registry_error": str(registry.get("error") or ""),
            "children": 0,
            "skipped": [],
            "cloudflare": {"connection": hub["cloudflare"], "state": "", "error": ""},
        }
        if not registry.get("ok"):
            errors.append({"hub": hub["name"], "error": hub_out["registry_error"]})
        hub_deploys: dict[str, Any] = {"state": "none", "projects": {}}
        if hub["cloudflare"]:
            token, account_id, cred_error = _cloudflare_credentials(
                hub["cloudflare"], hub["connect_checkout"], hub["name"]
            )
            if cred_error:
                hub_deploys["state"] = "error"
                hub_out["cloudflare"].update({"state": "error", "error": cred_error})
                errors.append({"hub": hub["name"], "error": cred_error})
            else:
                projects, message = cf.production_deployments(token, account_id)
                token = ""
                if not message:
                    hub_deploys = {"state": "ok", "projects": projects}
                    hub_out["cloudflare"].update({"state": "ok", "projects": len(projects)})
                else:
                    hub_deploys["state"] = "error"
                    hub_out["cloudflare"].update({"state": "error", "error": message})
                    errors.append({"hub": hub["name"], "error": message})
        for entry in registry.get("repos") or []:
            full = str(entry.get("remote_full_name") or "")
            if not full:
                hub_out["skipped"].append(
                    {"slug": entry.get("slug", ""), "reason": "no GitHub remote"}
                )
                continue
            if entry.get("lifecycle") in {"archived", "superseded"}:
                hub_out["skipped"].append(
                    {"slug": entry.get("slug", ""), "reason": str(entry.get("lifecycle"))}
                )
                continue
            hub_out["children"] += 1
            if full not in repo_cache:
                repo_cache[full] = read_repo(gh, full, started)
            facts = repo_cache[full]
            if not facts.get("readable") and entry.get("lifecycle") == "proposed":
                # A proposed repo may not exist yet; that is not a refresh error.
                hub_out["children"] -= 1
                hub_out["skipped"].append(
                    {"slug": entry.get("slug", ""), "reason": "proposed, not readable yet"}
                )
                continue
            for message in facts.get("errors") or []:
                errors.append({"hub": hub["name"], "repo": full, "error": str(message)})
            descriptor = facts.get("descriptor") or {}
            role = str(entry.get("role") or descriptor.get("role") or "")
            repos_out.append(
                {
                    "hub": hub["name"],
                    "repo": full,
                    "slug": entry.get("slug", ""),
                    "role": role,
                    "lifecycle": entry.get("lifecycle", ""),
                    "readable": bool(facts.get("readable")),
                    "default_branch": facts.get("default_branch", ""),
                    "main_sha": facts.get("main_sha", ""),
                    "main_committed_at": facts.get("main_committed_at", ""),
                    "ci": facts.get("ci") or {"state": "unknown", "total": 0, "failing": []},
                    "descriptor": {
                        "read_state": (facts.get("descriptor_read") or {}).get("state", ""),
                        "http_status": (facts.get("descriptor_read") or {}).get("http_status"),
                        "found": bool(descriptor.get("found")),
                        "ok": bool(descriptor.get("ok")),
                        "role": descriptor.get("role", ""),
                        "sites_errors": descriptor.get("sites_errors") or [],
                    },
                    "dependabot_alerts": facts.get("dependabot_alerts")
                    or {"state": "unavailable", "http_status": 0, "open": None, "by_severity": {}},
                    "dependabot_prs": facts.get("dependabot_prs")
                    or {
                        "state": "unavailable",
                        "http_status": 0,
                        "open": None,
                        "oldest_days": None,
                    },
                }
            )
            if not facts.get("readable"):
                continue
            descriptor_state = str((facts.get("descriptor_read") or {}).get("state") or "absent")
            sites_known = descriptor_state in {"ok", "absent"}
            sites: list[dict[str, Any] | None] = list(descriptor.get("sites") or []) or [None]
            for site in sites:
                site_dir = str((site or {}).get("dir") or ".")
                package_read = _site_package(facts, site_dir)
                if not sites_known:
                    # The descriptor could not be read, so the repo's sites and
                    # their dirs are unknown: report that, never root facts.
                    package_read = {
                        "path": topology.CHILD_REPO_RELATIVE_PATH.as_posix(),
                        "state": descriptor_state,
                        "http_status": (facts.get("descriptor_read") or {}).get("http_status"),
                        "data": None,
                    }
                provider, project, source, deploy_facts = _resolve_deploy(
                    site, entry, full.split("/", 1)[1], hub_deploys
                )
                row: dict[str, Any] = {
                    "hub": hub["name"],
                    "repo": full,
                    "site": (site or {}).get("slug", ""),
                    "site_dir": site_dir if site else "",
                    "display_name": (site or {}).get("display_name")
                    or entry.get("display_name", ""),
                    "role": role,
                    "lifecycle": (site or {}).get("lifecycle") or entry.get("lifecycle", ""),
                    "sites_state": "ok" if sites_known else descriptor_state,
                    "package": {
                        "path": package_read["path"] if package_read["state"] != "absent" else "",
                        "state": package_read["state"],
                        "http_status": package_read.get("http_status"),
                    },
                    "framework": _framework_field(package_read),
                    "engine_pin": _engine_pin_field(gh, package_read, tags_cache),
                    "default_branch": facts.get("default_branch", ""),
                    "main_sha": facts.get("main_sha", ""),
                    "main_committed_at": facts.get("main_committed_at", ""),
                    "ci": facts.get("ci") or {"state": "unknown", "total": 0, "failing": []},
                    "deploy": _deploy_block(
                        gh,
                        full,
                        str(facts.get("main_sha") or ""),
                        hub_deploys,
                        provider,
                        project,
                        source,
                        deploy_facts,
                        compare_cache,
                    )
                    if sites_known
                    else _unknown_deploy(descriptor_state),
                }
                row["flags"] = _flags(row)
                sites_out.append(row)
        hubs_out.append(hub_out)

    finished = datetime.now(timezone.utc) if now is None else started
    snapshot = {
        "schema": FLEET_SCHEMA,
        "refreshed_at": _iso(started),
        "finished_at": _iso(finished),
        "hubs": hubs_out,
        "repos": repos_out,
        "sites": sites_out,
        "refresh_errors": errors,
        "api_calls": {"github": gh.calls, "cloudflare": cf.calls},
    }
    target = cache or cache_path()
    _store(target, snapshot)
    return {
        "ok": not errors,
        "schema": FLEET_SCHEMA,
        "cache": str(target),
        "refreshed_at": snapshot["refreshed_at"],
        "summary": _summary(snapshot),
        "api_calls": snapshot["api_calls"],
        "errors": [_error_text(item) for item in errors],
        "warnings": [],
        "actions": ["mb fleet status"],
    }


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _error_text(item: dict[str, str]) -> str:
    where = item.get("repo") or item.get("hub") or ""
    return f"{where}: {item.get('error', '')}" if where else str(item.get("error", ""))


def _summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    sites = snapshot.get("sites") or []
    flag_counts: dict[str, int] = {}
    for row in sites:
        for flag in row.get("flags") or []:
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
    repos = snapshot.get("repos") or []
    alert_totals = dict.fromkeys(SEVERITIES, 0)
    alerts_unavailable = 0
    dependabot_prs = 0
    for repo in repos:
        alerts = repo.get("dependabot_alerts") or {}
        if alerts.get("state") != "ok":
            alerts_unavailable += 1
        for severity in SEVERITIES:
            alert_totals[severity] += int((alerts.get("by_severity") or {}).get(severity) or 0)
        dependabot_prs += int((repo.get("dependabot_prs") or {}).get("open") or 0)
    return {
        "hubs": len(snapshot.get("hubs") or []),
        "repos": len(repos),
        "sites": len(sites),
        "flags": flag_counts,
        "dependabot_alerts": alert_totals,
        "dependabot_alerts_unavailable": alerts_unavailable,
        "dependabot_prs": dependabot_prs,
        "refresh_errors": len(snapshot.get("refresh_errors") or []),
    }


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _connect_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE IF NOT EXISTS snapshots ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, refreshed_at TEXT NOT NULL, payload TEXT NOT NULL)"
    )
    return db


def _store(path: Path, snapshot: dict[str, Any]) -> None:
    with closing(_connect_db(path)) as db, db:
        db.execute(
            "INSERT INTO snapshots (refreshed_at, payload) VALUES (?, ?)",
            (snapshot["refreshed_at"], json.dumps(snapshot, sort_keys=True)),
        )
        db.execute(
            "DELETE FROM snapshots WHERE id NOT IN "
            "(SELECT id FROM snapshots ORDER BY id DESC LIMIT ?)",
            (KEEP_SNAPSHOTS,),
        )
    with suppress(OSError):
        path.chmod(0o600)


def _latest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with closing(_connect_db(path)) as db:
            row = db.execute("SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1").fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    try:
        payload = json.loads(row[0])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def status(*, cache: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Report the cached fleet snapshot. Reads only the cache, never the network."""
    target = cache or cache_path()
    current = now or datetime.now(timezone.utc)
    snapshot = _latest(target)
    if snapshot is None:
        return {
            "ok": False,
            "schema": FLEET_SCHEMA,
            "cache": str(target),
            "refreshed_at": "",
            "age_seconds": None,
            "hubs": [],
            "repos": [],
            "sites": [],
            "summary": {},
            "errors": ["no fleet snapshot yet"],
            "warnings": [],
            "actions": ["mb fleet refresh"],
        }
    refreshed = _parse_time(str(snapshot.get("refreshed_at") or ""))
    age = int((current - refreshed).total_seconds()) if refreshed else None
    sites = [dict(row) for row in snapshot.get("sites") or []]
    for row in sites:
        committed = _parse_time(str(row.get("main_committed_at") or ""))
        row["days_since_commit"] = (current - committed).days if committed else None
    repos = [dict(repo) for repo in snapshot.get("repos") or []]
    for repo in repos:
        committed = _parse_time(str(repo.get("main_committed_at") or ""))
        repo["days_since_commit"] = (current - committed).days if committed else None
    warnings = [_error_text(item) for item in snapshot.get("refresh_errors") or []]
    return {
        "ok": True,
        "schema": FLEET_SCHEMA,
        "cache": str(target),
        "refreshed_at": snapshot.get("refreshed_at", ""),
        "age_seconds": age,
        "hubs": snapshot.get("hubs") or [],
        "repos": repos,
        "sites": sites,
        "summary": _summary(snapshot),
        "errors": [],
        "warnings": warnings,
        "actions": ["mb fleet refresh"] if warnings or (age or 0) > 86400 else [],
    }


# ---------------------------------------------------------------------------
# Human rendering
# ---------------------------------------------------------------------------


def _short(sha: str) -> str:
    return sha[:7] if sha else "-"


def _age_text(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 3600:
        return f"{seconds // 60} min ago"
    if seconds < 86400:
        return f"{seconds // 3600} h ago"
    return f"{seconds // 86400} d ago"


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    widths = [max(len(title), *(len(row[i]) for row in rows)) for i, title in enumerate(header)]
    lines = ["  ".join(cell.ljust(widths[i]) for i, cell in enumerate(header)).rstrip()]
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip())
    return lines


def _fact_text(field: dict[str, Any], text: str) -> str:
    if field.get("state") in _UNREAD_STATES:
        return f"{field['state']} ({field.get('http_status') or 'error'})"
    return text.strip() or "-"


def _yes_no(value: Any) -> str:
    if value is None:
        return "-"
    return "yes" if value else "no"


def render_status(result: dict[str, Any]) -> None:
    if not result.get("refreshed_at"):
        print("mb fleet: no snapshot yet. Run `mb fleet refresh`.")
        return
    print(f"mb fleet  snapshot {result['refreshed_at']} ({_age_text(result.get('age_seconds'))})")
    print("")
    site_rows: list[list[str]] = []
    for row in result.get("sites") or []:
        framework = row.get("framework") or {}
        pin = row.get("engine_pin") or {}
        deploy = row.get("deploy") or {}
        behind = deploy.get("behind_by")
        site_rows.append(
            [
                str(row.get("hub") or ""),
                str(row.get("repo") or "").split("/", 1)[-1],
                str(row.get("site") or "-"),
                str(row.get("role") or "-"),
                _fact_text(framework, f"{framework.get('name')} {framework.get('version')}"),
                _fact_text(pin, str(pin.get("ref") or "")) if pin else "-",
                str((row.get("ci") or {}).get("state") or "-"),
                _short(str(row.get("main_sha") or "")),
                _short(str(deploy.get("deployed_sha") or ""))
                if deploy.get("state") == "ok"
                else str(deploy.get("state") or "-"),
                _yes_no(deploy.get("dirty")),
                str(behind) if isinstance(behind, int) else "-",
                str(
                    row.get("days_since_commit")
                    if row.get("days_since_commit") is not None
                    else "-"
                ),
            ]
        )
    header = [
        "hub", "repo", "site", "role", "framework", "engine", "ci", "main", "deployed",
        "dirty", "behind", "days",
    ]  # fmt: skip
    if site_rows:
        print("\n".join(_table(header, site_rows)))
    else:
        print("no repos found in the hub registries")
    repo_rows: list[list[str]] = []
    for repo in result.get("repos") or []:
        alerts = repo.get("dependabot_alerts") or {}
        prs = repo.get("dependabot_prs") or {}
        if alerts.get("state") == "ok":
            sev = alerts.get("by_severity") or {}
            alert_text = "/".join(str(sev.get(level, 0)) for level in SEVERITIES)
        else:
            alert_text = f"unavailable ({alerts.get('http_status') or 'error'})"
        pr_text = "-" if prs.get("open") is None else str(prs.get("open"))
        oldest = prs.get("oldest_days")
        repo_rows.append(
            [
                str(repo.get("hub") or ""),
                str(repo.get("repo") or ""),
                alert_text,
                pr_text,
                str(oldest) if oldest is not None else "-",
            ]
        )
    if repo_rows:
        print("")
        print("Dependabot (alerts critical/high/medium/low, open PRs, oldest PR days)")
        print("\n".join(_table(["hub", "repo", "alerts", "prs", "oldest"], repo_rows)))
    summary = result.get("summary") or {}
    flags = summary.get("flags") or {}
    if flags:
        print("")
        print("flags: " + ", ".join(f"{name} {count}" for name, count in sorted(flags.items())))
    for warning in result.get("warnings") or []:
        print(f"warning: {warning}")


def render_refresh(result: dict[str, Any]) -> None:
    summary = result.get("summary") or {}
    print(
        f"mb fleet refresh: {summary.get('hubs', 0)} hubs, {summary.get('repos', 0)} repos, "
        f"{summary.get('sites', 0)} site rows"
    )
    calls = result.get("api_calls") or {}
    print(f"api calls: github {calls.get('github', 0)}, cloudflare {calls.get('cloudflare', 0)}")
    for error in result.get("errors") or []:
        print(f"error: {error}")
    print("next: mb fleet status")


def render_hubs(result: dict[str, Any]) -> None:
    print(f"hub list: {result['config']}")
    rows = [
        [
            hub["name"],
            hub["remote_full_name"],
            "yes" if hub["checkout_present"] else ("missing" if hub["checkout"] else "-"),
            hub["cloudflare"] or "-",
        ]
        for hub in result.get("hubs") or []
    ]
    print("\n".join(_table(["name", "remote", "checkout", "cloudflare"], rows)))
