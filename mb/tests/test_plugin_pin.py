"""Release plugin pinning: the pin script and the check that guards a pinned marketplace.

The first-party remote is a local bare repo passed through the Python `remote`
parameter; the CLI has no such option.
"""

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


def _remote_path(root: Path) -> Path:
    return root.parent / "remote.git"


def _commit(root: Path, version: str, *, plugin_version: str | None = None) -> str:
    _write(root, version, plugin_version=plugin_version)
    _git(root, "add", "-A")
    _git(root, "commit", "-m", f"release {version}")
    return _git(root, "rev-parse", "HEAD")


def _release(
    root: Path, version: str, *, plugin_version: str | None = None, annotated: bool = False
) -> str:
    """Commit, tag oe-v<version>, and publish main and the tag to the fake first-party remote."""
    sha = _commit(root, version, plugin_version=plugin_version)
    tag = f"oe-v{version}"
    _git(root, "tag", *(["-a", "-m", tag] if annotated else []), tag)
    _git(root, "push", "-q", str(_remote_path(root)), "HEAD:refs/heads/main", f"refs/tags/{tag}")
    return sha


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(tmp_path, "init", "-q", "--bare", "remote.git")
    return root


@pytest.fixture
def remote(repo: Path) -> str:
    return str(_remote_path(repo))


def _pin_source(sha: str, **overrides: str) -> dict[str, str]:
    source = {"source": "url", "url": pp.PIN_URL, "sha": sha}
    source.update(overrides)
    return source


def _set_source(root: Path, source: object) -> None:
    path = root / pp.MARKETPLACE
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["plugins"][0]["source"] = source
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_unpinned_source_passes(repo: Path, remote: str) -> None:
    _release(repo, "0.6.17")
    assert pp.check(repo, remote=remote) == []


@pytest.mark.parametrize("annotated", [False, True])
def test_pin_writes_full_sha_and_https_url(repo: Path, remote: str, annotated: bool) -> None:
    sha = _release(repo, "0.6.17", annotated=annotated)
    assert pp.pin(repo, "oe-v0.6.17", remote=remote) == sha
    source = json.loads((repo / pp.MARKETPLACE).read_text(encoding="utf-8"))["plugins"][0]["source"]
    assert source == {
        "source": "url",
        "url": "https://github.com/dmthepm/mainbranch.git",
        "sha": sha,
    }
    assert pp.check(repo, remote=remote) == []


def test_pin_refuses_tag_whose_commit_declares_another_version(repo: Path, remote: str) -> None:
    _release(repo, "0.6.16")
    _git(repo, "tag", "oe-v0.6.17")  # tagged before the version bump landed
    _git(repo, "push", "-q", remote, "refs/tags/oe-v0.6.17")
    with pytest.raises(ValueError, match="declares plugin.json 0.6.16"):
        pp.pin(repo, "oe-v0.6.17", remote=remote)


def test_pin_refuses_when_plugin_and_marketplace_disagree(repo: Path, remote: str) -> None:
    _release(repo, "0.6.17", plugin_version="0.6.16")
    with pytest.raises(ValueError, match="refusing to pin"):
        pp.pin(repo, "oe-v0.6.17", remote=remote)


def test_pin_refuses_unknown_tag(repo: Path, remote: str) -> None:
    _release(repo, "0.6.17")
    with pytest.raises(ValueError, match="tag oe-v9.9.9 does not exist on the first-party remote"):
        pp.pin(repo, "oe-v9.9.9", remote=remote)


def test_pin_refuses_a_branch_name_that_is_not_a_tag(repo: Path, remote: str) -> None:
    _release(repo, "0.6.16")
    _commit(repo, "0.6.17")
    _git(repo, "push", "-q", remote, "HEAD:refs/heads/oe-v0.6.17")  # a branch, not a release tag
    with pytest.raises(ValueError, match="does not exist on the first-party remote"):
        pp.pin(repo, "oe-v0.6.17", remote=remote)


def test_pin_ignores_a_forged_local_tag(repo: Path, remote: str) -> None:
    real = _release(repo, "0.6.18")
    _git(repo, "reset", "-q", "--hard", "HEAD~0")
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "skill.md").write_text("changed skill\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "side commit repeating the version")
    forged = _git(repo, "rev-parse", "HEAD")
    _git(repo, "tag", "-f", "oe-v0.6.18")  # local only; the first-party tag stays on `real`
    assert pp.pin(repo, "oe-v0.6.18", remote=remote) == real != forged


def test_check_fails_when_pin_is_a_forged_local_tag_commit(repo: Path, remote: str) -> None:
    _release(repo, "0.6.18")
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "skill.md").write_text("changed skill\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "side commit repeating the version")
    forged = _git(repo, "rev-parse", "HEAD")
    _git(repo, "tag", "-f", "oe-v0.6.18")
    _set_source(repo, _pin_source(forged))
    assert any("cannot read the pinned commit" in p for p in pp.check(repo, remote=remote))


def test_check_fails_on_untagged_commit_repeating_the_released_version(
    repo: Path, remote: str
) -> None:
    _release(repo, "0.6.17")
    (repo / "extra.md").write_text("post-release change\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "post-release change, version unchanged")
    _git(repo, "push", "-q", remote, "HEAD:refs/heads/main")
    untagged = _git(repo, "rev-parse", "HEAD")
    _set_source(repo, _pin_source(untagged))
    problems = pp.check(repo, remote=remote)
    assert any("is not the commit of first-party tag oe-v0.6.17" in p for p in problems)


def test_check_fails_on_tagged_commit_outside_main(repo: Path, remote: str) -> None:
    _release(repo, "0.6.17")
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "x.md").write_text("x\n", encoding="utf-8")
    outside = _commit(repo, "0.6.18")
    _git(repo, "tag", "oe-v0.6.18")
    _git(repo, "push", "-q", remote, "refs/tags/oe-v0.6.18")  # tag only, never merged to main
    _set_source(repo, _pin_source(outside))
    assert any("cannot read the pinned commit" in p for p in pp.check(repo, remote=remote))


def test_pin_refuses_tagged_commit_outside_main(repo: Path, remote: str) -> None:
    _release(repo, "0.6.16")
    _git(repo, "checkout", "-q", "-b", "side")
    _commit(repo, "0.6.17")
    _git(repo, "tag", "oe-v0.6.17")
    _git(repo, "push", "-q", remote, "refs/tags/oe-v0.6.17")  # tag only, never merged to main
    with pytest.raises(ValueError, match="is not an ancestor of first-party main"):
        pp.pin(repo, "oe-v0.6.17", remote=remote)


def _forged_remote(root: Path, sha: str) -> str:
    """A second remote that claims a forged commit is the release on main."""
    forged = root.parent / "forged.git"
    _git(root.parent, "init", "-q", "--bare", "forged.git")
    _git(root, "tag", "oe-v0.6.17", sha)
    _git(root, "push", "-q", str(forged), f"{sha}:refs/heads/main", "refs/tags/oe-v0.6.17")
    return str(forged)


def test_git_environment_cannot_redirect_the_remote(
    repo: Path, remote: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = _release(repo, "0.6.17")
    _git(repo, "tag", "-d", "oe-v0.6.17")
    (repo / "forged.txt").write_text("not the release", encoding="utf-8")
    forged = _commit(repo, "0.6.17")
    target = _forged_remote(repo, forged)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", f"url.{target}.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", remote)
    assert pp.pin(repo, "oe-v0.6.17", remote=remote) == real != forged


def test_user_git_config_cannot_redirect_the_remote(
    repo: Path, remote: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = _release(repo, "0.6.17")
    _git(repo, "tag", "-d", "oe-v0.6.17")
    (repo / "forged.txt").write_text("not the release", encoding="utf-8")
    forged = _commit(repo, "0.6.17")
    target = _forged_remote(repo, forged)
    config = tmp_path / "gitconfig"
    config.write_text(f'[url "{target}"]\n\tinsteadOf = {remote}\n', encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    assert pp.pin(repo, "oe-v0.6.17", remote=remote) == real != forged


@pytest.mark.parametrize("key", ["url.{target}.insteadOf", "remote.{remote}.url"])
def test_repo_git_config_cannot_redirect_the_remote(repo: Path, remote: str, key: str) -> None:
    real = _release(repo, "0.6.17")
    _git(repo, "tag", "-d", "oe-v0.6.17")
    (repo / "forged.txt").write_text("not the release", encoding="utf-8")
    forged = _commit(repo, "0.6.17")
    target = _forged_remote(repo, forged)
    value = remote if "insteadOf" in key else target
    _git(repo, "config", key.format(target=target, remote=remote), value)
    assert pp.pin(repo, "oe-v0.6.17", remote=remote) == real != forged
    _set_source(repo, _pin_source(real))
    assert pp.check(repo, remote=remote) == []
    _set_source(repo, _pin_source(forged))
    assert any("cannot read the pinned commit" in p for p in pp.check(repo, remote=remote))


def test_pin_and_check_fail_when_remote_is_unreachable(repo: Path, tmp_path: Path) -> None:
    sha = _release(repo, "0.6.17")
    gone = str(tmp_path / "nowhere.git")
    with pytest.raises(ValueError, match="cannot fetch first-party main"):
        pp.pin(repo, "oe-v0.6.17", remote=gone)
    _set_source(repo, _pin_source(sha))
    problems = pp.check(repo, remote=gone)
    assert any("cannot fetch first-party main" in p for p in problems)
    assert pp.check(repo, offline=True, remote=gone) == []


def test_check_passes_when_versions_are_bumped_but_pin_names_previous_release(
    repo: Path, remote: str
) -> None:
    old = _release(repo, "0.6.17")
    _write(repo, "0.6.18", source=_pin_source(old))  # release commit: bumped, pin still old
    assert pp.check(repo, remote=remote) == []


def test_check_passes_when_pin_names_this_trees_release(repo: Path, remote: str) -> None:
    sha = _release(repo, "0.6.17")
    _set_source(repo, _pin_source(sha))
    assert pp.check(repo, remote=remote) == []


def test_check_passes_for_annotated_tag(repo: Path, remote: str) -> None:
    sha = _release(repo, "0.6.17", annotated=True)
    _set_source(repo, _pin_source(sha))
    assert pp.check(repo, remote=remote) == []


def test_check_fails_when_pinned_commit_is_newer_than_tree(repo: Path, remote: str) -> None:
    _release(repo, "0.6.17")
    new = _release(repo, "0.6.18")
    _write(repo, "0.6.17", source=_pin_source(new))
    assert any("newer than" in p for p in pp.check(repo, remote=remote))


def test_check_fails_when_pinned_commit_declares_mismatched_versions(
    repo: Path, remote: str
) -> None:
    bad = _release(repo, "0.6.17", plugin_version="0.6.16")
    _write(repo, "0.6.17", source=_pin_source(bad))
    assert any(
        "plugin.json 0.6.16 but marketplace 0.6.17" in p for p in pp.check(repo, remote=remote)
    )


def test_check_fails_on_short_sha(repo: Path, remote: str) -> None:
    sha = _release(repo, "0.6.17")
    _set_source(repo, _pin_source(sha[:12]))
    assert any("40-character" in p for p in pp.check(repo, remote=remote))


def test_check_fails_on_uppercase_sha(repo: Path, remote: str) -> None:
    sha = _release(repo, "0.6.17")
    _set_source(repo, _pin_source(sha.upper()))
    assert any("40-character" in p for p in pp.check(repo, remote=remote))


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
def test_check_fails_on_non_https_or_wrong_repo(repo: Path, remote: str, url: str) -> None:
    sha = _release(repo, "0.6.17")
    _set_source(repo, _pin_source(sha, url=url))
    assert any("pin url must be" in p for p in pp.check(repo, remote=remote))


def test_check_fails_on_github_source_shape(repo: Path, remote: str) -> None:
    sha = _release(repo, "0.6.17")
    _set_source(repo, {"source": "github", "repo": "dmthepm/mainbranch", "sha": sha})
    assert any("must be './' or a url pin" in p for p in pp.check(repo, remote=remote))


def test_check_fails_when_pinned_commit_is_not_available(repo: Path, remote: str) -> None:
    _release(repo, "0.6.17")
    _set_source(repo, _pin_source("0" * 40))
    assert any("cannot read the pinned commit" in p for p in pp.check(repo, remote=remote))
    assert pp.check(repo, offline=True, remote=remote) == []


@pytest.mark.parametrize("bad", ["0.6", "0.6.17.1", "0.6.x"])
def test_versions_must_have_exactly_three_numeric_parts(repo: Path, remote: str, bad: str) -> None:
    sha = _release(repo, "0.6.17")
    with pytest.raises(ValueError, match="three-part version"):
        pp.pin(repo, f"oe-v{bad}", remote=remote)
    _write(repo, bad, source=_pin_source(sha))
    with pytest.raises(ValueError, match="three numeric parts"):
        pp.check(repo, offline=True)


@pytest.mark.parametrize("bad", ["0.6", "0.6.17.1"])
def test_check_fails_when_pinned_commit_declares_a_non_canonical_version(
    repo: Path, remote: str, bad: str
) -> None:
    _commit(repo, bad)
    _git(repo, "push", "-q", remote, "HEAD:refs/heads/main")
    odd = _git(repo, "rev-parse", "HEAD")
    _write(repo, "0.6.18", source=_pin_source(odd))
    problems = pp.check(repo, remote=remote)
    assert any(
        "cannot read the pinned commit" in p and "three numeric parts" in p for p in problems
    )


@pytest.mark.parametrize(
    "manifest",
    [
        [],
        {"metadata": "0.6.17", "plugins": [{"name": "x", "source": "./"}]},
        {"metadata": {"version": 617}, "plugins": [{"name": "x", "source": "./"}]},
        {"metadata": {"version": "0.6.17"}, "plugins": "nope"},
    ],
)
def test_malformed_marketplace_is_a_plain_error(
    repo: Path, capsys: pytest.CaptureFixture[str], manifest: object
) -> None:
    _release(repo, "0.6.17")
    (repo / pp.MARKETPLACE).write_text(json.dumps(manifest), encoding="utf-8")
    assert pp.main(["--root", str(repo), "check", "--offline"]) == 1
    assert capsys.readouterr().err.startswith("plugin-pin: ")


@pytest.mark.parametrize("plugin_json", [[], {"version": 617}])
def test_malformed_plugin_json_at_pinned_commit_is_a_plain_problem(
    repo: Path, remote: str, plugin_json: object
) -> None:
    _write(repo, "0.6.17")
    (repo / pp.PLUGIN).write_text(json.dumps(plugin_json), encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "bad plugin.json")
    _git(repo, "push", "-q", remote, "HEAD:refs/heads/main")
    bad = _git(repo, "rev-parse", "HEAD")
    _set_source(repo, _pin_source(bad))
    problems = pp.check(repo, remote=remote)
    assert any("cannot read the pinned commit" in p for p in problems)


def test_candidate_export_resets_source_to_local(repo: Path, remote: str, tmp_path: Path) -> None:
    old = _release(repo, "0.6.17")
    _write(repo, "0.6.18", source=_pin_source(old))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "bump")
    head = _git(repo, "rev-parse", "HEAD")
    dest = tmp_path / "candidate"
    assert pp.candidate(repo, dest) == head
    exported = json.loads((dest / pp.MARKETPLACE).read_text(encoding="utf-8"))
    assert exported["plugins"][0]["source"] == "./"
    assert exported["metadata"]["version"] == "0.6.18"
    with pytest.raises(ValueError, match="not empty"):
        pp.candidate(repo, dest)


@pytest.mark.parametrize("kind", ["unstaged", "staged", "untracked"])
def test_candidate_refuses_a_dirty_tree(repo: Path, tmp_path: Path, kind: str) -> None:
    _release(repo, "0.6.17")
    if kind == "untracked":
        (repo / "new.md").write_text("new\n", encoding="utf-8")
    else:
        (repo / pp.PLUGIN).write_text("{}", encoding="utf-8")
        if kind == "staged":
            _git(repo, "add", "-A")
    with pytest.raises(ValueError, match="uncommitted or untracked"):
        pp.candidate(repo, tmp_path / "candidate")
    assert not (tmp_path / "candidate").exists()


def test_cli_prints_exported_head_sha(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _release(repo, "0.6.17")
    head = _git(repo, "rev-parse", "HEAD")
    assert pp.main(["--root", str(repo), "candidate", str(tmp_path / "out")]) == 0
    assert head in capsys.readouterr().out


def test_cli_cannot_override_the_remote(repo: Path) -> None:
    _release(repo, "0.6.17")
    with pytest.raises(SystemExit):
        pp.main(["--root", str(repo), "check", "--remote", "/tmp/x"])
    with pytest.raises(SystemExit):
        pp.main(["--root", str(repo), "pin", "oe-v0.6.17", "--remote", "/tmp/x"])


def test_cli_exit_codes(repo: Path) -> None:
    sha = _release(repo, "0.6.17")
    assert pp.main(["--root", str(repo), "check"]) == 0
    _set_source(repo, _pin_source(sha[:7]))
    assert pp.main(["--root", str(repo), "check"]) == 1
    assert pp.main(["--root", str(repo), "pin", "oe-v9.9.9"]) == 1
