"""Qualify doctor repair commands with their business repository."""

from __future__ import annotations

import copy
import re
import shlex
from pathlib import Path
from typing import Any

from mb import engine as engine_mod

_REPO_FLAG_COMMANDS = (
    "mb doctor repair",
    "mb update",
    "mb validate",
    "mb checkpoint",
    "mb skill link",
    "mb skill repair",
    "mb migrate",
    "mb onboard status",
    "mb spine declare",
    "mb spine show",
    "mb spine init",
)
_REPO_POSITIONAL_COMMANDS = ("mb status", "mb graph")
_COMMAND_KEYS = {"command", "repair_command", "update_check_command"}
_COMMAND_LIST_KEYS = {"scope_choices", "apply_choices"}
_RUN_TAIL = re.compile(r"(\bthen run |^(?:claude|codex): run )(mb .+)$")
_BACKTICKED_MB = re.compile(r"`(mb [^`]+)`")
_REDIRECT_WORD = re.compile(r"^\d*[<>]")


def _shell_words(text: str) -> list[tuple[int, int, str]] | None:
    """Split one command segment into (start, end, value) words, or None if unbalanced."""
    words: list[tuple[int, int, str]] = []
    index, size = 0, len(text)
    while index < size:
        if text[index].isspace():
            index += 1
            continue
        start, value, quote = index, "", ""
        while index < size and (quote or not text[index].isspace()):
            char = text[index]
            if quote:
                if char == quote:
                    quote = ""
                elif char == "\\" and quote == '"' and index + 1 < size:
                    index += 1
                    value += text[index]
                else:
                    value += char
            elif char in "'\"":
                quote = char
            elif char == "\\" and index + 1 < size:
                index += 1
                value += text[index]
            else:
                value += char
            index += 1
        if quote:
            return None
        words.append((start, index, value))
    return words


def _unsupported_shell_syntax(command: str) -> bool:
    """Refuse constructs the command lexer cannot safely split or rewrite."""
    if "\\\n" in command:
        return True
    quote = ""
    escaped = False
    word_start = True
    for index, char in enumerate(command):
        if quote == "'":
            if char == quote:
                quote = ""
            continue
        pair = command[index : index + 2]
        if char == "`" or pair in {"$(", "${"}:
            return True
        if escaped:
            escaped = False
            if char != "\n":
                word_start = False
            continue
        if char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = ""
        elif char in "'\"":
            quote = char
            word_start = False
        elif pair in {"<<", "<(", ">("} or (char == "#" and word_start):
            return True
        else:
            word_start = char.isspace() or char in ";|&<>()"
    return False


def _command_segments(command: str) -> list[tuple[int, int]] | None:
    """Spans of a command line between unquoted `&&`, `||`, `|`, `;`, `&` and newlines."""
    spans: list[tuple[int, int]] = []
    begin, index, size, quote = 0, 0, len(command), ""
    while index < size:
        char = command[index]
        if quote:
            if char == "\\" and quote == '"':
                index += 1
            elif char == quote:
                quote = ""
        elif char == "\\":
            index += 1
        elif char in "'\"":
            quote = char
        elif char in ";\n|" or (
            char == "&"
            and command[index - 1 : index] not in {">", "<"}
            and command[index + 1 : index + 2] != ">"
        ):
            spans.append((begin, index))
            while index + 1 < size and command[index + 1] in "&|":
                index += 1
            begin = index + 1
        index += 1
    if quote:
        return None
    spans.append((begin, size))
    return spans


def _qualify_segment(text: str, repo_arg: str, repo_text: str) -> str:
    """One `mb ...` segment, naming the repo exactly once (idempotent).

    Only the repo flag or path is spliced in; every other byte is kept.
    """
    words = _shell_words(text)
    if not words or words[0][2] != "mb":
        return text
    values = [value for _, _, value in words]
    for index, value in enumerate(values):
        if value in {"--repo", "--business-repo"}:
            if index + 1 >= len(values):
                return text  # dangling: never a second flag
            if values[index + 1] != ".":
                return text  # already names a repo
            if value == "--business-repo" and not repo_arg:
                return text  # the repo is the current folder: `.` already names it
            start = words[index - 1][1]
            end = words[index + 1][1]
            flag = repo_arg.replace("--repo", value, 1).strip() if repo_arg else ""
            return text[:start] + (f" {flag}" if flag else "") + text[end:]
        if value.startswith(("--repo=", "--business-repo=")):
            return text
    if values[:2] in (["mb", "status"], ["mb", "graph"]) or values[:3] in (
        ["mb", "books", "status"],
        ["mb", "books", "doctor"],
    ):
        if not repo_arg or repo_text in values:
            return text
        quoted = shlex.quote(repo_text)
        for position, (_, _, value) in enumerate(words):
            if _REDIRECT_WORD.match(value):
                return (
                    text[: words[position - 1][1]] + f" {quoted}" + text[words[position - 1][1] :]
                )
        return text[: words[-1][1]] + f" {quoted}" + text[words[-1][1] :]
    for prefix in _REPO_FLAG_COMMANDS:
        count = len(prefix.split())
        if values[:count] == prefix.split():
            if not repo_arg:
                return text
            return text[: words[count - 1][1]] + f" {repo_arg}" + text[words[count - 1][1] :]
    return text


def _qualify_command(command: str, repo: Path) -> str:
    """Name the business repo in every `mb` command of a suggested command line (#1072).

    Decided on words, never substrings, so a repo path that itself contains
    ` --repo . `, ` && ` or `mb status` is quoted once and left alone. `--repo .`
    becomes the shared rule's flag; a command with no repo gains it; `mb status`
    and `mb graph` take the path as an argument. A command that already names a
    repo (flag or trailing path) and anything that is not an `mb` command are
    kept, so running this twice changes nothing. Only the `mb` segments are
    edited (#1083): pipes, `;`, redirects, `$VAR`, globs and `~` in the rest of
    the line keep every byte, and a dangling `--repo` is left alone. Lines with
    substitutions, heredocs, herestrings, comments or a backslash line continuation
    are left exactly as written.
    """
    if _unsupported_shell_syntax(command):
        return command
    spans = _command_segments(command)
    if spans is None or not command.strip():
        return command
    repo_arg = engine_mod.repo_flag(repo).strip()
    repo_text = str(Path(repo).expanduser().resolve())
    pieces: list[str] = []
    cursor = 0
    for start, end in spans:
        pieces.append(command[cursor:start])
        pieces.append(_qualify_segment(command[start:end], repo_arg, repo_text))
        cursor = end
    pieces.append(command[cursor:])
    return "".join(pieces)


def _qualify_field(value: str, repo: Path) -> str:
    """A command field, manual run tail, or explicitly labelled skipped-surface step."""
    qualified = _qualify_command(value, repo)
    if qualified != value:
        return qualified
    match = _RUN_TAIL.search(value)
    if match is None:
        return value
    return value[: match.start(2)] + _qualify_command(match.group(2), repo)


def _qualify_run_commands(checks: list[dict[str, Any]], update: dict[str, Any], repo: Path) -> None:
    """Name the repo in the command fields `mb doctor` itself emits (#1083).

    Only the fields doctor owns: repair commands, migration findings, version
    and campaign prose, and the update object's own commands. Nested status
    blocks keep the text their source provides.
    """
    for check in checks:
        if check.get("name") in {"mainbranch-version", "legacy-campaigns"}:
            check["detail"] = _qualify_prose(check["detail"], repo)
        if isinstance(check.get("repair_command"), str):
            check["repair_command"] = _qualify_field(check["repair_command"], repo)
        for finding in check.get("findings") or []:
            if isinstance(finding.get("repair_command"), str):
                finding["repair_command"] = _qualify_field(finding["repair_command"], repo)
    for key in ("command", "update_check_command"):
        if isinstance(update.get(key), str):
            update[key] = _qualify_field(update[key], repo)


def _qualify_prose(text: str, repo: Path) -> str:
    """Name the repo in each backticked `mb ...` command of a sentence; the rest is kept."""
    return _BACKTICKED_MB.sub(lambda m: f"`{_qualify_command(m.group(1), repo)}`", text)


def _qualify_validation_report(report: dict[str, Any], repo: Path) -> dict[str, Any]:
    """A copy of the validation summary whose repair prose names the repo (#1083).

    The report is shared with `raw.validation`, which stays verbatim, so this
    never edits it in place.
    """
    qualified = copy.deepcopy(report)
    legacy = qualified.get("legacy_repair")
    if isinstance(legacy, dict) and isinstance(legacy.get("next_steps"), list):
        legacy["next_steps"] = [
            _qualify_prose(step, repo) if isinstance(step, str) else step
            for step in legacy["next_steps"]
        ]
    categories = qualified.get("validation_categories")
    if not isinstance(categories, dict):
        return qualified
    for key in ("top_repair", "top_operator_summary"):
        if isinstance(categories.get(key), str):
            categories[key] = _qualify_prose(categories[key], repo)
    for entry in (categories.get("by_category") or {}).values():
        for key in ("repair", "operator_summary"):
            if isinstance(entry.get(key), str):
                entry[key] = _qualify_prose(entry[key], repo)
    return qualified


def _qualify_report(node: Any, repo: Path, seen: set[int] | None = None) -> None:
    """Rewrite every suggested-command field of a report in place, once per object.

    `raw` and `result` are verbatim diagnostic copies and are never rewritten.
    """
    seen = set() if seen is None else seen
    if id(node) in seen:
        return  # doctor shares one action dict between `actions[]` and `sections[]`
    seen.add(id(node))
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _COMMAND_KEYS and isinstance(value, str):
                node[key] = _qualify_field(value, repo)
            elif key in _COMMAND_LIST_KEYS and isinstance(value, list):
                node[key] = [_qualify_command(str(item), repo) for item in value]
            elif key == "skipped_surfaces" and isinstance(value, list):
                node[key] = [_qualify_field(str(item), repo) for item in value]
            elif key not in {"raw", "result"}:
                _qualify_report(value, repo, seen)
    elif isinstance(node, list):
        for item in node:
            _qualify_report(item, repo, seen)
