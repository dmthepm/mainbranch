from __future__ import annotations

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
        str(path.relative_to(REPO_ROOT)) for path in _guidance_files(SKILLS) if _mentions_env_sh(path)
    ]
    assert offenders == []


def test_cloudflare_credential_writer_is_gone() -> None:
    assert not (SKILLS / "mb-site" / "scripts" / "setup_creds.sh").exists()


def test_guidance_does_not_tell_a_person_to_paste_a_key_through_token_stdin() -> None:
    # --token-stdin reads stdin with echo on, so a key typed or pasted at a
    # terminal shows and stays in scrollback. Omit it and the hidden prompt runs.
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for root in (SKILLS, EDUCATIONAL)
        for path in _guidance_files(root)
        if "--token-stdin" in path.read_text(encoding="utf-8")
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
