"""mb agent check, slice 1: is the agents.json policy, and every file it names, safe to trust?

Read only. This module launches nothing, writes no state, takes no locks and sends no
signals. It says the policy is valid or lists what is wrong; it never says an agent is
verified. Every path is walked one component at a time through directory descriptors with
``O_NOFOLLOW``, and each directory entered is checked on the descriptor actually used:
owned by root or the caller, and not group or world writable (a sticky bit does not excuse
world write). Symlinks are followed only above the places the policy says must be plain.
"""

from __future__ import annotations

import json
import os
import pwd
import re
import stat
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mb import roles

STORE_PARTS = (".local", "state", "mainbranch", "agents")
SHARED_CARDS_PARTS = (".local", "share", "agent-role-cards")
POLICY_FILE = "agents.json"
MAX_POLICY_BYTES = 65_536
MAX_ROWS = 50
MAX_STRING = 200
MAX_LINKS = 40
DEFAULT_PATH = ("/usr/local/bin", "/usr/bin", "/bin")
DEFAULT = "default"

NAME_RE = re.compile(r"^[a-z0-9-]{1,40}$")
MODEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
RUNTIMES = ("claude", "codex")
# Fixed in code. Confirmed against the installed runtimes in slices 2 and 4, not here.
EFFORT = {
    "claude": ("low", "medium", "high", "xhigh", "max"),
    "codex": ("minimal", "low", "medium", "high", "xhigh"),
}
OPTIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "claude": {"--permission-mode": ("default", "acceptEdits", "plan", "bypassPermissions")},
    "codex": {"--sandbox": ("read-only", "workspace-write", "danger-full-access")},
}
# Allowed, and never an error, but "valid" must not be read as "safe": check says so.
MOST_PERMISSIVE = {("--permission-mode", "bypassPermissions"), ("--sandbox", "danger-full-access")}
TOP_KEYS = {"version", "path", "profiles", "agents"}
ROW_KEYS = {
    "name",
    "runtime",
    "cwd",
    "role",
    "profile",
    "model",
    "effort",
    "options",
    "start_file",
    "declared_work",
}
ROW_REQUIRED = ("name", "runtime", "cwd", "role", "profile", "model")
WORK_KEYS = {"name", "kind", "schedule", "prompt_file"}
WORK_KINDS = ("cron", "background")


@dataclass(frozen=True)
class Host:
    """Who is asking and where. ``floor`` is the highest directory whose ancestors are judged."""

    home: str
    uid: int
    floor: str = "/"
    default_path: tuple[str, ...] = DEFAULT_PATH

    @classmethod
    def local(cls) -> Host:
        uid = os.getuid()
        return cls(home=pwd.getpwuid(uid).pw_dir, uid=uid)


@dataclass(frozen=True)
class Problem:
    code: str
    where: str
    detail: str

    def text(self) -> str:
        return f"{self.code}: {roles.printable(self.where, 120)}: {self.detail}"


@dataclass
class Report:
    problems: list[Problem] = field(default_factory=list)
    agents: int = 0
    path: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


class _Unsafe(Exception):
    """A path failed a trust rule. The message says which."""


@dataclass(frozen=True)
class _Found:
    real: str
    st: os.stat_result


def _parts(path: str) -> list[str]:
    return [p for p in path.split("/") if p and p != "."]


def _within(real: list[str], base: list[str]) -> bool:
    return real[: len(base)] == base


def _dir_problem(st: os.stat_result, uid: int) -> str | None:
    if not stat.S_ISDIR(st.st_mode):
        return "not a directory"
    if st.st_uid not in (0, uid):
        return "directory is owned by someone else"
    if st.st_mode & 0o022:
        return "directory is group or world writable"
    return None


def _walk(path: str, host: Host, *, plain_below: str | None = None) -> _Found | None:
    """Resolve absolute ``path`` safely; None when missing. Every directory entered is checked.

    Links are followed through directories that passed the check. Below ``plain_below`` (a
    real path) any link is refused, so a file the policy names cannot be a redirect.
    """
    if not path.startswith("/") or ".." in path.split("/"):
        raise _Unsafe("path must be absolute with no '..'")
    floor = _parts(host.floor)
    plain = _parts(plain_below) if plain_below else None
    pending = deque(_parts(path))
    root_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    fds = [root_fd]
    real: list[str] = []
    links = 0

    def enter(fd: int) -> None:
        # Strict ancestors of the floor are outside what the caller vouches for.
        if len(real) >= len(floor) or real != floor[: len(real)]:
            problem = _dir_problem(os.fstat(fd), host.uid)
            if problem:
                raise _Unsafe(f"{problem}: /{'/'.join(real)}")

    try:
        enter(root_fd)
        while pending:
            name = pending.popleft()
            try:
                st = os.stat(name, dir_fd=fds[-1], follow_symlinks=False)
            except FileNotFoundError:
                return None
            except NotADirectoryError:
                raise _Unsafe("a parent is not a directory") from None
            if stat.S_ISLNK(st.st_mode):
                if plain is not None and _within(real, plain):
                    raise _Unsafe(f"symlink not allowed: {name}")
                links += 1
                if links > MAX_LINKS:
                    raise _Unsafe("too many symlinks")
                target = os.readlink(name, dir_fd=fds[-1])
                if ".." in target.split("/"):
                    raise _Unsafe(f"symlink target has '..': {name}")
                if target.startswith("/"):
                    for fd in fds[1:]:
                        os.close(fd)
                    fds, real = [root_fd], []
                pending.extendleft(reversed(_parts(target)))
                continue
            real.append(name)
            if not pending and not stat.S_ISDIR(st.st_mode):
                return _Found("/" + "/".join(real), st)
            if not stat.S_ISDIR(st.st_mode):
                raise _Unsafe(f"not a directory: {name}")
            try:
                fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fds[-1])
            except OSError as exc:
                raise _Unsafe(f"cannot open directory {name}: {exc.strerror}") from None
            fds.append(fd)
            opened = os.fstat(fd)
            if (opened.st_dev, opened.st_ino) != (st.st_dev, st.st_ino):
                raise _Unsafe(f"directory changed while checking: {name}")
            enter(fd)
        return _Found("/" + "/".join(real), os.fstat(fds[-1]))
    except OSError as exc:
        raise _Unsafe(f"cannot check path: {exc.strerror}") from None
    finally:
        for fd in fds:
            os.close(fd)


def _read_file(real: str, host: Host, limit: int, *, caller_only: bool) -> bytes:
    """Read a regular file by its link-free ``real`` path, checking the object actually opened."""
    parts = _parts(real)
    fds: list[int] = []
    try:
        fds.append(os.open("/", os.O_RDONLY | os.O_DIRECTORY))
        for name in parts[:-1]:
            fds.append(os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fds[-1]))
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fds[-1])
        fds.append(fd)
        st = os.fstat(fd)
        problem = _file_problem(st, host.uid, caller_only=caller_only)
        if problem:
            raise _Unsafe(problem)
        data = b""
        while len(data) <= limit:
            chunk = os.read(fd, limit + 1 - len(data))
            if not chunk:
                break
            data += chunk
        return data
    except OSError as exc:
        raise _Unsafe(f"cannot read file: {exc.strerror}") from None
    finally:
        for fd in fds:
            os.close(fd)


def _file_problem(st: os.stat_result, uid: int, *, caller_only: bool) -> str | None:
    if not stat.S_ISREG(st.st_mode):
        return "not a regular file"
    if st.st_uid not in ((uid,) if caller_only else (0, uid)):
        return "file is owned by someone else"
    if st.st_mode & 0o022:
        return "file is group or world writable"
    return None


# --- schema -------------------------------------------------------------------------


class _Collect:
    def __init__(self, report: Report) -> None:
        self.report = report

    def add(self, code: str, where: str, detail: str) -> None:
        self.report.problems.append(Problem(code, where, detail))

    def schema(self, where: str, detail: str) -> None:
        self.add("schema", where, detail)

    def unsafe(self, path: str, exc: _Unsafe) -> None:
        self.add("unsafe-path", path, str(exc))


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key")
        out[key] = value
    return out


def _refuse_constant(_: str) -> Any:
    raise ValueError("not JSON")


def _bad_strings(value: Any, where: str) -> str | None:
    """The location of the first overlong or control-bearing string, else None."""
    if isinstance(value, str):
        return where if len(value) > MAX_STRING or roles.has_control(value) else None
    if isinstance(value, list):
        for i, item in enumerate(value):
            hit = _bad_strings(item, f"{where}[{i}]")
            if hit:
                return hit
    elif isinstance(value, dict):
        for key, item in value.items():
            hit = _bad_strings(key, f"{where}.<key>") or _bad_strings(item, f"{where}.{key}")
            if hit:
                return hit
    return None


def _norm_abs(value: Any, *, colon_ok: bool = True) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("/")
        and os.path.normpath(value) == value
        and (colon_ok or ":" not in value)
    )


def _relative_ok(value: Any) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith(("/", "~", "\\"))
        and not roles.has_control(value)
        and os.path.normpath(value) == value
        and ".." not in value.split("/")
    )


def _loc(i: int, key: str | None = None) -> str:
    return f"agents[{i}]" + (f".{key}" if key else "")


def _row_schema(c: _Collect, i: int, row: Any, profiles: dict[str, Any]) -> bool:
    """Check one row's shape. True when the row is sound enough for filesystem checks."""
    if not isinstance(row, dict):
        c.schema(_loc(i), "row must be an object")
        return False
    before = len(c.report.problems)
    for key in sorted(set(row) - ROW_KEYS):
        c.schema(_loc(i), f"unknown field: {roles.printable(key, 40)}")
    for key in ROW_REQUIRED:
        if key not in row:
            c.schema(_loc(i), f"missing field: {key}")
    name, role, runtime = row.get("name"), row.get("role"), row.get("runtime")
    for key, value in (("name", name), ("role", role)):
        if key in row and not (isinstance(value, str) and NAME_RE.fullmatch(value)):
            c.schema(_loc(i, key), "must be lowercase letters, digits and hyphens (1-40)")
    if "runtime" in row and runtime not in RUNTIMES:
        c.schema(_loc(i, "runtime"), "must be claude or codex")
    model = row.get("model")
    if "model" in row and not (isinstance(model, str) and MODEL_RE.fullmatch(model)):
        c.schema(_loc(i, "model"), "must be letters, digits, '.', '_' or '-' (1-64)")
    if "cwd" in row and not _norm_abs(row["cwd"]):
        c.add("cwd", _loc(i, "cwd"), "must be a normalized absolute path")
    profile = row.get("profile")
    if "profile" in row:
        if not isinstance(profile, str):
            c.schema(_loc(i, "profile"), "must be text")
        elif profile != DEFAULT and profile not in profiles:
            c.add("profile", _loc(i, "profile"), "unknown profile")
        elif profile != DEFAULT and runtime in RUNTIMES and runtime not in profiles[profile]:
            c.add("profile", _loc(i, "profile"), f"profile has no {runtime} directory")
    if "effort" in row and runtime in RUNTIMES and row["effort"] not in EFFORT[runtime]:
        c.schema(_loc(i, "effort"), f"must be one of {', '.join(EFFORT[runtime])}")
    if "options" in row:
        _options(c, i, row["options"], runtime)
    if "start_file" in row and not _relative_ok(row["start_file"]):
        c.schema(_loc(i, "start_file"), "must be a relative path inside cwd, no '..'")
    if "declared_work" in row:
        _declared_work(c, i, row["declared_work"])
    return len(c.report.problems) == before


def _options(c: _Collect, i: int, options: Any, runtime: Any) -> None:
    if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
        c.schema(_loc(i, "options"), "must be a list of text")
        return
    allowed = OPTIONS.get(runtime if isinstance(runtime, str) else "", {})
    seen: set[str] = set()
    for option in options:
        flag, _, value = option.partition(" ")
        if flag not in allowed or value not in allowed[flag]:
            c.schema(_loc(i, "options"), f"not allowed: {roles.printable(option, 60)}")
        elif flag in seen:
            c.schema(_loc(i, "options"), f"repeated: {flag}")
        seen.add(flag)


def _declared_work(c: _Collect, i: int, work: Any) -> None:
    where = _loc(i, "declared_work")
    if not isinstance(work, list):
        c.schema(where, "must be a list")
        return
    for entry in work:
        ok = (
            isinstance(entry, dict)
            and set(entry) <= WORK_KEYS
            and isinstance(entry.get("name"), str)
            and NAME_RE.fullmatch(entry["name"]) is not None
            and entry.get("kind") in WORK_KINDS
            and isinstance(entry.get("schedule", ""), str)
            and (entry.get("prompt_file") is None or _relative_ok(entry["prompt_file"]))
        )
        if not ok:
            c.schema(
                where,
                "each entry needs name, kind (cron or background); optional schedule, prompt_file",
            )
            return


# --- filesystem ---------------------------------------------------------------------


def _check_dir(
    c: _Collect,
    host: Host,
    path: str,
    *,
    owner_only: bool,
    plain_below: str | None,
    code: str = "unsafe-path",
    must_exist: bool = True,
) -> _Found | None:
    try:
        found = _walk(path, host, plain_below=plain_below)
    except _Unsafe as exc:
        c.unsafe(path, exc)
        return None
    if found is None:
        if must_exist:
            c.add(code, path, "does not exist")
        return None
    problem = _dir_problem(found.st, host.uid)
    if problem is None and owner_only and found.st.st_uid != host.uid:
        problem = "directory is not owned by the caller"
    if problem is None and plain_below is not None and found.real != path:
        problem = "is not its own real path"
    if problem:
        c.unsafe(path, _Unsafe(problem))
        return None
    return found


def _check_card(
    c: _Collect, host: Host, i: int, row: dict[str, Any], cwd: str, home: str, report: Report
) -> None:
    role, runtime = row["role"], row["runtime"]
    if os.path.lexists(f"{cwd}/core/roles"):
        folder = f"{cwd}/core/roles"
    else:
        folder = "/".join([home, *SHARED_CARDS_PARTS])
    path = f"{folder}/{role}.md"
    try:
        found = _walk(path, host, plain_below=home)
    except _Unsafe as exc:
        c.unsafe(path, exc)
        return
    if found is None:
        if runtime == "claude":
            c.add("card", _loc(i, "role"), "no role card at the fixed location")
        else:
            report.notes.append(f"{row['name']}: card: unverified(no-adapter)")
        return
    try:
        raw = _read_file(found.real, host, roles.MAX_CARD_BYTES, caller_only=False)
    except _Unsafe as exc:
        c.unsafe(path, exc)
        return
    if len(raw) > roles.MAX_CARD_BYTES:
        c.add("card", _loc(i, "role"), f"card is larger than {roles.MAX_CARD_BYTES} bytes")
        return
    try:
        text = raw.decode()
    except UnicodeDecodeError:
        c.add("card", _loc(i, "role"), "card is not UTF-8 text")
        return
    for error in roles.card_text_errors(text, role, Path(cwd)):
        c.add("card", _loc(i, "role"), error)


def _check_default_profile(
    c: _Collect, host: Host, home: str, runtime: str, report: Report
) -> None:
    names = [".claude", ".claude.json"] if runtime == "claude" else [".codex"]
    for name in names:
        path = f"{home}/{name}"
        try:
            found = _walk(path, host, plain_below=home)
        except _Unsafe as exc:
            c.unsafe(path, exc)
            continue
        if found is None:
            report.notes.append(f"default {runtime} profile: {name} absent")
        elif name.endswith(".json"):
            problem = _file_problem(found.st, host.uid, caller_only=True)
            if problem:
                c.unsafe(path, _Unsafe(problem))
        else:
            _check_dir(c, host, path, owner_only=True, plain_below=home)


def _check_start_file(c: _Collect, host: Host, i: int, cwd: str, home: str, rel: str) -> None:
    path = f"{cwd}/{rel}"
    try:
        found = _walk(path, host, plain_below=home)
    except _Unsafe as exc:
        c.unsafe(path, exc)
        return
    if found is None:
        c.add("start_file", _loc(i, "start_file"), "does not exist")
        return
    problem = _file_problem(found.st, host.uid, caller_only=True)
    if problem:
        c.unsafe(path, _Unsafe(problem))


def _check_path_list(c: _Collect, host: Host, listed: Any, report: Report) -> None:
    if listed is None:
        entries = list(host.default_path)
    elif not isinstance(listed, list) or not listed:
        c.schema("path", "must be a non-empty list of absolute directories")
        return
    else:
        entries = listed
    for entry in entries:
        if not _norm_abs(entry, colon_ok=False):
            c.schema(
                "path", f"not a normalized absolute directory: {roles.printable(str(entry), 60)}"
            )
            continue
        try:
            found = _walk(entry, host)
        except _Unsafe as exc:
            c.unsafe(entry, exc)
            continue
        if found is None:
            report.skipped.append(entry)
            continue
        problem = _dir_problem(found.st, host.uid)
        if problem:
            c.unsafe(entry, _Unsafe(problem))
        else:
            report.path.append(entry)


def _check_profiles(c: _Collect, host: Host, home: str, profiles: Any) -> dict[str, Any]:
    """Validate the named profiles. Returns the usable ``{name: {runtime: dir}}`` map."""
    if profiles is None:
        return {}
    if not isinstance(profiles, dict):
        c.schema("profiles", "must be an object")
        return {}
    clean: dict[str, Any] = {}
    for name, entry in profiles.items():
        where = f"profiles.{roles.printable(name, 40)}"
        if name == DEFAULT or not NAME_RE.fullmatch(name):
            c.add(
                "profile", where, "name must be lowercase letters, digits, hyphens; not 'default'"
            )
            continue
        if not isinstance(entry, dict) or not entry or set(entry) - set(RUNTIMES):
            c.add("profile", where, "must map claude and/or codex to a directory")
            continue
        clean[name] = {}
        for runtime, directory in entry.items():
            if not _norm_abs(directory):
                c.add("profile", f"{where}.{runtime}", "must be a normalized absolute path")
                continue
            if _check_dir(c, host, directory, owner_only=True, plain_below="/", code="profile"):
                clean[name][runtime] = directory
    return clean


# --- entry point --------------------------------------------------------------------


def check(host: Host, name: str | None = None) -> Report:
    """Validate the policy and the files it names. Never changes anything."""
    report = Report()
    c = _Collect(report)
    if host.uid == 0:
        c.add("root", "uid", "run as the agent's own user, never root")
        return report
    home_found = _check_dir(c, host, host.home, owner_only=True, plain_below=None)
    if home_found is None:
        return report
    home = home_found.real
    store = "/".join([home, *STORE_PARTS])
    if _check_dir(c, host, store, owner_only=True, plain_below=home, must_exist=False) is None:
        if not report.problems:
            c.add("policy-missing", store, "no agents directory")
        return report
    policy_path = f"{store}/{POLICY_FILE}"
    try:
        found = _walk(policy_path, host, plain_below=home)
        if found is None:
            c.add("policy-missing", policy_path, "no agents.json")
            return report
        raw = _read_file(found.real, host, MAX_POLICY_BYTES, caller_only=True)
    except _Unsafe as exc:
        c.unsafe(policy_path, exc)
        return report
    if len(raw) > MAX_POLICY_BYTES:
        c.schema(POLICY_FILE, f"larger than {MAX_POLICY_BYTES} bytes")
        return report
    try:
        policy = json.loads(
            raw.decode(), object_pairs_hook=_no_duplicates, parse_constant=_refuse_constant
        )
    except (ValueError, UnicodeDecodeError, RecursionError):
        c.schema(POLICY_FILE, "not valid JSON, or has a repeated key")
        return report
    if not isinstance(policy, dict):
        c.schema(POLICY_FILE, "must be a JSON object")
        return report
    hit = _bad_strings(policy, POLICY_FILE)
    if hit:
        c.schema(hit, f"text over {MAX_STRING} characters or with control characters")
        return report
    for key in sorted(set(policy) - TOP_KEYS):
        c.schema(POLICY_FILE, f"unknown field: {roles.printable(key, 40)}")
    if policy.get("version") != 1 or isinstance(policy.get("version"), bool):
        c.schema("version", "must be 1")
    rows = policy.get("agents")
    if not isinstance(rows, list) or len(rows) > MAX_ROWS:
        c.schema("agents", f"must be a list of at most {MAX_ROWS} rows")
        rows = []
    _check_path_list(c, host, policy.get("path"), report)
    profiles = _check_profiles(c, host, home, policy.get("profiles"))
    names: set[str] = set()
    default_seen: set[str] = set()
    for i, row in enumerate(rows):
        sound = _row_schema(c, i, row, profiles)
        if isinstance(row, dict) and isinstance(row.get("name"), str):
            if row["name"] in names:
                c.schema(_loc(i, "name"), "repeats an earlier name")
            names.add(row["name"])
        if not sound:
            continue
        for option in row.get("options", []):
            if tuple(option.split(" ", 1)) in MOST_PERMISSIVE:
                report.warnings.append(
                    f"{row['name']}: {option} is the most permissive mode; allowed, not safe"
                )
        cwd = row["cwd"]
        if not cwd.startswith(home + "/"):
            c.add("cwd", _loc(i, "cwd"), "must be under HOME, written as its real path")
            continue
        if _check_dir(c, host, cwd, owner_only=True, plain_below=home, code="cwd"):
            _check_card(c, host, i, row, cwd, home, report)
            if "start_file" in row:
                _check_start_file(c, host, i, cwd, home, row["start_file"])
        if row["profile"] == DEFAULT and row["runtime"] not in default_seen:
            default_seen.add(row["runtime"])
            _check_default_profile(c, host, home, row["runtime"], report)
    report.agents = len(rows)
    if name is not None and name not in names:
        c.add("unknown-agent", name, "no row with that name")
    return report


def human_report(report: Report) -> str:
    """Success says only that the policy is valid. It claims nothing about any agent."""
    notes = [f"  note: {w}" for w in report.warnings]
    if report.ok:
        return "\n".join(["Policy valid.", *notes])
    return "\n".join(["Policy not valid.", *[f"  {p.text()}" for p in report.problems], *notes])
