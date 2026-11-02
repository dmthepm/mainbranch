"""Human rendering of doctor repair reports."""

from __future__ import annotations

from typing import Any


def render_repair(report: dict[str, Any]) -> None:
    """Print the doctor repair plan/apply report for humans."""
    from rich.console import Console

    console = Console()
    if report.get("guard") == "not_business_folder":
        console.print("\n[bold]mb doctor repair[/bold]")
        console.print(f"repo: {report['repo']}\n")
        console.print(f"  [blue]info[/blue]  {report['plan_interpretation']['summary']}")
        return
    mode = "read-only plan" if report["read_only"] else "apply summary"
    console.print(f"\n[bold]mb doctor repair[/bold]  {mode}")
    if report.get("only"):
        console.print(f"scope: {report['only']}")
    elif report.get("all_agents"):
        console.print("scope: all agent surfaces")
    console.print(f"repo: {report['repo']}\n")
    for section in report["sections"]:
        state = str(section["state"])
        mark = {
            "ok": "[green]ok[/green]",
            "info": "[blue]info[/blue]",
            "warn": "[yellow]warn[/yellow]",
            "error": "[red]error[/red]",
        }.get(state, "[red]error[/red]")
        console.print(f"  {mark}  [bold]{section['title']}[/bold] - {section['summary']}")
        for check in section.get("checks", [])[:6]:
            check_state = str(check.get("state", "ok"))
            if check_state == "ok":
                prefix = "ok"
            elif check_state == "info":
                prefix = "info"
            elif check_state == "warn":
                prefix = "warn"
            else:
                prefix = "error"
            console.print(f"       {prefix:<5} {check['name']}: {check['summary']}")
    if report.get("applied_actions"):
        console.print("\n[bold]Applied safe repairs[/bold]")
        for action in report["applied_actions"]:
            console.print(f"  - {action['title']}: {action['command']}")
        receipt = report.get("receipt", {})
        touched = receipt.get("touched_files", []) if isinstance(receipt, dict) else []
        installed = receipt.get("installed_skills", []) if isinstance(receipt, dict) else []
        if touched:
            console.print("  touched: " + ", ".join(str(item) for item in touched[:8]))
        if installed:
            console.print("  installed Codex skills: " + ", ".join(str(item) for item in installed))
    if report.get("agent_surfaces"):
        console.print("\n[bold]Agent surfaces[/bold]")
        for surface in report["agent_surfaces"].get("surfaces", []):
            files = surface.get("touched_files", [])
            console.print(
                f"  - {surface['label']}: {surface['state']} "
                f"({len(surface.get('planned_actions', []))} action(s))"
            )
            if files:
                console.print("    would touch: " + ", ".join(str(item) for item in files[:8]))
    if report["actions"]:
        console.print("\n[bold]Repair plan[/bold]")
        for action in report["actions"]:
            mutability = "read-only" if action["mode"] == "read" else action["mode"]
            safe = "safe apply" if action["safe_to_apply"] else "manual approval"
            console.print(f"  - [{mutability}; {safe}] {action['title']}")
            console.print(f"    command: {action['command']}")
            console.print(f"    why: {action['reason']}")
    else:
        console.print("\n[green]No repair actions needed.[/green]")
    if report.get("operator_actions"):
        console.print("\n[bold]For you to run[/bold]")
        for item in report["operator_actions"]:
            console.print(f"  - {item['command']}", markup=False)
            if item.get("note"):
                console.print(f"    {item['note']}", markup=False)
    console.print("\n[bold]After apply[/bold]")
    console.print(f"  structural: {report['post_apply']['structural_verification']}")
    console.print(f"  validation: {report['post_apply']['validation_frontmatter_debt']}")
    console.print(f"  runtime: {report['post_apply']['runtime_smoke_required']}")
    console.print("  git:")
    for command in report["post_apply"]["git_review"]:
        console.print(f"    {command}")
