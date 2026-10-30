"""Static guards for the package release workflow."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PUBLISH_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "publish-pypi.yml"


def _publish_workflow_text() -> str:
    return PUBLISH_WORKFLOW.read_text(encoding="utf-8")


def _publish_steps() -> list[tuple[str, dict[str, Any]]]:
    workflow = yaml.safe_load(_publish_workflow_text())
    return [(name, step) for name, job in workflow["jobs"].items() for step in job["steps"]]


def test_publish_workflow_validates_release_tag_before_downstream_jobs() -> None:
    text = _publish_workflow_text()

    assert "release-metadata:" in text
    assert r"^oe-v([0-9]+)\.([0-9]+)\.([0-9]+)$" in text
    assert "needs.release-metadata.outputs.valid == 'true'" in text
    assert "startsWith(github.event.release.tag_name" not in text


def test_publish_workflow_does_not_interpolate_release_tag_into_python_source() -> None:
    text = _publish_workflow_text()

    assert 'version = "$version"' not in text
    assert "python3 - <<PY" not in text
    assert "python3 - <<'PY'" in text
    assert 'os.environ["RELEASE_VERSION"]' in text


def test_publish_workflow_actions_are_pinned_to_commit_shas() -> None:
    text = _publish_workflow_text()
    refs = re.findall(r"^\s*uses:\s*([^@\s#]+)@([0-9a-f]{40})(?:\s+#\s+\S+)?$", text, re.M)
    uses_lines = re.findall(r"^\s*uses:\s*(\S+)", text, re.M)

    assert uses_lines
    assert len(refs) == len(uses_lines)


def test_publish_build_job_does_not_restore_a_dependency_cache() -> None:
    setup = [step for _, step in _publish_steps() if "setup-python" in step.get("uses", "")]

    assert setup
    assert all("cache" not in step.get("with", {}) for step in setup)


def test_publish_workflow_run_steps_do_not_expand_expressions() -> None:
    runs = [step["run"] for _, step in _publish_steps() if "run" in step]

    assert runs
    assert all("${{" not in run for run in runs)


def test_publish_workflow_checkouts_do_not_persist_credentials() -> None:
    checkouts = [step for _, step in _publish_steps() if "checkout" in step.get("uses", "")]

    assert len(checkouts) == 3
    assert all(step["with"]["persist-credentials"] is False for step in checkouts)
