from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS = REPO_ROOT / ".claude" / "skills"
EDUCATIONAL = REPO_ROOT / ".claude" / "educational"

# Setup no longer creates ~/.config/vip/env.sh. Only the config reference may
# name it, and only on the lines that say an old file is legacy or still works.
LEGACY_NOTE = SKILLS / "mb-start" / "references" / "config-system.md"
LEGACY_LINE_MARKERS = ("Legacy", "no longer creates", "existing")


def _guidance_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix in {".md", ".py", ".sh"}
    ]


def _mentions_env_sh(path: Path) -> bool:
    for line in path.read_text(encoding="utf-8").splitlines():
        if "env.sh" not in line:
            continue
        if path == LEGACY_NOTE and any(marker in line for marker in LEGACY_LINE_MARKERS):
            continue
        return True
    return False


def test_skills_do_not_send_credentials_to_env_sh() -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _guidance_files(SKILLS)
        if _mentions_env_sh(path)
    ]
    assert offenders == []


def test_cloudflare_credential_writer_is_gone() -> None:
    assert not (SKILLS / "mb-site" / "scripts" / "setup_creds.sh").exists()


# A secure producer (`op read ... | mb connect <p> --token-stdin`) and a warning
# against pasting are fine. A line that sends a person to type or paste into an
# echoed --token-stdin is not. Reviewed exceptions go here, as (path, reason).
TOKEN_STDIN_REVIEWED: list[tuple[str, str]] = []
TOKEN_STDIN_SAFE_MARKERS = (
    "op read",
    "pass show",
    "secret-tool",
    "never",
    "do not",
    "don't",
    "avoid",
)


def _is_unsafe_token_stdin(line: str) -> bool:
    return "--token-stdin" in line and not any(m in line.lower() for m in TOKEN_STDIN_SAFE_MARKERS)


def _unsafe_token_stdin_lines(path: Path) -> list[str]:
    if str(path.relative_to(REPO_ROOT)) in {name for name, _ in TOKEN_STDIN_REVIEWED}:
        return []
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if _is_unsafe_token_stdin(line)
    ]


def test_guidance_does_not_tell_a_person_to_paste_a_key_through_token_stdin() -> None:
    # --token-stdin reads stdin with echo on, so a key typed or pasted at a
    # terminal shows and stays in scrollback. Omit it and the hidden prompt runs.
    offenders = {
        str(path.relative_to(REPO_ROOT)): lines
        for root in (SKILLS, EDUCATIONAL)
        for path in _guidance_files(root)
        if (lines := _unsafe_token_stdin_lines(path))
    }
    assert offenders == {}


def test_token_stdin_guard_allows_a_secure_producer_and_a_warning() -> None:
    assert _is_unsafe_token_stdin("mb connect cloudflare --token-stdin")
    assert not _is_unsafe_token_stdin("op read op://vault/cf | mb connect cloudflare --token-stdin")
    assert not _is_unsafe_token_stdin("Never paste a key into --token-stdin at a terminal.")


# One standard sentence, reused wherever an agent is told to connect a provider.
HANDOFF = (
    "Credential entry happens in the owner's own terminal, because the hidden prompt "
    "needs a real terminal; the agent hands off, then resumes its readiness check."
)
CONNECT_SUBCOMMANDS = (
    "exec|test|token|status|doctor|plan|list|identity|hygiene|repair|rotate|audit|"
    "remove|hydrate|policy|rebind|google|<id>"
)
CONNECT_A_PROVIDER = re.compile(rf"mb connect (?!(?:{CONNECT_SUBCOMMANDS})(?![\w-]))[a-z<][\w<>-]*")
# Index tables and "do not imply" notes name `mb connect` without telling anyone to run it.
HANDOFF_EXEMPT = {
    ".claude/skills/mb-help/SKILL.md",
    ".claude/skills/mb-help/references/cli-surfaces.md",
    ".claude/skills/mb-start/references/cli-surfaces.md",
    ".claude/skills/mb-think/references/research-depth-ladder.md",
    ".claude/skills/mb-think/references/tool-detection.md",
    ".claude/skills/mb-think/references/tool-surfacing.md",
    # Defines OWNER_HANDOFF; a test below checks it equals HANDOFF.
    ".claude/skills/mb-site/scripts/_envelope.py",
}


def test_every_connect_instruction_hands_credential_entry_to_the_owner() -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for root in (SKILLS, EDUCATIONAL)
        for path in _guidance_files(root)
        if str(path.relative_to(REPO_ROOT)) not in HANDOFF_EXEMPT
        and CONNECT_A_PROVIDER.search(text := path.read_text(encoding="utf-8"))
        and HANDOFF not in " ".join(text.split())
    ]
    assert offenders == []


def test_cloudflare_exec_hints_keep_the_account_id() -> None:
    # `mb connect exec` drops every variable outside its allowlist, so a bare
    # CF_ACCOUNT_ID=<id> in front of it never reaches the script.
    scripts = SKILLS / "mb-site" / "scripts"
    for name in ("dns.py", "verify_live.py"):
        text = (scripts / name).read_text(encoding="utf-8")
        assert "--keep-env CF_ACCOUNT_ID" in text, name
    verify = (scripts / "verify_live.py").read_text(encoding="utf-8")
    assert "--keep-env VERIFY_LIVE_CF_ZONE" in verify


def test_zone_retry_command_carries_account_id_and_both_keep_env_flags() -> None:
    # Check the one command, not the whole file: a retry that drops the account
    # id fails check_cf_auth before it ever reaches the zone lookup.
    text = (SKILLS / "mb-site" / "scripts" / "verify_live.py").read_text(encoding="utf-8")
    retry = [line for line in text.splitlines() if "VERIFY_LIVE_CF_ZONE=<" in line]
    assert len(retry) == 1
    for needle in ("CF_ACCOUNT_ID=<", "--keep-env CF_ACCOUNT_ID", "--keep-env VERIFY_LIVE_CF_ZONE"):
        assert needle in retry[0], needle


MB_SITE_SCRIPTS = SKILLS / "mb-site" / "scripts"
CREDENTIAL_PRINTERS = ("dns.py", "pages.py", "stripe.py", "verify_live.py")


def _missing_credential_messages(path: Path) -> list[ast.expr]:
    # The `suggestion=` text an atom returns, or the line verify_live prints,
    # when it tells someone to store a credential with `mb connect`.
    found: list[ast.expr] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.keyword) and node.arg == "suggestion":
            found.append(node.value)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_info"
            and node.args
        ):
            found.append(node.args[0])
    return [
        expr for expr in found if "mb connect" in ast.unparse(expr) and "tore" in ast.unparse(expr)
    ]


def test_runtime_missing_credential_messages_carry_the_owner_handoff() -> None:
    # The module docstring is never printed; the message the agent reads is.
    sys.path.insert(0, str(MB_SITE_SCRIPTS))
    try:
        from _envelope import OWNER_HANDOFF  # type: ignore[import-not-found]
    finally:
        sys.path.remove(str(MB_SITE_SCRIPTS))
    assert OWNER_HANDOFF == HANDOFF

    checked = 0
    offenders = []
    for name in CREDENTIAL_PRINTERS:
        for expr in _missing_credential_messages(MB_SITE_SCRIPTS / name):
            checked += 1
            if not any(isinstance(n, ast.Name) and n.id == "OWNER_HANDOFF" for n in ast.walk(expr)):
                offenders.append(f"{name}:{expr.lineno}")
    assert checked >= 9
    assert offenders == []
