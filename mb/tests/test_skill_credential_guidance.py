from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILLS = REPO_ROOT / ".claude" / "skills"

# Setup no longer creates ~/.config/vip/env.sh. Only the config reference may
# name it, to say that an existing file keeps working.
LEGACY_NOTE = SKILLS / "mb-start" / "references" / "config-system.md"


def test_skills_do_not_send_credentials_to_env_sh() -> None:
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in sorted(SKILLS.rglob("*"))
        if path.is_file()
        and path != LEGACY_NOTE
        and path.suffix in {".md", ".py", ".sh"}
        and "env.sh" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_cloudflare_credential_writer_is_gone() -> None:
    assert not (SKILLS / "mb-site" / "scripts" / "setup_creds.sh").exists()
