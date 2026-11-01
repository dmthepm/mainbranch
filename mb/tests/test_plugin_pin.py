"""Release plugin pinning: the pin script and the check that guards a pinned marketplace."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "plugin_pin.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("plugin_pin", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["plugin_pin"] = module
    spec.loader.exec_module(module)
    return module


pp = _load()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _write(
    root: Path, version: str, *, plugin_version: str | None = None, source: object = "./"
) -> None:
    (root / ".claude-plugin").mkdir(exist_ok=True)
    (root / pp.PLUGIN).write_text(
        json.dumps({"name": "mainbranch", "version": plugin_version or version}), encoding="utf-8"
    )
    (root / pp.MARKETPLACE).write_text(
        json.dumps(
            {
                "name": "mainbranch",
                "metadata": {"version": version},
                "plugins": [{"name": "mainbranch", "source": source}],
            }
        ),
        encoding="utf-8",
    )


def _release(root: Path, version: str, *, plugin_version: str | None = None) -> str:
    _write(root, version, plugin_version=plugin_version)
    _git(root, "add", "-A")
    _git(root, "commit", "-m", f"release {version}")
    _git(root, "tag", f"oe-v{version}")
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    return root


def _pin_source(sha: str, **overrides: str) -> dict[str, str]:
    source = {"source": "url", "url": pp.PIN_URL, "sha": sha}
    source.update(overrides)
    return source


def _set_source(root: Path, source: object) -> None:
    path = root / pp.MARKETPLACE
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["plugins"][0]["source"] = source
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_unpinned_source_passes(repo: Path) -> None:
    _release(repo, "0.6.17")
    assert pp.check(repo) == []


def test_pin_writes_full_sha_and_https_url(repo: Path) -> None:
    sha = _release(repo, "0.6.17")
    assert pp.pin(repo, "oe-v0.6.17") == sha
    source = json.loads((repo / pp.MARKETPLACE).read_text(encoding="utf-8"))["plugins"][0]["source"]
    assert source == {
        "source": "url",
        "url": "https://github.com/dmthepm/mainbranch.git",
        "sha": sha,
    }
    assert pp.check(repo) == []


def test_pin_refuses_tag_whose_commit_declares_another_version(repo: Path) -> None:
    _release(repo, "0.6.16")
    _write(repo, "0.6.16")
    _git(repo, "tag", "oe-v0.6.17")  # tagged before the version bump landed
    with pytest.raises(ValueError, match="declares plugin.json 0.6.16"):
        pp.pin(repo, "oe-v0.6.17")


def test_pin_refuses_when_plugin_and_marketplace_disagree(repo: Path) -> None:
    _release(repo, "0.6.17", plugin_version="0.6.16")
    with pytest.raises(ValueError, match="refusing to pin"):
        pp.pin(repo, "oe-v0.6.17")


def test_pin_refuses_unknown_tag(repo: Path) -> None:
    _release(repo, "0.6.17")
    with pytest.raises(ValueError):
        pp.pin(repo, "oe-v9.9.9")


def test_pin_refuses_a_branch_name_that_is_not_a_tag(repo: Path) -> None:
    _release(repo, "0.6.16")
    _write(repo, "0.6.17")
    _git(repo, "commit", "-am", "bump, not yet tagged")
    _git(repo, "branch", "oe-v0.6.17")  # declares 0.6.17 but is a branch, not a release tag
    with pytest.raises(ValueError):
        pp.pin(repo, "oe-v0.6.17")


def test_check_passes_when_versions_are_bumped_but_pin_names_previous_release(repo: Path) -> None:
    old = _release(repo, "0.6.17")
    _write(repo, "0.6.18", source=_pin_source(old))  # release commit: bumped, pin still old
    assert pp.check(repo) == []


def test_check_passes_when_pin_names_this_trees_release(repo: Path) -> None:
    sha = _release(repo, "0.6.17")
    _set_source(repo, _pin_source(sha))
    assert pp.check(repo) == []


def test_check_fails_when_pinned_commit_is_newer_than_tree(repo: Path) -> None:
    _release(repo, "0.6.17")
    new = _release(repo, "0.6.18")
    _write(repo, "0.6.17", source=_pin_source(new))
    assert any("newer than" in p for p in pp.check(repo))


def test_check_fails_when_pinned_commit_declares_mismatched_versions(repo: Path) -> None:
    bad = _release(repo, "0.6.17", plugin_version="0.6.16")
    _write(repo, "0.6.17", source=_pin_source(bad))
    assert any("plugin.json 0.6.16 but marketplace 0.6.17" in p for p in pp.check(repo))


def test_check_fails_on_short_sha(repo: Path) -> None:
    sha = _release(repo, "0.6.17")
    _set_source(repo, _pin_source(sha[:12]))
    assert any("40-character" in p for p in pp.check(repo))


def test_check_fails_on_uppercase_sha(repo: Path) -> None:
    sha = _release(repo, "0.6.17")
    _set_source(repo, _pin_source(sha.upper()))
    assert any("40-character" in p for p in pp.check(repo))


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/dmthepm/mainbranch.git",
        "git@github.com:dmthepm/mainbranch.git",
        "https://github.com/noontide-co/mainbranch.git",
        "https://github.com/someone-else/mainbranch.git",
        "https://github.com/dmthepm/mainbranch",
    ],
)
def test_check_fails_on_non_https_or_wrong_repo(repo: Path, url: str) -> None:
    sha = _release(repo, "0.6.17")
    _set_source(repo, _pin_source(sha, url=url))
    assert any("pin url must be" in p for p in pp.check(repo))


def test_check_fails_on_github_source_shape(repo: Path) -> None:
    sha = _release(repo, "0.6.17")
    _set_source(repo, {"source": "github", "repo": "dmthepm/mainbranch", "sha": sha})
    assert any("must be './' or a url pin" in p for p in pp.check(repo))


def test_check_fails_when_pinned_commit_is_not_available(repo: Path) -> None:
    _release(repo, "0.6.17")
    _set_source(repo, _pin_source("0" * 40))
    assert any("cannot read the pinned commit" in p for p in pp.check(repo))
    assert pp.check(repo, offline=True) == []


def test_candidate_export_resets_source_to_local(repo: Path, tmp_path: Path) -> None:
    old = _release(repo, "0.6.17")
    _write(repo, "0.6.18", source=_pin_source(old))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "bump")
    dest = tmp_path / "candidate"
    pp.candidate(repo, dest)
    exported = json.loads((dest / pp.MARKETPLACE).read_text(encoding="utf-8"))
    assert exported["plugins"][0]["source"] == "./"
    assert exported["metadata"]["version"] == "0.6.18"
    with pytest.raises(ValueError, match="not empty"):
        pp.candidate(repo, dest)


def test_cli_exit_codes(repo: Path) -> None:
    sha = _release(repo, "0.6.17")
    assert pp.main(["--root", str(repo), "check"]) == 0
    _set_source(repo, _pin_source(sha[:7]))
    assert pp.main(["--root", str(repo), "check"]) == 1
    assert pp.main(["--root", str(repo), "pin", "oe-v9.9.9"]) == 1
