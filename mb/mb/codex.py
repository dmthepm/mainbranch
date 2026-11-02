"""Codex global-skill helpers.

Codex support starts with repo instructions, global Main Branch skills, and
deterministic ``mb`` facts. This module intentionally does not invoke Codex or
manage model conversation.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from mb import __version__
from mb import engine as engine_mod
from mb.codex_data import _DEFAULT_AGENTS as _DEFAULT_AGENTS
from mb.codex_data import AGENTS_MANAGED_BEGIN as AGENTS_MANAGED_BEGIN
from mb.codex_data import AGENTS_MANAGED_END as AGENTS_MANAGED_END
from mb.codex_data import AGENTS_RELATIVE_PATH as AGENTS_RELATIVE_PATH
from mb.codex_data import AGENTS_TEMPLATE as AGENTS_TEMPLATE
from mb.codex_data import CLAUDE_PLAYBOOK_SOURCE_NAMES as CLAUDE_PLAYBOOK_SOURCE_NAMES
from mb.codex_data import CLAUDE_SKILL_SOURCE_NAMES as CLAUDE_SKILL_SOURCE_NAMES
from mb.codex_data import CODEX_ADS_APPROVAL_GATES as CODEX_ADS_APPROVAL_GATES
from mb.codex_data import CODEX_ADS_PUBLIC_PRIVATE_BOUNDARIES as CODEX_ADS_PUBLIC_PRIVATE_BOUNDARIES
from mb.codex_data import CODEX_ADS_REQUIRED_JSON_FACTS as CODEX_ADS_REQUIRED_JSON_FACTS
from mb.codex_data import CODEX_ADS_REQUIRED_MB_COMMANDS as CODEX_ADS_REQUIRED_MB_COMMANDS
from mb.codex_data import CODEX_ADS_SOURCE_WORKFLOW as CODEX_ADS_SOURCE_WORKFLOW
from mb.codex_data import CODEX_BET_APPROVAL_GATES as CODEX_BET_APPROVAL_GATES
from mb.codex_data import CODEX_BET_PUBLIC_PRIVATE_BOUNDARIES as CODEX_BET_PUBLIC_PRIVATE_BOUNDARIES
from mb.codex_data import CODEX_BET_REQUIRED_JSON_FACTS as CODEX_BET_REQUIRED_JSON_FACTS
from mb.codex_data import CODEX_BET_REQUIRED_MB_COMMANDS as CODEX_BET_REQUIRED_MB_COMMANDS
from mb.codex_data import CODEX_BET_SOURCE_WORKFLOW as CODEX_BET_SOURCE_WORKFLOW
from mb.codex_data import CODEX_END_APPROVAL_GATES as CODEX_END_APPROVAL_GATES
from mb.codex_data import CODEX_END_PUBLIC_PRIVATE_BOUNDARIES as CODEX_END_PUBLIC_PRIVATE_BOUNDARIES
from mb.codex_data import CODEX_END_REQUIRED_JSON_FACTS as CODEX_END_REQUIRED_JSON_FACTS
from mb.codex_data import CODEX_END_REQUIRED_MB_COMMANDS as CODEX_END_REQUIRED_MB_COMMANDS
from mb.codex_data import CODEX_END_SOURCE_WORKFLOW as CODEX_END_SOURCE_WORKFLOW
from mb.codex_data import CODEX_GLOBAL_SKILL_DESCRIPTIONS as CODEX_GLOBAL_SKILL_DESCRIPTIONS
from mb.codex_data import CODEX_GLOBAL_SKILL_FACTS as CODEX_GLOBAL_SKILL_FACTS
from mb.codex_data import CODEX_GLOBAL_SKILL_NAME as CODEX_GLOBAL_SKILL_NAME
from mb.codex_data import CODEX_GLOBAL_SKILL_NAMES as CODEX_GLOBAL_SKILL_NAMES
from mb.codex_data import CODEX_GLOBAL_SKILL_RELATIVE_PATH as CODEX_GLOBAL_SKILL_RELATIVE_PATH
from mb.codex_data import CODEX_GLOBAL_SKILL_SUPPORT as CODEX_GLOBAL_SKILL_SUPPORT
from mb.codex_data import CODEX_GUIDANCE_MIN_MB as CODEX_GUIDANCE_MIN_MB
from mb.codex_data import CODEX_GUIDANCE_SCHEMA as CODEX_GUIDANCE_SCHEMA
from mb.codex_data import CODEX_LEGACY_GLOBAL_SKILL_NAME as CODEX_LEGACY_GLOBAL_SKILL_NAME
from mb.codex_data import (
    CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH as CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH,
)
from mb.codex_data import CODEX_LEGACY_PLUGIN_NAME as CODEX_LEGACY_PLUGIN_NAME
from mb.codex_data import CODEX_LEGACY_PLUGIN_SELECTOR as CODEX_LEGACY_PLUGIN_SELECTOR
from mb.codex_data import (
    CODEX_MAINTENANCE_REPAIR_SOURCE_WORKFLOW as CODEX_MAINTENANCE_REPAIR_SOURCE_WORKFLOW,
)
from mb.codex_data import CODEX_MARKETPLACE_NAME as CODEX_MARKETPLACE_NAME
from mb.codex_data import CODEX_MARKETPLACE_RELATIVE_PATH as CODEX_MARKETPLACE_RELATIVE_PATH
from mb.codex_data import CODEX_ORGANIC_APPROVAL_GATES as CODEX_ORGANIC_APPROVAL_GATES
from mb.codex_data import (
    CODEX_ORGANIC_PUBLIC_PRIVATE_BOUNDARIES as CODEX_ORGANIC_PUBLIC_PRIVATE_BOUNDARIES,
)
from mb.codex_data import CODEX_ORGANIC_REQUIRED_JSON_FACTS as CODEX_ORGANIC_REQUIRED_JSON_FACTS
from mb.codex_data import CODEX_ORGANIC_REQUIRED_MB_COMMANDS as CODEX_ORGANIC_REQUIRED_MB_COMMANDS
from mb.codex_data import CODEX_ORGANIC_SOURCE_WORKFLOW as CODEX_ORGANIC_SOURCE_WORKFLOW
from mb.codex_data import CODEX_PLUGIN_COMMANDS_RELATIVE_PATH as CODEX_PLUGIN_COMMANDS_RELATIVE_PATH
from mb.codex_data import CODEX_PLUGIN_DIR_RELATIVE_PATH as CODEX_PLUGIN_DIR_RELATIVE_PATH
from mb.codex_data import CODEX_PLUGIN_INSTALL_COMMAND as CODEX_PLUGIN_INSTALL_COMMAND
from mb.codex_data import (
    CODEX_PLUGIN_LEGACY_COMMANDS_RELATIVE_PATH as CODEX_PLUGIN_LEGACY_COMMANDS_RELATIVE_PATH,
)
from mb.codex_data import CODEX_PLUGIN_MANIFEST_RELATIVE_PATH as CODEX_PLUGIN_MANIFEST_RELATIVE_PATH
from mb.codex_data import CODEX_PLUGIN_NAME as CODEX_PLUGIN_NAME
from mb.codex_data import CODEX_PLUGIN_REQUIRED_MARKERS as CODEX_PLUGIN_REQUIRED_MARKERS
from mb.codex_data import CODEX_PLUGIN_SELECTOR as CODEX_PLUGIN_SELECTOR
from mb.codex_data import CODEX_PLUGIN_SKILL_RELATIVE_PATH as CODEX_PLUGIN_SKILL_RELATIVE_PATH
from mb.codex_data import CODEX_REPAIR_COMMAND as CODEX_REPAIR_COMMAND
from mb.codex_data import CODEX_REPAIR_TEXT as CODEX_REPAIR_TEXT
from mb.codex_data import CODEX_RETIRED_GLOBAL_SKILL_NAMES as CODEX_RETIRED_GLOBAL_SKILL_NAMES
from mb.codex_data import CODEX_RUNTIME_MISMATCH_STOP_TEXT as CODEX_RUNTIME_MISMATCH_STOP_TEXT
from mb.codex_data import CODEX_SETUP_SOURCE_WORKFLOW as CODEX_SETUP_SOURCE_WORKFLOW
from mb.codex_data import CODEX_SHARED_WORKFLOW_SKILLS as CODEX_SHARED_WORKFLOW_SKILLS
from mb.codex_data import CODEX_SITE_APPROVAL_GATES as CODEX_SITE_APPROVAL_GATES
from mb.codex_data import (
    CODEX_SITE_PUBLIC_PRIVATE_BOUNDARIES as CODEX_SITE_PUBLIC_PRIVATE_BOUNDARIES,
)
from mb.codex_data import CODEX_SITE_REQUIRED_JSON_FACTS as CODEX_SITE_REQUIRED_JSON_FACTS
from mb.codex_data import CODEX_SITE_REQUIRED_MB_COMMANDS as CODEX_SITE_REQUIRED_MB_COMMANDS
from mb.codex_data import CODEX_SITE_SOURCE_WORKFLOW as CODEX_SITE_SOURCE_WORKFLOW
from mb.codex_data import CODEX_SKILL_DIR_RELATIVE_PATH as CODEX_SKILL_DIR_RELATIVE_PATH
from mb.codex_data import CODEX_SKILL_RELATIVE_PATH as CODEX_SKILL_RELATIVE_PATH
from mb.codex_data import CODEX_SLASH_COMMAND_DESCRIPTIONS as CODEX_SLASH_COMMAND_DESCRIPTIONS
from mb.codex_data import CODEX_SLASH_COMMAND_FACTS as CODEX_SLASH_COMMAND_FACTS
from mb.codex_data import CODEX_SLASH_COMMAND_NAMES as CODEX_SLASH_COMMAND_NAMES
from mb.codex_data import CODEX_SLASH_COMMAND_RELATIVE_PATHS as CODEX_SLASH_COMMAND_RELATIVE_PATHS
from mb.codex_data import CODEX_SOURCE_STATUS_DESCRIPTIONS as CODEX_SOURCE_STATUS_DESCRIPTIONS
from mb.codex_data import CODEX_SOURCE_STATUS_VOCABULARY as CODEX_SOURCE_STATUS_VOCABULARY
from mb.codex_data import CODEX_START_STATUS_SOURCE_WORKFLOW as CODEX_START_STATUS_SOURCE_WORKFLOW
from mb.codex_data import CODEX_SUPPORT_LEVEL as CODEX_SUPPORT_LEVEL
from mb.codex_data import CODEX_SURFACE_KIND_DESCRIPTIONS as CODEX_SURFACE_KIND_DESCRIPTIONS
from mb.codex_data import CODEX_SURFACE_KIND_VOCABULARY as CODEX_SURFACE_KIND_VOCABULARY
from mb.codex_data import CODEX_THINK_APPROVAL_GATES as CODEX_THINK_APPROVAL_GATES
from mb.codex_data import (
    CODEX_THINK_PUBLIC_PRIVATE_BOUNDARIES as CODEX_THINK_PUBLIC_PRIVATE_BOUNDARIES,
)
from mb.codex_data import CODEX_THINK_REQUIRED_JSON_FACTS as CODEX_THINK_REQUIRED_JSON_FACTS
from mb.codex_data import CODEX_THINK_REQUIRED_MB_COMMANDS as CODEX_THINK_REQUIRED_MB_COMMANDS
from mb.codex_data import CODEX_THINK_SOURCE_WORKFLOW as CODEX_THINK_SOURCE_WORKFLOW
from mb.codex_data import CODEX_WORKFLOW_INVENTORY as CODEX_WORKFLOW_INVENTORY
from mb.codex_data import (
    CODEX_WORKFLOW_INVENTORY_RELATIVE_PATH as CODEX_WORKFLOW_INVENTORY_RELATIVE_PATH,
)
from mb.codex_data import CODEX_WORKFLOW_STATUS_VOCABULARY as CODEX_WORKFLOW_STATUS_VOCABULARY
from mb.codex_data import REQUIRED_FACT_COMMANDS as REQUIRED_FACT_COMMANDS
from mb.codex_data import REQUIRED_LIFECYCLE_GUIDANCE as REQUIRED_LIFECYCLE_GUIDANCE
from mb.codex_data import REQUIRED_LIFECYCLE_GUIDANCE_MARKERS as REQUIRED_LIFECYCLE_GUIDANCE_MARKERS
from mb.codex_data import REQUIRED_LIFECYCLE_SECTION_MARKERS as REQUIRED_LIFECYCLE_SECTION_MARKERS
from mb.codex_guidance import _GUIDANCE_METADATA_RE as _GUIDANCE_METADATA_RE
from mb.codex_guidance import _OWNER_LINE_RE as _OWNER_LINE_RE
from mb.codex_guidance import AGENTS_RERUN_STEP as AGENTS_RERUN_STEP
from mb.codex_guidance import _agents_refusal as _agents_refusal
from mb.codex_guidance import _managed_agents_block as _managed_agents_block
from mb.codex_guidance import _managed_agents_content as _managed_agents_content
from mb.codex_guidance import _marker_refusal as _marker_refusal
from mb.codex_guidance import _merge_agents_md as _merge_agents_md
from mb.codex_guidance import _old_generated_span as _old_generated_span
from mb.codex_guidance import _unrendered_template_hash as _unrendered_template_hash
from mb.codex_guidance import parse_guidance_metadata as parse_guidance_metadata
from mb.codex_known_files import KNOWN_FILE_DIGESTS
from mb.durable import atomic_write_text
from mb.workflows import WorkflowSource, load_workflow, render_codex_shell


def _repo_flag(repo: str | Path | None) -> str:
    """The shared `--repo` rule (#1072); see `engine.repo_flag`."""

    return engine_mod.repo_flag(repo)


def repair_command(repo: str | Path | None = None) -> str:
    """The Codex apply command, naming the business repo when one is known (#1072)."""

    return f"mb doctor repair{_repo_flag(repo)} --apply --only codex"


def repair_text(repo: str | Path | None = None) -> str:
    """The Codex plan-then-apply sentence, naming the business repo when known (#1072)."""

    flag = _repo_flag(repo)
    return (
        f"Run `mb doctor repair{flag} --plan --only codex`, review, then "
        f"`mb doctor repair{flag} --apply --only codex`."
    )


def _global_plugin_root_unresolved() -> tuple[Path, bool]:
    """The global plugin root as configured, before links are resolved, and
    whether it came from `MAINBRANCH_CODEX_PLUGIN_ROOT`."""

    override = os.environ.get("MAINBRANCH_CODEX_PLUGIN_ROOT", "").strip()
    if override:
        return Path(override).expanduser(), True
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", "") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", "") or Path.home() / ".local" / "share")
    return (base / "mainbranch" / "codex").expanduser(), False


def global_plugin_source_root() -> Path:
    """Return the user-local source directory for the global Codex plugin."""

    return _global_plugin_root_unresolved()[0].resolve()


def global_plugin_root_link() -> Path | None:
    """A link at the global plugin root, or at its `mainbranch` folder (#1067).

    Main Branch names those folders; a link there leads somewhere a person
    chose, so the cleanup does not walk through it. None when neither is a link.
    """

    root, overridden = _global_plugin_root_unresolved()
    for candidate in (root,) if overridden else (root.parent, root):
        if candidate.is_symlink():
            return candidate
    return None


def _symlinked_ancestor(base: Path, path: Path) -> Path | None:
    """The first folder strictly between `base` and `path` that is a link (#1067)."""

    current = base
    for part in path.relative_to(base).parts[:-1]:
        current = current / part
        if current.is_symlink():
            return current
    return None


def _read_text_or_none(path: Path) -> str | None:
    """The file's UTF-8 text, "" when it is absent, None when it cannot be read.

    Unreadable means an OS error on read or bytes that are not UTF-8 (#1067).
    """

    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def global_skill_source_root() -> Path:
    """Return the user-local directory where Codex global skills are installed."""

    override = os.environ.get("MAINBRANCH_CODEX_SKILLS_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".codex" / "skills").expanduser().resolve()


def global_skill_path() -> Path:
    return global_skill_source_root() / CODEX_GLOBAL_SKILL_RELATIVE_PATH


def global_skill_file_path(name: str) -> Path:
    return global_skill_source_root() / name / "SKILL.md"


def _is_retired_mainbranch_global_skill(path: Path, name: str) -> bool:
    """Whether the retired skill at `path` (a link is read through) is one `mb` wrote.

    Proven by content: a known generated version of `<name>/SKILL.md`. A
    person's edited copy, or their own skill at that name, is not.
    """

    skill_file = path / "SKILL.md" if path.is_dir() else path
    return skill_file.parent.name == name and _is_known_generated_content(skill_file)


def codex_marketplace_add_command() -> str:
    return f"codex plugin marketplace add {shlex.quote(str(global_plugin_source_root()))}"


def _read_template(name: str) -> str:
    try:
        ref = resources.files("mb").joinpath("_data").joinpath("templates").joinpath(name)
        return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        here = Path(__file__).resolve().parent / "_data" / "templates" / name
        if here.exists():
            return here.read_text(encoding="utf-8")
        return ""


def _render(text: str, mapping: dict[str, str]) -> str:
    out = text
    for key, val in mapping.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def _which(name: str) -> str:
    return shutil.which(name) or ""


def _markdown_h1(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    except OSError:
        return ""
    return ""


def _repo_owner(repo: Path) -> str:
    codeowners = repo / ".github" / "CODEOWNERS"
    try:
        for raw_line in codeowners.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            for part in parts[1:]:
                if part.startswith("@"):
                    return part.removeprefix("@")
    except OSError:
        pass
    agents = repo / AGENTS_RELATIVE_PATH
    try:
        lines = agents.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "your-gh-username"
    for line in lines:
        stripped = line.strip().strip("`")
        if stripped.startswith("@") and " " not in stripped:
            return stripped.removeprefix("@")
    return "your-gh-username"


def business_name(repo: str | Path) -> str:
    target = Path(repo).expanduser().resolve()
    for relative in ("CLAUDE.md", "AGENTS.md"):
        name = _markdown_h1(target / relative)
        if name and "instructions" not in name.lower():
            return name
    return target.name or "Business"


def render_agents_md(repo: str | Path, *, name: str = "", gh_username: str = "") -> str:
    target = Path(repo).expanduser().resolve()
    template = _read_template(AGENTS_TEMPLATE) or _DEFAULT_AGENTS
    template_hash = guidance_template_hash(template)
    mapping = {
        "BUSINESS_NAME": name.strip() or business_name(target),
        "GH_USERNAME": gh_username.strip() or _repo_owner(target),
        "MAINBRANCH_VERSION": __version__,
        "CODEX_GUIDANCE_METADATA": guidance_metadata_comment(template_hash=template_hash),
    }
    return _render(template, mapping)


def _metadata_free_template(template: str) -> str:
    return template.replace("{{CODEX_GUIDANCE_METADATA}}\n\n", "").replace(
        "{{CODEX_GUIDANCE_METADATA}}\n", ""
    )


def guidance_template_hash(template: str | None = None) -> str:
    source = (
        template if template is not None else (_read_template(AGENTS_TEMPLATE) or _DEFAULT_AGENTS)
    )
    normalized = _metadata_free_template(source).replace("\r\n", "\n").strip() + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def guidance_metadata_comment(*, template_hash: str | None = None) -> str:
    digest = template_hash or guidance_template_hash()
    return (
        "<!-- mainbranch:codex-guidance "
        f"schema={CODEX_GUIDANCE_SCHEMA} "
        f"template_hash={digest} "
        f"min_mb={CODEX_GUIDANCE_MIN_MB} -->"
    )


def _agents_rerun_step(repo: str | Path | None = None) -> str:
    """The closing step of a refusal's manual step, naming the repo when known (#1072)."""

    return f"then run `mb doctor repair{_repo_flag(repo)} --plan --only codex` again."


def _markdown_section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start == -1:
        return ""
    next_heading = text.find("\n## ", start + len(heading))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]


def _commands_for_inventory_item(item: dict[str, Any]) -> tuple[str, ...]:
    commands = item.get("commands") or ()
    if not isinstance(commands, tuple):
        return tuple(str(command) for command in commands)
    return tuple(str(command) for command in commands)


def _workflow_source_path(relative_path: str) -> Path:
    root = engine_mod.engine_root()
    if root is not None:
        candidate = root / relative_path
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parents[2] / relative_path


def _load_shared_workflow_for_skill(name: str) -> WorkflowSource | None:
    relative_path = CODEX_SHARED_WORKFLOW_SKILLS.get(name)
    if relative_path is None:
        return None
    return load_workflow(_workflow_source_path(relative_path))


def _claude_skill_sources_for_inventory_item(item: dict[str, Any]) -> tuple[str, ...]:
    sources = item.get("claude_skill_sources") or ()
    names = sources if isinstance(sources, tuple) else tuple(str(source) for source in sources)
    return tuple(f".claude/skills/{name}/SKILL.md" for name in names)


def _claude_playbook_sources_for_inventory_item(item: dict[str, Any]) -> tuple[str, ...]:
    sources = item.get("claude_playbook_sources") or ()
    names = sources if isinstance(sources, tuple) else tuple(str(source) for source in sources)
    return tuple(f".claude/playbooks/{name}/SKILL.md" for name in names)


def _source_of_truth_for_inventory_item(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item["source_status"])
    surface_kinds = _surface_kinds_for_inventory_item(item)
    return {
        "status": status,
        "description": CODEX_SOURCE_STATUS_DESCRIPTIONS[status],
        "surface_type": item.get("surface_type", "workflow"),
        "playbook_status": item.get("playbook_status"),
        "status_reason": item.get("status_reason"),
        "shared_source": item.get("shared_source"),
        "playbook_source": item.get("playbook_source"),
        "surface_kinds": surface_kinds,
        "claude_sources": list(
            _claude_skill_sources_for_inventory_item(item)
            + _claude_playbook_sources_for_inventory_item(item)
        ),
        "codex_sources": [str(entrypoint) for entrypoint in item.get("codex_entrypoints", ())],
        "contract_checks": [str(check) for check in item.get("contract_checks", ())],
        "next_required_issue": item.get("next_required_issue"),
        "follow_up_issue": item.get("follow_up_issue"),
    }


def _surface_kinds_for_inventory_item(item: dict[str, Any]) -> list[str]:
    kinds: list[str] = []
    if item.get("shared_source"):
        kinds.append("shared_source")
    if item.get("claude_skill_sources"):
        kinds.append("claude_skill")
    if item.get("claude_playbook_sources"):
        kinds.append("playbook")
    if item.get("codex_entrypoints"):
        kinds.append("codex_global_skill")
    codex_status = str(item.get("codex_status", ""))
    source_status = str(item.get("source_status", ""))
    if codex_status == "read_only_planning":
        kinds.append("read_only_planning")
    if source_status == "pending_shared_source_migration":
        kinds.append("pending_shared_source_migration")
    if codex_status == "blocked_by_provider_gates" or source_status == "blocked_by_provider_gates":
        kinds.append("blocked_by_provider_gates")
    if codex_status == "internal_composable" or source_status == "internal_composable":
        kinds.append("internal_composable")
    if codex_status == "intentionally_unsupported":
        kinds.append("intentionally_unsupported")
    return kinds


def workflow_inventory(*, runtime: str = "codex") -> dict[str, Any]:
    """Return the public-safe Main Branch workflow support inventory."""

    items = []
    for item in CODEX_WORKFLOW_INVENTORY:
        copied = dict(item)
        copied["surface_type"] = str(item.get("surface_type", "workflow"))
        if item.get("playbook_status"):
            copied["playbook_status"] = str(item["playbook_status"])
        if item.get("playbook_source"):
            copied["playbook_source"] = str(item["playbook_source"])
        copied["commands"] = list(_commands_for_inventory_item(item))
        copied["claude_skill_sources"] = list(_claude_skill_sources_for_inventory_item(item))
        copied["claude_playbook_sources"] = list(_claude_playbook_sources_for_inventory_item(item))
        copied["codex_entrypoints"] = [
            str(entrypoint) for entrypoint in item.get("codex_entrypoints", ())
        ]
        copied["surface_kinds"] = _surface_kinds_for_inventory_item(item)
        copied["source_of_truth"] = _source_of_truth_for_inventory_item(item)
        items.append(copied)
    statuses = sorted(
        {*CODEX_WORKFLOW_STATUS_VOCABULARY}
        | {str(item["codex_status"]) for item in CODEX_WORKFLOW_INVENTORY}
    )
    source_statuses = sorted(
        {*CODEX_SOURCE_STATUS_VOCABULARY}
        | {str(item["source_status"]) for item in CODEX_WORKFLOW_INVENTORY}
    )
    counts = {
        "items": len(items),
        "workflows": len(items),
        "codex_global_skill_routes": len(CODEX_GLOBAL_SKILL_NAMES),
        "shared_source": sum(1 for item in items if "shared_source" in item["surface_kinds"]),
        "read_only_planning": sum(
            1 for item in items if "read_only_planning" in item["surface_kinds"]
        ),
        "intentionally_unsupported": sum(
            1 for item in items if "intentionally_unsupported" in item["surface_kinds"]
        ),
    }
    return {
        "ok": True,
        "runtime": runtime,
        "support_level": CODEX_SUPPORT_LEVEL,
        "entrypoint": "main-branch mb-start",
        "repo_guidance": AGENTS_RELATIVE_PATH,
        "inventory_path": CODEX_WORKFLOW_INVENTORY_RELATIVE_PATH,
        "architecture": {
            "canonical_flow": (
                "shared workflow source -> Claude Code shell -> Codex shell -> inventory/tests"
            ),
            "shared_source_root": "workflows/<workflow>/workflow.md",
            "runtime_shells": {
                "claude_code": ".claude/skills/<name>/SKILL.md",
                "codex_cli": "global main-branch skills plus AGENTS.md guidance",
            },
            "status_field": "items[].source_of_truth.status",
        },
        "claude_skill_sources": [
            f".claude/skills/{name}/SKILL.md" for name in CLAUDE_SKILL_SOURCE_NAMES
        ],
        "claude_playbook_sources": [
            f".claude/playbooks/{name}/SKILL.md" for name in CLAUDE_PLAYBOOK_SOURCE_NAMES
        ],
        "playbook_sources": sorted(
            str(item["playbook_source"])
            for item in CODEX_WORKFLOW_INVENTORY
            if item.get("playbook_source")
        ),
        "global_skill": {
            "name": CODEX_GLOBAL_SKILL_NAME,
            "display_name": "Main Branch",
            "path": CODEX_GLOBAL_SKILL_RELATIVE_PATH,
            "routes": list(CODEX_GLOBAL_SKILL_NAMES),
            "support": {
                name: CODEX_GLOBAL_SKILL_SUPPORT[name] for name in CODEX_GLOBAL_SKILL_NAMES
            },
            "install_hint": CODEX_REPAIR_COMMAND,
        },
        "statuses": statuses,
        "source_statuses": source_statuses,
        "source_status_descriptions": CODEX_SOURCE_STATUS_DESCRIPTIONS,
        "surface_kinds": list(CODEX_SURFACE_KIND_VOCABULARY),
        "surface_kind_descriptions": CODEX_SURFACE_KIND_DESCRIPTIONS,
        "json_shape": {
            "canonical_items": "items",
            "compatibility_alias": "workflows",
            "summary_count": "counts.items",
            "note": (
                "`items` is canonical; `workflows` is an alias for agents that "
                "expect workflow inventories under that key."
            ),
        },
        "counts": counts,
        "items": items,
        "workflows": items,
        "safe_to_share": True,
    }


def render_workflow_inventory_md() -> str:
    """Render the project-local Codex workflow inventory reference."""

    rows = []
    for item in CODEX_WORKFLOW_INVENTORY:
        commands = ", ".join(f"`{command}`" for command in _commands_for_inventory_item(item))
        entrypoints = ", ".join(f"`{entry}`" for entry in item.get("codex_entrypoints", ()))
        next_issue = item.get("next_required_issue") or item.get("follow_up_issue") or "None"
        claude_sources = ", ".join(
            f"`{source}`"
            for source in (
                _claude_skill_sources_for_inventory_item(item)
                + _claude_playbook_sources_for_inventory_item(item)
            )
        )
        row_template = (
            "| {label} | `{surface_type}` | `{status}` | `{source_status}` | {reason} | "
            "{next_issue} | {claude} | {sources} | {codex} | {entrypoints} | {commands} |"
        )
        rows.append(
            row_template.format(
                label=item["label"],
                surface_type=item.get("surface_type", "workflow"),
                status=item["codex_status"],
                source_status=item["source_status"],
                reason=item.get("status_reason", item["notes"]),
                next_issue=next_issue,
                claude=item["claude_surface"],
                sources=claude_sources or "None",
                codex=item["codex_surface"],
                entrypoints=entrypoints or "None",
                commands=commands or "None",
            )
        )
    return (
        "# Main Branch Codex Workflow Inventory\n\n"
        "Generated by `mb`. Do not edit by hand in business repos. This file maps "
        "Main Branch workflow surfaces to the Codex global-skill support boundary.\n\n"
        "Status meanings:\n\n"
        "- `supported`: Codex can use this surface through global Main Branch skills "
        "grounded in deterministic `mb` facts.\n"
        "- `read_only_planning`: Codex can inspect facts and help plan, but must "
        "not claim full workflow parity until a shared source migration lands.\n"
        "- `pending_shared_source_migration`: Codex may plan from read-only facts, "
        "but a runtime shell should wait for a shared workflow source.\n"
        "- `blocked_by_provider_gates`: Codex may plan or review, but provider "
        "mutation, publishing, spend, customer contact, or account changes wait "
        "for explicit gates and runtime evidence.\n"
        "- `internal_composable`: internal or provisional route hidden from "
        "default user-facing Codex global skills.\n"
        "- `generated_shell_pending`: a shared source exists, but a generated Codex "
        "shell still needs implementation and smoke evidence.\n"
        "- `intentionally_unsupported`: outside the current Codex daily-loop target.\n\n"
        "Source-of-truth meanings:\n\n"
        "- `shared_workflow_source`: `workflows/<workflow>/workflow.md` owns "
        "the portable workflow contract and tests check runtime shells against it.\n"
        "- `temporary_source_skill_mirror`: Codex mirrors existing Claude skill "
        "or CLI guidance until a shared source owns both runtime shells.\n"
        "- `pending_shared_source_migration`: Codex may use read-only facts or "
        "planning guidance, but runtime shells wait for a shared source migration.\n"
        "- `blocked_by_provider_gates`: planning or review may be useful, but "
        "execution waits for provider, publishing, spend, customer-contact, or "
        "account-mutation gates.\n"
        "- `internal_composable`: provisional surface that may compose other "
        "workflows but is not a default user-facing route.\n"
        "- `intentionally_unsupported`: outside the current Codex daily-loop target.\n\n"
        "Canonical architecture: shared workflow source -> Claude Code shell -> "
        "Codex shell -> inventory/tests. Temporary mirrors are explicit so "
        "reviewers can see which routes still need migration.\n\n"
        "`mb workflow list --runtime codex --json` returns workflow inventory "
        "under canonical `items`, with `workflows` as a compatibility alias and "
        "`counts.items` as the top-level count.\n\n"
        "Surface kinds in `mb workflow list --json`: `shared_source`, "
        "`claude_skill`, `playbook`, `codex_global_skill`, `read_only_planning`, "
        "`pending_shared_source_migration`, `blocked_by_provider_gates`, "
        "`internal_composable`, and `intentionally_unsupported`.\n\n"
        "The global Main Branch skill bundle is installed by "
        "`mb doctor repair --only codex`; business repos keep only lightweight "
        "`AGENTS.md` guidance. After repair, open a fresh Codex thread in the "
        "business repo and ask Main Branch to run one of the `mb-*` routes. "
        "Each row names its bundled Claude skill "
        "source(s); every bundled Claude `mb-*` skill must be accounted for here "
        "until the shared workflow generator owns both runtime shells.\n\n"
        "| Workflow | Type | Codex status | Source of truth | Reason | Next issue | "
        "Claude Code surface | Claude source | Codex surface | Codex route | Fact commands |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
        "Codex must ask before durable writes, checkpoints, repairs, updates, "
        "migrations, provider mutation, publishing, spend, customer contact, or "
        "public issue/proposal submission.\n"
    )


def render_codex_plugin_manifest() -> str:
    """Render the global Codex plugin manifest."""

    payload = {
        "name": CODEX_PLUGIN_NAME,
        "version": "0.1.0",
        "description": (
            "Main Branch /mb commands for Codex. Uses deterministic mb facts "
            "and business-repo guidance."
        ),
        "author": {"name": "Noontide"},
        "homepage": "https://github.com/dmthepm/mainbranch",
        "repository": "https://github.com/dmthepm/mainbranch",
        "license": "MIT",
        "keywords": ["main-branch", "mainbranch", "business-memory"],
        "interface": {
            "displayName": "Main Branch",
            "shortDescription": "Main Branch /mb commands for business repos",
            "longDescription": (
                "Adds Codex `/mb-*` commands for Main Branch business repos. Commands "
                "route through deterministic mb facts and repo guidance; "
                "they do not add provider mutation, publishing, spend, customer "
                "contact, ads/site production, or all-skill parity."
            ),
            "developerName": "Noontide",
            "category": "Productivity",
            "capabilities": ["Interactive", "Read", "Write"],
            "websiteURL": "https://github.com/dmthepm/mainbranch",
            "defaultPrompt": [
                "Use /mb-start to start this Main Branch business day",
                "Use /mb-help to show supported Main Branch Codex commands",
                "Use /mb-end to plan a checkpoint before saving work",
            ],
            "brandColor": "#0F766E",
            "screenshots": [],
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def render_codex_marketplace_json() -> str:
    """Render the global Codex plugin marketplace metadata."""

    payload = {
        "name": CODEX_MARKETPLACE_NAME,
        "interface": {"displayName": "Main Branch"},
        "plugins": [
            {
                "name": CODEX_PLUGIN_NAME,
                "source": {
                    "source": "local",
                    "path": f"./{CODEX_PLUGIN_DIR_RELATIVE_PATH}",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            }
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def _slash_command_label(name: str) -> str:
    return f"/{name}"


def render_codex_slash_command_md(name: str) -> str:
    """Render one thin Codex slash-command file for the global plugin."""

    if name not in CODEX_SLASH_COMMAND_NAMES:
        raise ValueError(f"unknown Codex slash command: {name}")
    description = CODEX_SLASH_COMMAND_DESCRIPTIONS[name]
    facts = CODEX_SLASH_COMMAND_FACTS[name]
    fact_lines = "\n".join(f"- `{command}`" for command in facts)
    command = _slash_command_label(name)
    specific = {
        "mb-start": (
            "Summarize the business state, readiness, ranked actions, and one "
            "clear next route. Use `mb start --json` when runtime handoff or "
            "Codex readiness matters."
        ),
        "mb-status": (
            "Answer from status facts: readiness, drift, recent work, "
            "since-last-check, MoneyPath, content strategy, provider signals, "
            "and ranked actions."
        ),
        "mb-setup": (
            "Treat setup prompts as onboarding intent. Explain the target folder "
            "and ask before running any command that writes files."
        ),
        "mb-update": (
            "Report whether an update is required or recommended. Ask before "
            "running update, repair, migration, or package-changing commands."
        ),
        "mb-doctor": (
            "Explain the repair plan in business language first. Quote exact "
            "safe commands and ask before applying any write action."
        ),
        "mb-think": (
            "Use the Codex Think Route in `AGENTS.md`. Choose the smallest honest "
            "research depth, read only needed business files, and ask before "
            "codifying or checkpointing."
        ),
        "mb-end": (
            "Use the shared closeout workflow. Run the status scan and checkpoint "
            "plan, summarize the session, capture a final thought, do "
            "crystallize-lite or an available subagent pass, name the owner-facing "
            "save state, and ask before saving."
        ),
        "mb-help": (
            "Show the supported, pending, and unsupported Codex workflow surfaces. "
            "Do not claim parity for surfaces the inventory does not mark supported."
        ),
    }[name]
    return f"""---
description: {description}
---

# {command}

Use Main Branch from the current repo. This command is a thin Codex route over
deterministic `mb` facts and the repo `AGENTS.md` guidance. Do not duplicate
workflow logic here.

## Preflight

Run first:

- `command -v mb`
- `mb --version`

If `mb` is missing or reports an unexpected version, stop and tell the operator
to fix the runtime/login-shell PATH before continuing.

## Facts

Run the read-only facts that fit this command:

{fact_lines}

Stop before business routing if `runtime.codex_cli.status` is
`runtime_mismatch` or if any drift item is `codex_runtime_mb_mismatch`.

## Route

{specific}

Ask before durable writes, checkpoints, updates, repairs, migrations, provider
mutation, publishing, spend, customer contact, destructive operations, or public
issue/proposal submission.
"""


def render_codex_slash_commands() -> dict[str, str]:
    """Render all generated Codex slash-command files by relative path."""

    return {
        f"{CODEX_PLUGIN_COMMANDS_RELATIVE_PATH}/{name}.md": render_codex_slash_command_md(name)
        for name in CODEX_SLASH_COMMAND_NAMES
    }


def _render_shared_workflow_global_skill_adapter(workflow: WorkflowSource) -> str:
    rendered_shell = render_codex_shell(workflow).strip()
    return (
        "Follow the generated Codex shell below. It is rendered from the canonical "
        "shared workflow source, so workflow substance belongs in that source and "
        "Codex differences stay in this adapter layer.\n\n"
        f"{rendered_shell}"
    )


def render_codex_global_skill_md(name: str = CODEX_GLOBAL_SKILL_NAME) -> str:
    """Render one global Main Branch Codex skill."""

    route_lines = "\n".join(
        f"- `{skill}`: {CODEX_GLOBAL_SKILL_DESCRIPTIONS[skill]} "
        f"({CODEX_GLOBAL_SKILL_SUPPORT[skill]})"
        for skill in CODEX_GLOBAL_SKILL_NAMES
        if skill != CODEX_GLOBAL_SKILL_NAME
    )
    if name not in CODEX_GLOBAL_SKILL_NAMES:
        raise ValueError(f"unknown Codex global skill: {name}")
    description = CODEX_GLOBAL_SKILL_DESCRIPTIONS[name]
    support_level = CODEX_GLOBAL_SKILL_SUPPORT[name]
    workflow = _load_shared_workflow_for_skill(name)
    facts = tuple(workflow.required_mb_commands) if workflow else CODEX_GLOBAL_SKILL_FACTS[name]
    if name == CODEX_GLOBAL_SKILL_NAME:
        argument_hint = (
            "[mb-start|mb-status|mb-setup|mb-update|mb-doctor|mb-think|mb-end|mb-help|other-route]"
        )
        title = "Main Branch"
        route_guidance = (
            "Choose the closest route below, then follow that route's facts and approval boundary."
        )
    else:
        argument_hint = "[target]"
        title = name
        if workflow is not None:
            route_guidance = _render_shared_workflow_global_skill_adapter(workflow)
        else:
            supported_guidance = {
                "mb-start": (
                    "Summarize the business state, readiness, ranked actions, and one "
                    "clear next route. Use `mb start --json` when runtime handoff or "
                    "Codex readiness matters."
                ),
                "mb-status": (
                    "Answer from status facts: readiness, drift, recent work, "
                    "since-last-check, MoneyPath, content strategy, provider signals, "
                    "and ranked actions."
                ),
                "mb-setup": (
                    "Treat setup prompts as onboarding intent. Explain the target folder "
                    "and ask before running any command that writes files."
                ),
                "mb-update": (
                    "Report whether an update is required or recommended. Ask before "
                    "running update, repair, migration, or package-changing commands."
                ),
                "mb-doctor": (
                    "Explain the repair plan in business language first. Quote exact "
                    "safe commands and ask before applying any write action."
                ),
                "mb-think": (
                    "Use the Codex Think Route in `AGENTS.md`. Choose the smallest honest "
                    "research depth, read only needed business files, and ask before "
                    "codifying or checkpointing."
                ),
                "mb-end": (
                    "Use the shared closeout workflow. Run the status scan and checkpoint "
                    "plan, summarize the session, capture a final thought, do "
                    "crystallize-lite or an available subagent pass, name the owner-facing "
                    "save state, and ask before saving."
                ),
                "mb-help": (
                    "Show the supported, pending, and unsupported Codex workflow surfaces. "
                    "Do not claim parity for surfaces the inventory does not mark supported."
                ),
                "mb-books": (
                    "From the business repo run `mb books check . --json`. Discover "
                    "books_repo in core/finance/books.md or ask for its location, then "
                    "run `mb books doctor --repo $BOOKS_REPO --json`. Review only "
                    "aggregate close state and process docs. Never open evidence "
                    "bytes, quote doctor output or financial details, post or edit "
                    "journal entries, or run hledger import/add. Propose rules edits "
                    "for operator approval in the private books repo."
                ),
            }
            if name in supported_guidance:
                route_guidance = supported_guidance[name]
            elif support_level == "read_only_planning":
                route_guidance = (
                    "Use this as a read-only planning route in Codex. Ground the answer "
                    "in the facts below, name what Claude Code can do more fully when "
                    "relevant, and ask before writing files or touching providers. This "
                    "route is pending shared source migration and is not full workflow "
                    "parity."
                )
            else:
                route_guidance = (
                    "This workflow is inventoried for completeness but is not a supported "
                    "Codex execution route yet. Explain the support boundary and route "
                    "the operator to Claude Code or another supported Main Branch path."
                )
    fact_lines = "\n".join(f"- `{command}`" for command in facts)
    return f"""---
name: {name}
description: "{description}"
argument-hint: "{argument_hint}"
user-invocable: true
---

# {title}

Support level: `{support_level}`.

Use this skill when the operator is in a Main Branch business repo and asks to
start the day, inspect status, set up, update, repair, think through a decision,
close a session, get help, or use one of the inventoried Main Branch workflows.

## Routes

{route_lines}

{route_guidance}

Use the route names above as product-facing workflow names. Do not introduce
legacy adapter names, installation internals, or command-surface vocabulary in
operator-facing answers.

## Grounding

Start in the current repo. Run the read-only facts that fit the route before
advice:

{fact_lines}

Run `command -v mb` and `mb --version` first when setup, update, repair, or
runtime readiness is uncertain. If `mb` is missing or reports an unexpected
version, stop and tell the operator to fix the runtime/login-shell PATH before
continuing.

Use `mb status --json --peek` as the default daily briefing source. It names
readiness, drift, onboarding progress, update state, GitHub activity, provider
signals, recent work, MoneyPath, ranked actions, bets, pushes, and checkpoint
state. Use `mb start --json` when runtime handoff or repo-boundary facts matter.

Stop before business routing if `runtime.codex_cli.status` is `runtime_mismatch`
or if any drift item is `codex_runtime_mb_mismatch`.

## Approval

Read-only fact commands can run without asking. Ask before durable writes,
checkpoints, updates, repairs, migrations, provider mutation, publishing, spend,
customer contact, destructive operations, or public issue/proposal submission.

## Boundaries

Codex supports the daily Main Branch routes listed here. Do not claim all Claude
Code skills, provider mutation, ads/site production, publishing, spend, customer
contact, or Claude Code command surfaces are available unless `mb workflow list
--runtime codex --json` and current runtime evidence say so.
Read workflow inventory from canonical `items`; `workflows` is a compatibility
alias and `counts.items` is the top-level count.
"""


def agents_path(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve() / AGENTS_RELATIVE_PATH


def codex_skill_path(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve() / CODEX_SKILL_RELATIVE_PATH


def workflow_inventory_path(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve() / CODEX_WORKFLOW_INVENTORY_RELATIVE_PATH


def marketplace_path(repo: str | Path) -> Path:
    return global_plugin_source_root() / CODEX_MARKETPLACE_RELATIVE_PATH


def plugin_manifest_path(repo: str | Path) -> Path:
    return global_plugin_source_root() / CODEX_PLUGIN_MANIFEST_RELATIVE_PATH


def plugin_skill_path(repo: str | Path) -> Path:
    return global_plugin_source_root() / CODEX_PLUGIN_SKILL_RELATIVE_PATH


def plugin_commands_dir(repo: str | Path) -> Path:
    return global_plugin_source_root() / CODEX_PLUGIN_COMMANDS_RELATIVE_PATH


def plugin_command_path(repo: str | Path, name: str) -> Path:
    return plugin_commands_dir(repo) / f"{name}.md"


def executable_status() -> dict[str, Any]:
    path = _which("codex")
    return {
        "found": bool(path),
        "path": path,
        "executable": "codex",
        "repair": "" if path else "Install Codex CLI before using Main Branch in Codex.",
    }


def _run_codex_plugin_command(repo: Path, args: list[str]) -> dict[str, Any]:
    codex_path = _which("codex")
    command = [codex_path or "codex", *args]
    if not codex_path:
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": "codex not on PATH",
            "command": " ".join(["codex", *args]),
        }
    try:
        proc = subprocess.run(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": 124,
            "stdout": "",
            "stderr": "codex plugin command timed out",
            "command": " ".join(["codex", *args]),
        }
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
            "command": " ".join(["codex", *args]),
        }
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": " ".join(["codex", *args]),
    }


def _codex_plugin_list(repo: Path) -> dict[str, Any]:
    return _run_codex_plugin_command(
        repo,
        ["plugin", "list", "--marketplace", CODEX_MARKETPLACE_NAME],
    )


def _parse_plugin_install_status(output: str, expected_marketplace_path: Path) -> dict[str, Any]:
    lines = output.splitlines()
    actual_marketplace_path = ""
    for index, line in enumerate(lines):
        if line.strip() == f"Marketplace `{CODEX_MARKETPLACE_NAME}`":
            if index + 1 < len(lines):
                actual_marketplace_path = lines[index + 1].strip()
            break

    marketplace_registered = bool(
        actual_marketplace_path
        and Path(actual_marketplace_path).expanduser().resolve()
        == expected_marketplace_path.expanduser().resolve()
    )
    marketplace_stale = bool(actual_marketplace_path and not marketplace_registered)
    plugin_line = next((line.strip() for line in lines if CODEX_PLUGIN_SELECTOR in line), "")
    plugin_available = bool(plugin_line and marketplace_registered)
    status_text = plugin_line.split(CODEX_PLUGIN_SELECTOR, 1)[1].strip() if plugin_line else ""
    plugin_installed = bool(
        plugin_available and "installed" in status_text and "not installed" not in status_text
    )
    plugin_enabled = bool(plugin_installed and "enabled" in status_text)
    return {
        "marketplace_registered": marketplace_registered,
        "marketplace_stale": marketplace_stale,
        "marketplace_path": str(expected_marketplace_path),
        "registered_marketplace_path": actual_marketplace_path,
        "global_plugin_installed": plugin_installed,
        "plugin_available": plugin_available,
        "plugin_installed": plugin_installed,
        "plugin_enabled": plugin_enabled,
        "skill_available": False,
        "skill_ready": False,
        "slash_commands_ready": False,
        "plugin_line": plugin_line,
    }


def plugin_install_status(repo: str | Path, *, adapter_files_ok: bool = True) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    expected_marketplace_path = marketplace_path(target)
    install_command = CODEX_PLUGIN_INSTALL_COMMAND
    register_command = codex_marketplace_add_command()
    source_status = plugin_status(target)
    source_ok = source_status["ok"]
    if not _which("codex"):
        return {
            "checked": False,
            "ok": False,
            "state": "codex_missing",
            "summary": "Codex CLI is not installed, so plugin install state was not checked.",
            "marketplace_name": CODEX_MARKETPLACE_NAME,
            "plugin_selector": CODEX_PLUGIN_SELECTOR,
            "marketplace_registered": False,
            "marketplace_stale": False,
            "global_source_path": str(global_plugin_source_root()),
            "global_source_ok": source_ok,
            "plugin_available": False,
            "global_plugin_installed": False,
            "plugin_installed": False,
            "plugin_enabled": False,
            "command_files_current": bool(source_status.get("command_files_current", False)),
            "command_surface_ok": False,
            "slash_commands_likely_loaded": False,
            "slash_commands_restart_required": False,
            "skill_ready": False,
            "slash_commands_ready": False,
            "install_command": install_command,
            "register_command": register_command,
            "repair": "Install Codex CLI before using Main Branch Codex commands.",
            "safe_to_share": True,
        }
    if not adapter_files_ok:
        return {
            "checked": False,
            "ok": False,
            "state": "waiting_for_adapter_files",
            "summary": (
                "Codex plugin install check waits until repo AGENTS.md guidance is current."
            ),
            "marketplace_name": CODEX_MARKETPLACE_NAME,
            "plugin_selector": CODEX_PLUGIN_SELECTOR,
            "marketplace_registered": False,
            "marketplace_stale": False,
            "global_source_path": str(global_plugin_source_root()),
            "global_source_ok": source_ok,
            "plugin_available": False,
            "global_plugin_installed": False,
            "plugin_installed": False,
            "plugin_enabled": False,
            "command_files_current": bool(source_status.get("command_files_current", False)),
            "command_surface_ok": False,
            "slash_commands_likely_loaded": False,
            "slash_commands_restart_required": False,
            "skill_ready": False,
            "slash_commands_ready": False,
            "install_command": install_command,
            "register_command": register_command,
            "repair": repair_text(target),
            "safe_to_share": True,
        }

    if not source_ok:
        return {
            "checked": True,
            "ok": False,
            "state": "global_plugin_source_missing",
            "summary": ("The global Main Branch Codex plugin source is missing or stale."),
            "marketplace_name": CODEX_MARKETPLACE_NAME,
            "plugin_selector": CODEX_PLUGIN_SELECTOR,
            "marketplace_registered": False,
            "marketplace_stale": False,
            "marketplace_path": str(expected_marketplace_path),
            "registered_marketplace_path": "",
            "global_source_path": str(global_plugin_source_root()),
            "global_source_ok": False,
            "plugin_available": False,
            "global_plugin_installed": False,
            "plugin_installed": False,
            "plugin_enabled": False,
            "slash_commands_ready": False,
            "command_files_current": bool(source_status.get("command_files_current", False)),
            "command_surface_ok": False,
            "slash_commands_likely_loaded": False,
            "slash_commands_restart_required": False,
            "skill_ready": False,
            "plugin_line": "",
            "install_command": install_command,
            "register_command": register_command,
            "repair": f"Run `{repair_command(target)}` to install the global plugin.",
            "safe_to_share": True,
        }

    result = _codex_plugin_list(target)
    parsed = _parse_plugin_install_status(
        str(result.get("stdout") or ""), expected_marketplace_path
    )
    command_files_current = bool(source_status.get("command_files_current"))
    state = "ok"
    summary = "Main Branch Codex commands are installed and ready after restarting Codex."
    repair = ""
    if not result["ok"]:
        state = "plugin_state_unverified"
        summary = "Codex plugin install state could not be checked."
        repair = f"Run `{register_command}`, then `{install_command}`."
    elif not parsed["marketplace_registered"]:
        state = "marketplace_not_registered"
        summary = (
            "The global Main Branch Codex plugin source is ready, but its Codex "
            "marketplace is not registered."
        )
        if parsed["marketplace_stale"]:
            summary = (
                "A `main-branch` Codex marketplace is registered, but it "
                "points at a different Main Branch plugin source."
            )
        repair = f"Run `{register_command}`, then `{install_command}`."
    elif not parsed["plugin_available"]:
        state = "plugin_not_available"
        summary = (
            "The global Main Branch Codex marketplace is registered, but the plugin is missing."
        )
        repair = f"Run `{register_command}`, then `{install_command}`."
    elif not parsed["plugin_installed"]:
        state = "plugin_not_installed"
        summary = (
            "The global Main Branch Codex plugin source is ready, but the plugin "
            "is not installed in Codex yet."
        )
        repair = f"Run `{install_command}`."
    elif not parsed["plugin_enabled"]:
        state = "plugin_disabled"
        summary = "The Main Branch Codex plugin is installed but not enabled."
        repair = f"Enable `{CODEX_PLUGIN_SELECTOR}` in Codex plugins."
    elif not command_files_current:
        state = "slash_commands_stale"
        summary = "Main Branch Codex command files are missing or stale."
        repair = repair_text(target)

    installed_enabled_current = bool(
        state == "ok"
        and command_files_current
        and parsed["plugin_installed"]
        and parsed["plugin_enabled"]
    )
    return {
        "checked": True,
        "ok": state == "ok",
        "state": state,
        "summary": summary,
        "marketplace_name": CODEX_MARKETPLACE_NAME,
        "plugin_selector": CODEX_PLUGIN_SELECTOR,
        **parsed,
        "global_source_path": str(global_plugin_source_root()),
        "global_source_ok": source_ok,
        "command_files": list(CODEX_SLASH_COMMAND_RELATIVE_PATHS),
        "command_files_current": command_files_current,
        "slash_commands_generated": command_files_current,
        "command_surface_ok": installed_enabled_current,
        "slash_commands_ready": installed_enabled_current,
        "slash_commands_likely_loaded": False,
        "slash_commands_restart_required": installed_enabled_current,
        "install_command": install_command,
        "register_command": register_command,
        "repair": repair,
        "command": result.get("command", ""),
        "returncode": result.get("returncode"),
        "error": str(result.get("stderr") or "").strip(),
        "safe_to_share": True,
    }


def install_plugin(repo: str | Path) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    source = write_global_plugin_source()
    steps = [
        _run_codex_plugin_command(target, ["plugin", "remove", CODEX_LEGACY_PLUGIN_SELECTOR]),
        _run_codex_plugin_command(
            target,
            ["plugin", "marketplace", "add", str(global_plugin_source_root())],
        ),
        _run_codex_plugin_command(target, ["plugin", "add", CODEX_PLUGIN_SELECTOR]),
    ]
    final = plugin_install_status(target)
    return {
        "ok": bool(final.get("ok")),
        "source": source,
        "steps": steps,
        "status": final,
        "safe_to_share": True,
    }


def global_skill_status(repo: str | Path) -> dict[str, Any]:
    """Return status for the global Main Branch Codex skill bundle."""

    expected_by_name = {
        name: render_codex_global_skill_md(name) for name in CODEX_GLOBAL_SKILL_NAMES
    }
    path_by_name = {name: global_skill_file_path(name) for name in CODEX_GLOBAL_SKILL_NAMES}
    missing = [f"{name}/SKILL.md" for name, path in path_by_name.items() if not path.is_file()]
    read_error = ""
    stale: list[str] = []
    missing_markers: list[str] = []
    skill_reports: dict[str, dict[str, Any]] = {}
    unreadable: list[str] = []
    for skill_name, path in path_by_name.items():
        exists = path.is_file()
        text = ""
        skill_read_error = ""
        try:
            text = path.read_text(encoding="utf-8") if exists else ""
        except (OSError, UnicodeDecodeError) as exc:
            # #1067: unreadable (an OS error, or bytes that are not UTF-8) is
            # reported, kept and never overwritten; see `global_skill_operations`.
            skill_read_error = str(exc)
            read_error = skill_read_error
            unreadable.append(str(path))
        markers = (
            f"name: {skill_name}",
            "user-invocable: true",
            "mb status --json --peek",
        )
        route_missing = [marker for marker in markers if marker not in text]
        if route_missing:
            missing_markers.extend(f"{skill_name}: {marker}" for marker in route_missing)
        if exists and not skill_read_error and text != expected_by_name[skill_name]:
            stale.append(f"{skill_name}/SKILL.md")
        skill_reports[skill_name] = {
            "ok": bool(
                exists
                and not route_missing
                and not skill_read_error
                and text == expected_by_name[skill_name]
            ),
            "exists": exists,
            "current": bool(exists and text == expected_by_name[skill_name]),
            "path": f"{skill_name}/SKILL.md",
            "absolute_path": str(path),
            "missing_markers": route_missing,
            "read_error": skill_read_error,
        }
    # #1056: an old surface is stale while it holds a Main Branch file; a
    # person's files left in it are reported as kept, never removed.
    cleanup = global_skill_cleanup()
    stale.extend(cleanup["removals"])
    ok = bool(not missing and not stale and not read_error and not missing_markers)
    linked = [str(path) for path in _linked_current_skill_folders()]
    summary = (
        "The global Main Branch Codex skill bundle is installed and current."
        if ok
        else (
            "The global Main Branch Codex skill bundle is missing, stale, "
            "or has old plugin artifacts."
        )
    )
    # #1087 item 6: informational, not an action; present only when it applies.
    extra: dict[str, Any] = (
        {"linked": linked, "note": _linked_current_note(linked)} if linked else {}
    )
    return {
        "checked": True,
        "ok": ok,
        "state": "ok" if ok else "global_skill_missing_or_stale",
        "summary": f"{summary} {extra['note']}" if extra else summary,
        "name": CODEX_GLOBAL_SKILL_NAME,
        "display_name": "Main Branch",
        "path": CODEX_GLOBAL_SKILL_RELATIVE_PATH,
        "absolute_path": str(global_skill_path()),
        "skills_root": str(global_skill_source_root()),
        "exists": not missing,
        "current": bool(not stale and not missing_markers),
        "skills": skill_reports,
        "required_skills": list(CODEX_GLOBAL_SKILL_NAMES),
        "stale": stale,
        "kept": [*unreadable, *cleanup["kept"]],
        "missing": missing,
        "missing_markers": missing_markers,
        "read_error": read_error,
        "routes": list(CODEX_SLASH_COMMAND_NAMES),
        "repair": "" if ok else repair_text(repo),
        "repair_command": repair_command(repo),
        **extra,
        "safe_to_share": True,
    }


def _owned_tree_cleanup(
    path: Path,
    is_owned: Callable[[Path], bool],
    *,
    remove_link: bool = True,
    base: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Per-file removals under one Main Branch path, and the entries it keeps (#1056).

    Only files `is_owned` recognises are removed, one by one, and a folder
    goes only once it is empty. A symlink at `path` itself is removed as a
    link when `remove_link`, never followed. Symlinks inside and every other
    file stay, and are returned as kept. When a folder between `base` and
    `path` is a link, nothing under it is walked; the link is kept (#1067).
    """

    link = _symlinked_ancestor(base, path) if base is not None else None
    if link is not None:
        return [], [str(link)] if path.exists() or path.is_symlink() else []
    if path.is_symlink():
        if remove_link:
            return [{"op": "delete", "path": str(path), "root": str(path)}], []
        return [], [str(path)]
    if path.is_file():
        if is_owned(path):
            return [{"op": "delete", "path": str(path), "root": str(path)}], []
        return [], [str(path)]
    if not path.is_dir():
        return [], []
    operations: list[dict[str, Any]] = []
    kept: list[str] = []
    for root, dirs, files in os.walk(path):
        base = Path(root)
        for entry in sorted([*files, *(name for name in dirs if (base / name).is_symlink())]):
            item = base / entry
            if is_owned(item):
                operations.append({"op": "delete", "path": str(item), "root": str(path)})
            else:
                kept.append(str(item))
    return operations, kept


def _plugin_link_above(path: Path) -> Path | None:
    """The link at the plugin root or its `mainbranch` folder, if it exists right now,
    for a planned plugin `path` (#1078). Checked again just before each removal.

    A path under the skills root is not a plugin path. The plan's own paths cannot be
    compared with the plugin root here: once the link exists, the root resolves
    through it.
    """

    link = global_plugin_root_link()
    if link is None:
        return None
    skills_root = global_skill_source_root()
    return None if path == skills_root or skills_root in path.parents else link


def _link_on_the_way(base: Path, path: Path) -> bool:
    """Whether `base`, or a folder between it and `path`, is now a link (#1067)."""

    return path != base and (base.is_symlink() or _symlinked_ancestor(base, path) is not None)


def _unlink_if_proven(path: Path, base: Path | None = None) -> bool:
    """Remove `path` only if its content is proven to be Main Branch's right now.

    Both applies, repo-local and global, prove each file again just before
    removing it, so a file changed after the plan stays (#1067). With `base`
    (where the plan's walk started) it also stays when `base` or a folder
    between them is now a link: the plan walked through none, so a link there
    appeared after it, and the file is no longer where the plan saw it.
    """

    if base is not None and _link_on_the_way(base, path):
        return False
    if not _is_mainbranch_transitional_file(path):
        return False
    path.unlink()
    return True


def _remove_owned_entry(item: dict[str, Any]) -> bool:
    """Remove one planned file or link, then any folders it leaves empty up to its root.

    A link is removed, as a link, only where the plan removes the path itself.
    A file is proven again first; one changed since the plan stays (#1067).
    """

    path = Path(item["path"])
    root = Path(item.get("root") or item["path"])
    if path.is_symlink():
        if path != root:
            return False
        path.unlink()  # a link is removed as a link, never followed
    elif not _unlink_if_proven(path, root):
        return False
    parent = path.parent
    while parent == root or root in parent.parents:
        try:
            parent.rmdir()  # only an empty folder; a non-empty one stays
        except OSError:
            break
        parent = parent.parent
    return True


def _is_retired_skill_file(name: str) -> Callable[[Path], bool]:
    def owned(path: Path) -> bool:
        return (
            path.name == "SKILL.md"
            and path.parent.name == name
            and not path.is_symlink()
            and _is_retired_mainbranch_global_skill(path, name)
        )

    return owned


def _held_global_skill_entry(path: Path) -> Path | None:
    """Keep a linked skill folder, a folder at SKILL.md, or a broken SKILL.md link."""

    if path.parent.is_symlink():
        return path.parent
    if path.is_dir() or (path.is_symlink() and not path.exists()):
        return path
    return None


def _linked_current_skill_folders() -> list[Path]:
    """Linked skill folders that already hold the current skill file (#1087 item 6).

    Nothing is written through them, as for any linked folder, but there is
    nothing for a person to do either, so they are not listed as kept.
    """

    found: list[Path] = []
    for name in CODEX_GLOBAL_SKILL_NAMES:
        path = global_skill_file_path(name)
        if (
            path.parent.is_symlink()
            and not path.is_symlink()
            and path.is_file()
            and _read_text_or_none(path) == render_codex_global_skill_md(name)
        ):
            found.append(path.parent)
    return found


def _linked_current_note(linked: list[str]) -> str:
    """The informational note for linked skill folders that are current (#1087 item 6)."""

    return (
        ", ".join(linked)
        + (" is a link" if len(linked) == 1 else " are links")
        + " to a folder that already holds the current Main Branch skill file. "
        "Nothing to do: Main Branch does not write through links, and if a later "
        "release changes the skill, `mb doctor` will say so."
    )


def global_skill_cleanup() -> dict[str, Any]:
    """Old global Codex surfaces to remove, per file, and what stays (#1056).

    `removals` maps each old surface (the label `global_skill_status` reports
    as stale) to its delete operations. `kept` lists files Main Branch did not
    write; they stay where they are.
    """

    skills_root = global_skill_source_root()
    plugin_root = global_plugin_source_root()
    # #1067: a link at the plugin root or its `mainbranch` folder is not walked.
    plugin_link = global_plugin_root_link()
    # (label, path, owned-file test, Main Branch-named, remove a link at path)
    surfaces: list[tuple[str, Path, Callable[[Path], bool], bool, bool]] = [
        (
            CODEX_LEGACY_GLOBAL_SKILL_NAME,
            skills_root / CODEX_LEGACY_GLOBAL_SKILL_NAME,
            _is_mainbranch_transitional_file,
            True,
            True,
        ),
        *(
            (
                name,
                skills_root / name,
                _is_retired_skill_file(name),
                False,
                # As before: a link here goes only when it leads to Main Branch's skill.
                _is_retired_mainbranch_global_skill(skills_root / name, name),
            )
            for name in CODEX_RETIRED_GLOBAL_SKILL_NAMES
        ),
        *(
            [(str(plugin_root), plugin_root, _is_mainbranch_transitional_file, True, True)]
            if plugin_link is None
            else []
        ),
    ]
    removals: dict[str, list[dict[str, Any]]] = {}
    kept: list[str] = [str(plugin_link)] if plugin_link and plugin_root.exists() else []
    linked = _linked_current_skill_folders()
    kept.extend(
        str(held)
        for name in CODEX_GLOBAL_SKILL_NAMES
        if (held := _held_global_skill_entry(global_skill_file_path(name))) is not None
        and held not in linked
    )
    for label, path, is_owned, main_branch_named, remove_link in surfaces:
        operations, others = _owned_tree_cleanup(path, is_owned, remove_link=remove_link)
        if operations:
            removals[label] = operations
        # A same-name folder with nothing of Main Branch's in it is not ours to report.
        if operations or main_branch_named:
            kept.extend(others)
    return {"removals": removals, "kept": kept}


def _link_note(paths: list[Path]) -> str:
    """A sentence naming the kept entries that are links, or "" (#1067)."""

    links = [str(path) for path in paths if path.is_symlink()]
    if not links:
        return ""
    return (
        " "
        + ", ".join(links)
        + (" is a link" if len(links) == 1 else " are links")
        + "; Main Branch does not follow links, so nothing a link leads to is touched."
    )


def _directory_note(paths: list[Path]) -> str:
    """A sentence naming the kept entries that are folders where a skill file belongs (#1078)."""

    folders = [str(path) for path in paths if path.name == "SKILL.md" and path.is_dir()]
    if not folders:
        return ""
    return (
        " "
        + ", ".join(folders)
        + (" is a folder" if len(folders) == 1 else " are folders")
        + " where a skill file belongs; Main Branch does not write there."
    )


def global_skill_operator_action(
    status: dict[str, Any], *, repo: str | Path | None = None
) -> dict[str, Any] | None:
    """The `operator_actions` entry while old global Codex folders hold unproven files.

    None when every file there is proven to be Main Branch's. Otherwise it
    names each kept file and what a person does with it; the apply removes
    only the proven files (#1062). `repo` names the business repo in the
    command (#1072).
    """

    kept = [str(item) for item in status.get("kept") or []]
    if not kept:
        return None
    effect = global_skill_apply_effect(status)
    command = repair_command(repo)
    reason = (
        "Global Codex folders hold files Main Branch cannot prove it wrote "
        "(your own files, Main Branch files that were changed, or files it cannot read): "
        + ", ".join(kept)
        + ". The repair leaves them where they are."
        + _link_note([Path(item) for item in kept])
        + _directory_note([Path(item) for item in kept])
    )
    manual_step = (
        "Open each file. Move anything you want to keep somewhere of your own, "
        "then delete the rest yourself. "
        f"`{command}` "
        + (
            "deletes only these unchanged Main Branch files: " + ", ".join(effect["removes"])
            if effect["removes"]
            else "deletes no files there"
        )
        + ("; writes these skill files: " + ", ".join(effect["writes"]) if effect["writes"] else "")
        + "; it keeps the files above."
    )
    action = engine_mod.operator_action(command, kept, f"{reason} {manual_step}")
    action.update(
        {
            "id": "codex-global-kept",
            "reason": reason,
            "manual_step": manual_step,
            "on_apply": effect,
        }
    )
    return action


def global_skill_apply_effect(status: dict[str, Any]) -> dict[str, list[str]]:
    """What `--apply --only codex` does to the global Codex folders (#1056)."""

    operations = global_skill_operations()
    return {
        "writes": [str(item["path"]) for item in operations if item["op"] == "write"],
        "removes": [str(item["path"]) for item in operations if item["op"] != "write"],
        "keeps": [str(item) for item in status.get("kept") or []],
    }


def global_skill_operations() -> list[dict[str, Any]]:
    """Every destination `write_global_skill_source` touches, in order (#1012)."""

    operations: list[dict[str, Any]] = []
    for name in CODEX_GLOBAL_SKILL_NAMES:
        path = global_skill_file_path(name)
        if _held_global_skill_entry(path) is not None:
            continue
        expected = render_codex_global_skill_md(name)
        existing = _read_text_or_none(path)
        # #1067: an unreadable file is not proven to be Main Branch's; it stays.
        if existing is not None and existing != expected:
            operations.append({"op": "write", "path": str(path), "content": expected})
    for removals in global_skill_cleanup()["removals"].values():
        operations.extend(removals)
    return operations


def write_global_skill_source() -> dict[str, Any]:
    """Write the global Main Branch Codex skill bundle and remove old surfaces."""

    changed_paths: list[str] = []
    kept = [
        str(path)
        for path in map(global_skill_file_path, CODEX_GLOBAL_SKILL_NAMES)
        if _read_text_or_none(path) is None
    ]
    kept.extend(global_skill_cleanup()["kept"])
    for item in global_skill_operations():
        path = Path(item["path"])
        if item["op"] == "write":
            if (held := _held_global_skill_entry(path)) is not None:
                kept.append(str(held))
                continue
            # Replace the directory entry: a hard-linked file keeps its content.
            atomic_write_text(path, item["content"])
            changed_paths.append(str(path))
        elif (link := _plugin_link_above(path)) is not None:
            kept.append(str(link))  # #1078: a link appeared above the plugin root
        elif _remove_owned_entry(item):
            changed_paths.append(str(path))
        elif path.exists() or path.is_symlink():
            kept.append(str(path))  # #1067: changed since the plan, so it stays
    kept = list(dict.fromkeys(kept))
    status = global_skill_status(Path.cwd())

    return {
        "ok": True,
        "path": str(global_skill_source_root()),
        "skills_root": str(global_skill_source_root()),
        "changed": bool(changed_paths),
        "changed_paths": changed_paths,
        "kept": kept,
        "relative_paths": [f"{name}/SKILL.md" for name in CODEX_GLOBAL_SKILL_NAMES],
        "status": status,
        # #1087 item 6: a current linked folder is reported, not kept.
        **{key: status[key] for key in ("linked", "note") if key in status},
        "safe_to_share": True,
    }


def install_global_skill(repo: str | Path) -> dict[str, Any]:
    """Install or refresh the primary global Codex skill."""

    source = write_global_skill_source()
    final = global_skill_status(repo)
    return {
        "ok": bool(final.get("ok")),
        "source": source,
        "steps": [],
        "status": final,
        "safe_to_share": True,
    }


def plugin_status(repo: str | Path) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    marketplace = marketplace_path(target)
    manifest = plugin_manifest_path(target)
    expected_marketplace = render_codex_marketplace_json()
    expected_manifest = render_codex_plugin_manifest()
    expected_commands = render_codex_slash_commands()

    paths = {
        CODEX_MARKETPLACE_RELATIVE_PATH: marketplace,
        CODEX_PLUGIN_MANIFEST_RELATIVE_PATH: manifest,
        **{
            relative: global_plugin_source_root() / relative
            for relative in CODEX_SLASH_COMMAND_RELATIVE_PATHS
        },
    }
    missing = [relative for relative, path in paths.items() if not path.is_file()]
    stale: list[str] = []
    read_errors: list[str] = []

    expected_by_path = {
        CODEX_MARKETPLACE_RELATIVE_PATH: expected_marketplace,
        CODEX_PLUGIN_MANIFEST_RELATIVE_PATH: expected_manifest,
        **expected_commands,
    }
    missing_markers: list[str] = []
    for relative, path in paths.items():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # #1067: not UTF-8, or not readable: reported, and the cleanup keeps it.
            read_errors.append(f"{relative}: {exc}")
            continue
        if text != expected_by_path[relative]:
            stale.append(relative)
        if relative == CODEX_PLUGIN_MANIFEST_RELATIVE_PATH:
            missing_markers.extend(
                marker for marker in CODEX_PLUGIN_REQUIRED_MARKERS if marker not in text
            )
    legacy_plugin = global_plugin_source_root() / CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH
    if legacy_plugin.exists():
        stale.append(CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH)
    visible_skill_dir = global_plugin_source_root() / CODEX_PLUGIN_DIR_RELATIVE_PATH / "skills"
    if visible_skill_dir.exists():
        stale.append(f"{CODEX_PLUGIN_DIR_RELATIVE_PATH}/skills")
    command_files_current = not any(
        relative in missing or relative in stale for relative in CODEX_SLASH_COMMAND_RELATIVE_PATHS
    )

    ok = not missing and not stale and not read_errors and not missing_markers
    return {
        "ok": ok,
        "exists": not missing,
        "current": not stale and not missing_markers,
        "marketplace_path": CODEX_MARKETPLACE_RELATIVE_PATH,
        "manifest_path": CODEX_PLUGIN_MANIFEST_RELATIVE_PATH,
        "skill_path": "",
        "commands_path": CODEX_PLUGIN_COMMANDS_RELATIVE_PATH,
        "command_files": list(CODEX_SLASH_COMMAND_RELATIVE_PATHS),
        "command_files_current": command_files_current,
        "slash_commands_generated": command_files_current,
        "command_surface_ok": command_files_current,
        "slash_commands_ready": False,
        "missing": missing,
        "stale": stale,
        "missing_markers": missing_markers,
        "read_errors": read_errors,
        "repair": "" if ok else repair_text(target),
        "repair_command": repair_command(target),
        "safe_to_share": True,
    }


def write_global_plugin_source() -> dict[str, Any]:
    """Write the global Main Branch Codex plugin source outside business repos."""

    root = global_plugin_source_root()
    link = global_plugin_root_link()
    if link is not None:
        # #1067: the root, or its `mainbranch` folder, is a person's link.
        return {
            "ok": True,
            "path": str(root),
            "changed": False,
            "changed_paths": [],
            "kept": [str(link)],
            "relative_paths": [],
            "safe_to_share": True,
        }
    marketplace = marketplace_path(root)
    manifest = plugin_manifest_path(root)
    expected_marketplace = render_codex_marketplace_json()
    expected_manifest = render_codex_plugin_manifest()
    expected_commands = render_codex_slash_commands()
    writes = {
        CODEX_MARKETPLACE_RELATIVE_PATH: (marketplace, expected_marketplace),
        CODEX_PLUGIN_MANIFEST_RELATIVE_PATH: (manifest, expected_manifest),
        **{relative: (root / relative, text) for relative, text in expected_commands.items()},
    }
    commands_dir = root / CODEX_PLUGIN_COMMANDS_RELATIVE_PATH
    changed_paths: list[str] = []
    kept: list[str] = []
    for _relative, (path, text) in writes.items():
        # #1062: a symlinked commands/ is a person's; never write or walk through it.
        if path.parent == commands_dir and commands_dir.is_symlink():
            continue
        # #1087: a link that appeared above the plugin root mid-run is not written through.
        if (above := _plugin_link_above(path)) is not None:
            kept.append(str(above))
            continue
        # #1067: never write or walk through a link inside the plugin root.
        link = _symlinked_ancestor(root, path)
        if link is not None:
            kept.append(str(link))
            continue
        existing = _read_text_or_none(path)
        if existing is None:
            kept.append(str(path))  # #1067: unreadable, so not proven; it stays
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if existing != text:
            atomic_write_text(path, text)
            changed_paths.append(str(path))
    # #1056: old plugin folders and unknown command files go only when Main
    # Branch wrote them; anything else stays and is reported as kept.
    for old in (
        root / CODEX_PLUGIN_DIR_RELATIVE_PATH / "skills",
        root / CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH,
    ):
        # #1078: a link at `old` stays, as the plan says; keeping is the safe way.
        operations, others = _owned_tree_cleanup(
            old, _is_mainbranch_transitional_file, remove_link=False, base=root
        )
        kept.extend(others)
        for item in operations:
            if (above := _plugin_link_above(Path(item["path"]))) is not None:
                kept.append(str(above))  # #1078: a link appeared above the plugin root
            elif _remove_owned_entry(item):
                changed_paths.append(item["path"])
            elif Path(item["path"]).exists():
                kept.append(item["path"])  # #1067: changed since the plan
    expected_names = {f"{name}.md" for name in CODEX_SLASH_COMMAND_NAMES}
    if commands_dir.is_symlink():
        kept.append(str(commands_dir))
    elif commands_dir.is_dir() and _symlinked_ancestor(root, commands_dir) is None:
        for path in sorted(commands_dir.iterdir()):
            if path.name in expected_names:
                continue
            if (above := _plugin_link_above(path)) is not None:
                kept.append(str(above))
            elif _unlink_if_proven(path, root):
                changed_paths.append(str(path))
            else:
                kept.append(str(path))
    kept = list(dict.fromkeys(kept))  # a link many paths lead through, once
    return {
        "ok": True,
        "path": str(root),
        "changed": bool(changed_paths),
        "changed_paths": changed_paths,
        "kept": kept,
        "relative_paths": list(writes),
        "safe_to_share": True,
    }


def _remove_generated_tree(path: Path, target: Path) -> bool:
    """Remove a transitional path the plan found to hold only `mb` files.

    A link is removed as a link. A folder is never removed whole: each file is
    checked again and removed only when proven, then folders that are left
    empty go; anything else stays with its folders. Nothing is removed when a
    folder between the repo and `path` has become a link since the plan (#1067).
    """

    if _symlinked_ancestor(target, path) is not None:
        return False
    if path.is_symlink():
        path.unlink()  # the link only, never the tree it points into
        return True
    if path.is_dir():
        for root, dirs, files in os.walk(path, topdown=False):
            base = Path(root)
            for name in files:
                _unlink_if_proven(base / name, target)
            for name in dirs:
                folder = base / name
                if not folder.is_symlink():
                    with contextlib.suppress(OSError):
                        folder.rmdir()  # only an empty folder
        try:
            path.rmdir()
        except OSError:
            return False
        return True
    return path.is_file() and _unlink_if_proven(path, target)


def _transitional_repo_paths() -> tuple[str, ...]:
    return (
        CODEX_PLUGIN_DIR_RELATIVE_PATH,
        CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH,
        CODEX_MARKETPLACE_RELATIVE_PATH,
        CODEX_SKILL_DIR_RELATIVE_PATH,
        ".agents/skills/main-branch",
    )


def _remove_empty_transitional_dirs(target: Path) -> None:
    for maybe_empty in (
        target / ".agents" / "plugins",
        target / ".agents" / "skills",
        target / ".agents",
    ):
        # #1067: a linked folder, or one under a link, is a person's; left alone.
        if maybe_empty.is_symlink() or _symlinked_ancestor(target, maybe_empty) is not None:
            continue
        try:
            if maybe_empty.is_dir() and not any(maybe_empty.iterdir()):
                maybe_empty.rmdir()
        except OSError:
            pass


# The `mb` version a release embedded in its Codex command and skill text, in
# the two sentences that carried it: "by Main Branch `0.3.30`. If runtime ..."
# and "`0.3.30`. If the runtime reports ...". Every release wrote a plain
# X.Y.Z there; anything else in that slot is a person's text and is compared.
_EMBEDDED_VERSION_RE = re.compile(r"`\d+\.\d+\.\d+`(?=\. If (?:the )?runtime )")
_EMBEDDED_VERSION_PLACEHOLDER = "`<mb-version>`"


def generated_file_key(path: Path) -> str:
    """The key a generated Codex file is proven under: its folder and file name."""

    return f"{path.parent.name}/{path.name}"


def normalised_generated_digest(name: str, data: bytes) -> str | None:
    """sha256 of a Codex file's content with what varies per install normalised.

    What varies: the embedded `mb` version (each release wrote its own) and
    line endings (git may check a repo-local copy out with CRLF). JSON
    manifests are compared as parsed data, re-serialised with sorted keys, so
    a formatter's whitespace or key order does not matter while any added,
    removed or changed key or value does. None when the bytes are not UTF-8
    text, or not valid JSON for a `.json` name, or JSON that repeats a key in
    any object (#1067: a JSON reader keeps the last value, which hides the first).
    """

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    text = text.replace("\r\n", "\n")
    if name.endswith(".json"):
        try:
            payload = json.loads(text, object_pairs_hook=_unique_keys)
        except ValueError:  # invalid JSON, or a repeated key
            return None
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    else:
        text = _EMBEDDED_VERSION_RE.sub(_EMBEDDED_VERSION_PLACEHOLDER, text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A JSON object's pairs as a dict; a key that appears twice is refused (#1067)."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


@lru_cache(maxsize=1)
def _current_generated_digests() -> dict[str, frozenset[str]]:
    """Digests of what this `mb` writes that an old Codex path may hold a copy of.

    The global plugin source files, and the `main-branch` skill (the
    repo-local `.agents/skills/main-branch` path held a copy of it).
    """

    rendered = {
        CODEX_MARKETPLACE_RELATIVE_PATH: render_codex_marketplace_json(),
        CODEX_PLUGIN_MANIFEST_RELATIVE_PATH: render_codex_plugin_manifest(),
        **render_codex_slash_commands(),
        CODEX_GLOBAL_SKILL_RELATIVE_PATH: render_codex_global_skill_md(CODEX_GLOBAL_SKILL_NAME),
    }
    digests: dict[str, set[str]] = {}
    for relative, text in rendered.items():
        path = Path(relative)
        digest = normalised_generated_digest(path.name, text.encode("utf-8"))
        if digest is not None:
            digests.setdefault(generated_file_key(path), set()).add(digest)
    return {key: frozenset(values) for key, values in digests.items()}


def _is_known_generated_content(path: Path) -> bool:
    """Whether the file at `path` (a link is read through) is a known generated version."""

    try:
        data = path.read_bytes()
    except OSError:
        return False
    digest = normalised_generated_digest(path.name, data)
    if digest is None:
        return False
    key = generated_file_key(path)
    if digest in KNOWN_FILE_DIGESTS.get(key, frozenset()):
        return True
    return digest in _current_generated_digests().get(key, frozenset())


def _is_mainbranch_transitional_file(path: Path) -> bool:
    """Whether this file at an old Codex path is proven to be one `mb` wrote.

    Proof is content, not name: the file must equal, after normalising what
    varies per install, a version a released `mb` wrote at that path (the
    frozen digests in `mb.codex_known_files`) or what this `mb` renders. A
    person's look-alike, a renamed file or a generated file with additions is
    not proven and stays. A symlink is never proven.
    """

    if path.is_symlink() or not path.is_file():
        return False
    return _is_known_generated_content(path)


def _transitional_cleanup(target: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Removals for the transitional repo-local Codex paths, and the files kept.

    A path is removed whole only when every file in it is one `mb` wrote. When
    a person's file sits inside, only the `mb` files are removed one by one and
    the person's files (and their folders) stay (#1052). A symlink at a
    transitional path is removed as a link, never followed.
    """

    operations: list[dict[str, Any]] = []
    kept: list[str] = []
    for relative in _transitional_repo_paths():
        candidate = target / relative
        # #1067: a linked folder above the path (`.agents/` or one under it) is
        # a person's; nothing under it is walked or removed, and the link is kept.
        link = _symlinked_ancestor(target, candidate)
        if link is not None:
            if candidate.exists() or candidate.is_symlink():
                kept.append(link.relative_to(target).as_posix())
            continue
        # #1056: a symlink, live or dangling, is removed as a link, never followed.
        if candidate.is_symlink() or (
            candidate.is_file() and _is_mainbranch_transitional_file(candidate)
        ):
            operations.append({"op": "delete_tree", "path": str(candidate), "rel": relative})
            continue
        if candidate.is_file():
            kept.append(relative)
            continue
        if not candidate.is_dir():
            continue
        owned: list[Path] = []
        person: list[Path] = []
        for root, dirs, files in os.walk(candidate):
            base = Path(root)
            for entry in [*files, *(name for name in dirs if (base / name).is_symlink())]:
                path = base / entry
                (owned if _is_mainbranch_transitional_file(path) else person).append(path)
        if not person:
            operations.append({"op": "delete_tree", "path": str(candidate), "rel": relative})
            continue
        kept.extend(sorted(path.relative_to(target).as_posix() for path in person))
        operations.extend(
            {"op": "delete", "path": str(path), "rel": path.relative_to(target).as_posix()}
            for path in sorted(owned)
        )
    return operations, list(dict.fromkeys(kept))


def _remove_transitional_file(path: Path, target: Path) -> bool:
    """Remove one `mb` file, then any folders it leaves empty, up to the repo."""

    if not _unlink_if_proven(path, target):
        return False
    parent = path.parent
    while parent != target and target in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return True


def _apply_transitional_operation(item: dict[str, Any], target: Path) -> bool:
    path = Path(item["path"])
    if item["op"] == "delete":
        return _remove_transitional_file(path, target)
    return _remove_generated_tree(path, target)


def remove_repo_local_codex_plugin_files(repo: str | Path) -> list[str]:
    """Remove generated repo-local Codex plugin files from the transitional model.

    Only files `mb` wrote are removed; a person's files stay (#1052).
    """

    target = Path(repo).expanduser().resolve()
    removed: list[str] = []
    operations, _kept = _transitional_cleanup(target)
    for item in operations:
        if _apply_transitional_operation(item, target):
            removed.append(str(item["rel"]))
    _remove_empty_transitional_dirs(target)
    return removed


def skill_status(repo: str | Path) -> dict[str, Any]:
    skill = global_skill_status(repo)
    return {
        "ok": bool(skill["ok"]),
        "exists": bool(skill["exists"]),
        "current": bool(skill["current"]),
        "path": skill["path"],
        "absolute_path": skill["absolute_path"],
        "inventory_path": CODEX_WORKFLOW_INVENTORY_RELATIVE_PATH,
        "missing_markers": skill["missing_markers"],
        "global_skill": skill,
        "plugin": plugin_status(repo),
        "read_error": skill["read_error"],
        "repair": skill["repair"],
        "repair_command": repair_command(repo),
        "deprecated": False,
        "summary": ("The global Main Branch Codex skill is the supported Codex surface."),
        "safe_to_share": True,
    }


def instructions_status(repo: str | Path) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    path = agents_path(target)
    expected = render_agents_md(target)
    exists = path.is_file()
    try:
        text = path.read_text(encoding="utf-8") if exists else ""
    except OSError as exc:
        text = ""
        read_error = str(exc)
    else:
        read_error = ""
    managed_text = _managed_agents_content(text)
    status_text = managed_text or text
    missing_commands = [command for command in REQUIRED_FACT_COMMANDS if command not in status_text]
    approval_ok = "explicit operator approval" in status_text
    slash_ok = "Do not pretend Claude Code slash skills work in Codex." in status_text
    missing_lifecycle_guidance = [
        marker for marker in REQUIRED_LIFECYCLE_GUIDANCE_MARKERS if marker not in status_text
    ]
    for heading, markers in REQUIRED_LIFECYCLE_SECTION_MARKERS:
        section = _markdown_section(status_text, heading)
        missing_lifecycle_guidance.extend(marker for marker in markers if marker not in section)
    missing_lifecycle_guidance = list(dict.fromkeys(missing_lifecycle_guidance))
    lifecycle_discovery_ok = bool(exists and not missing_lifecycle_guidance)
    guidance_metadata = parse_guidance_metadata(status_text) if exists else {}
    expected_template_hash = guidance_template_hash()
    expected_guidance_metadata = guidance_metadata_comment(template_hash=expected_template_hash)
    guidance_schema_ok = guidance_metadata.get("schema") == str(CODEX_GUIDANCE_SCHEMA)
    guidance_template_hash_ok = guidance_metadata.get("template_hash") == expected_template_hash
    guidance_min_mb_ok = guidance_metadata.get("min_mb") == CODEX_GUIDANCE_MIN_MB
    guidance_metadata_ok = bool(
        exists and guidance_schema_ok and guidance_template_hash_ok and guidance_min_mb_ok
    )
    fact_grounding_ok = bool(
        exists and not missing_commands and approval_ok and slash_ok and lifecycle_discovery_ok
    )
    skill = skill_status(target)
    repo_local_plugin_paths = [
        relative
        for relative in (
            CODEX_SKILL_DIR_RELATIVE_PATH,
            ".agents/skills/main-branch",
            CODEX_MARKETPLACE_RELATIVE_PATH,
            CODEX_PLUGIN_DIR_RELATIVE_PATH,
            CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH,
        )
        if (target / relative).exists() or (target / relative).is_symlink()
    ]
    template_match = bool(exists and status_text == expected)
    current = bool(fact_grounding_ok and guidance_metadata_ok and not repo_local_plugin_paths)
    return {
        "ok": current,
        "exists": exists,
        "current": current,
        "template_match": template_match,
        "fact_grounding_ok": fact_grounding_ok,
        "guidance_metadata_ok": guidance_metadata_ok,
        "guidance_schema_ok": guidance_schema_ok,
        "guidance_template_hash_ok": guidance_template_hash_ok,
        "guidance_min_mb_ok": guidance_min_mb_ok,
        "guidance_metadata": guidance_metadata,
        "expected_guidance_metadata": expected_guidance_metadata,
        "expected_template_hash": expected_template_hash,
        "guidance_min_mb": CODEX_GUIDANCE_MIN_MB,
        "generated_version_ok": guidance_metadata_ok,
        "expected_version_marker": "",
        "path": AGENTS_RELATIVE_PATH,
        "absolute_path": str(path),
        "missing_fact_commands": missing_commands,
        "missing_lifecycle_guidance": missing_lifecycle_guidance,
        "repo_local_plugin_paths": repo_local_plugin_paths,
        "lifecycle_discovery_ok": lifecycle_discovery_ok,
        "skill": skill,
        "workflow_inventory": workflow_inventory(),
        "approval_boundary_ok": approval_ok,
        "codex_native_ok": slash_ok,
        "repair": "" if current else repair_text(target),
        "repair_command": repair_command(target),
        "read_error": read_error,
        "safe_to_share": True,
    }


def _login_shell_mb_diagnostics() -> dict[str, Any]:
    return engine_mod.login_shell_mb_diagnostics()


def readiness(repo: str | Path) -> dict[str, Any]:
    executable = executable_status()
    instructions = instructions_status(repo)
    static_ok = bool(executable["found"] and instructions["ok"])
    runtime = _login_shell_mb_diagnostics()
    runtime_ok = bool(runtime.get("ok"))
    global_skill = global_skill_status(repo)
    global_skill_ok = bool(global_skill.get("ok"))
    plugin_install = {
        "checked": False,
        "ok": False,
        "state": "legacy_plugin_not_checked",
        "summary": "Codex plugin commands are legacy/experimental and not part of readiness.",
        "plugin_installed": False,
        "plugin_enabled": False,
        "command_files_current": False,
        "command_surface_ok": False,
        "slash_commands_ready": False,
        "slash_commands_likely_loaded": False,
        "slash_commands_restart_required": False,
        "repair": "",
        "safe_to_share": True,
    }
    plugin_ok = False
    slash_commands_ready = False
    command_surface_ok = global_skill_ok
    generated_guidance_ready = bool(instructions["ok"] and global_skill_ok)
    ok = bool(static_ok and runtime_ok and global_skill_ok)
    if ok:
        status = "ready"
    elif not executable["found"] or not instructions["ok"]:
        status = "needs_setup"
    elif runtime.get("mismatch"):
        status = "runtime_mismatch"
    elif runtime_ok and not global_skill_ok:
        status = str(global_skill.get("state") or "global_skill_missing_or_stale")
    else:
        status = "runtime_unverified"
    return {
        "ok": ok,
        "status": status,
        "support_level": CODEX_SUPPORT_LEVEL,
        "static_ok": static_ok,
        "runtime_ok": runtime_ok,
        "plugin_ok": plugin_ok,
        "global_skill_ok": global_skill_ok,
        "generated_guidance_ready": generated_guidance_ready,
        "command_surface_ok": command_surface_ok,
        "slash_commands_ready": slash_commands_ready,
        "global_skill": global_skill,
        "plugin_install": plugin_install,
        "runtime": runtime,
        "executable": executable,
        "instructions": instructions,
        "skill": instructions["skill"],
        "plugin": instructions["skill"]["plugin"],
        "workflow_inventory": workflow_inventory(),
        "fact_commands": list(REQUIRED_FACT_COMMANDS),
        "repair": ""
        if ok
        else (
            str(runtime.get("repair") or "")
            if static_ok and not runtime_ok
            else str(global_skill.get("repair") or "")
            if static_ok and runtime_ok and not global_skill_ok
            else instructions["repair"] or executable["repair"]
        ),
        "start_command": f"codex -C {shlex.quote(str(Path(repo).expanduser().resolve()))}",
        "smoke_command": (
            "codex exec --json --ephemeral --sandbox read-only "
            "-c 'approval_policy=\"never\"' "
            f"-C {shlex.quote(str(Path(repo).expanduser().resolve()))} "
            "'Start this Main Branch business day. Run only read-only mb checks "
            "and do not edit files.'"
        ),
        "safe_to_share": True,
    }


def human_readiness_label(readiness_report: dict[str, Any]) -> str:
    """Return a short user-facing Codex readiness label."""

    if readiness_report.get("ok"):
        return "ready"
    executable = readiness_report.get("executable") or {}
    if not executable.get("found"):
        return "missing"
    instructions = readiness_report.get("instructions") or {}
    if not instructions.get("ok"):
        return "needs setup"
    runtime = readiness_report.get("runtime") or {}
    if runtime.get("mismatch"):
        return "runtime mismatch"
    if not runtime.get("ok"):
        return "runtime unverified"
    global_skill = readiness_report.get("global_skill") or {}
    if not global_skill.get("ok"):
        return "skill not ready"
    plugin_install = readiness_report.get("plugin_install") or {}
    if not plugin_install.get("ok"):
        return "plugin optional"
    return "not ready"


def agents_md_plan(
    repo: str | Path,
    *,
    name: str = "",
    gh_username: str = "",
) -> dict[str, Any]:
    """What `write_agents_md` would do, what it refuses, and what it leaves (#1052).

    `operations` lists every destination it touches, in order (#1012): the
    AGENTS.md write, then each transitional repo-local Codex path or file it
    removes. `refused` names an AGENTS.md it will not touch, with the reason
    and the manual step; then nothing is written at all. `kept` lists the
    person's files left in transitional paths.
    """

    target = Path(repo).expanduser().resolve()
    path = agents_path(target)
    if path.is_dir():
        # #1072: a folder where the file belongs is not ours to read or replace.
        return {
            "operations": [],
            "refused": [
                _agents_refusal(
                    "is_directory",
                    "AGENTS.md is a folder, not a file, so Main Branch cannot read or "
                    "write the Codex guidance there. It left everything unchanged.",
                    "Move or rename the AGENTS.md folder (or merge what it holds into a "
                    f"file of your own), {_agents_rerun_step(target)}",
                )
            ],
            "kept": [],
        }
    rendered = render_agents_md(target, name=name, gh_username=gh_username)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    updated, refusal = _merge_agents_md(existing, rendered, _agents_rerun_step(target))
    if refusal is not None:
        return {"operations": [], "refused": [refusal], "kept": []}
    operations: list[dict[str, Any]] = []
    if existing != updated:
        operations.append(
            {"op": "write", "path": str(path), "rel": AGENTS_RELATIVE_PATH, "content": updated}
        )
    removals, kept = _transitional_cleanup(target)
    operations.extend(removals)
    return {"operations": operations, "refused": [], "kept": kept}


def agents_md_operations(
    repo: str | Path,
    *,
    name: str = "",
    gh_username: str = "",
) -> list[dict[str, Any]]:
    """Every destination `write_agents_md` touches, in order (#1012)."""

    return list(agents_md_plan(repo, name=name, gh_username=gh_username)["operations"])


def agents_md_operator_action(
    plan: dict[str, Any], *, repo: str | Path | None = None
) -> dict[str, Any] | None:
    """The `operator_actions` entry while the Codex AGENTS.md repair needs a person.

    None when the plan only replaces Main Branch's own guidance. Otherwise it
    names the reason and the manual step (#1052). `repo` names the business
    repo in the command (#1072).
    """

    refused = plan.get("refused") or []
    kept = plan.get("kept") or []
    effect = agents_md_apply_effect(plan)
    command = repair_command(repo)
    base = Path(repo).expanduser().resolve() if repo is not None else None
    if refused:
        reason = str(refused[0]["reason"])
        manual_step = str(refused[0]["manual_step"])
        changes = [AGENTS_RELATIVE_PATH]
    elif kept:
        reason = (
            "Old repo-local Codex folders hold files Main Branch cannot prove it wrote "
            "(your own files, or Main Branch files that were changed): "
            + ", ".join(kept)
            + ". The repair removes only unchanged Main Branch files and leaves these."
            + (_link_note([base / item for item in kept]) if base is not None else "")
        )
        # #1056: name exactly what an apply does, so the plan and the apply agree.
        removes = effect["removes"]
        manual_step = (
            "Open each file. Move anything you want to keep somewhere of your own, "
            "then delete the rest yourself. "
            f"`{command}` (or `--all-agents`) "
            + ("rewrites AGENTS.md, " if effect["writes"] else "")
            + (
                "deletes only these Main Branch files: " + ", ".join(removes)
                if removes
                else "deletes no files"
            )
            + "; it keeps the files above."
        )
        changes = [str(item["rel"]) for item in plan.get("operations", [])]
    else:
        return None
    action = engine_mod.operator_action(command, changes, f"{reason} {manual_step}")
    action.update(
        {
            "id": "codex-agents-md",
            "reason": reason,
            "manual_step": manual_step,
            "on_apply": effect,
        }
    )
    return action


def agents_md_apply_effect(plan: dict[str, Any]) -> dict[str, list[str]]:
    """What `--apply --only codex` or `--all-agents` does with this plan (#1056).

    The apply runs `write_agents_md`, which follows the same plan: a refusal
    writes and deletes nothing; otherwise it rewrites AGENTS.md when the plan
    says so, deletes exactly the planned Main Branch paths and keeps the rest.
    """

    if plan.get("refused"):
        return {"writes": [], "removes": [], "keeps": []}
    operations = plan.get("operations") or []
    return {
        "writes": [str(item["rel"]) for item in operations if item["op"] == "write"],
        "removes": [str(item["rel"]) for item in operations if item["op"] != "write"],
        "keeps": [str(item) for item in plan.get("kept") or []],
    }


def write_agents_md(
    repo: str | Path,
    *,
    name: str = "",
    gh_username: str = "",
) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    plan = agents_md_plan(target, name=name, gh_username=gh_username)
    changed_paths: list[str] = []
    kept = list(plan["kept"])
    for item in plan["operations"]:
        if item["op"] == "write":
            atomic_write_text(Path(item["path"]), item["content"])
            changed_paths.append(AGENTS_RELATIVE_PATH)
        elif _apply_transitional_operation(item, target):
            changed_paths.append(f"removed:{item['rel']}")
        elif Path(item["path"]).exists():
            kept.append(str(item["rel"]))  # #1067: changed since the plan, so it stays
    if not plan["refused"]:
        _remove_empty_transitional_dirs(target)
    return {
        "ok": not plan["refused"],
        "path": AGENTS_RELATIVE_PATH,
        "changed": bool(changed_paths),
        "changed_paths": changed_paths,
        "refused": plan["refused"],
        "kept": kept,
        "status": instructions_status(target),
    }
