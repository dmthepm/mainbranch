"""Text rendering for connect command results."""

from __future__ import annotations

from typing import Any

from mb.connect_registry import (
    BACKEND_FAILURE_STATE,
    GOOGLE_OAUTH_PRODUCTS,
    GOOGLE_REAUTH_REQUIRED_STATE,
    NOT_CHECKED_STATE,
    UNVERIFIED_STATE,
)


def render_identity(result: dict[str, Any]) -> None:
    print(f"mb connect identity  {result['repo']}")
    print(result["summary"])
    for item in result["providers"]:
        mark = "ok" if item["complete"] else "warn"
        print(f"  {mark}  {item['provider']}")
        for field, value in item["identity"].items():
            shown = value if value else "(unrecorded)"
            print(f"        {field}: {shown}")


def render_list(result: dict[str, Any]) -> None:
    for provider in result["providers"]:
        print(
            f"{provider['id']:<14} {provider['state']:<14} "
            f"{provider['auth']:<22} {provider['description']}"
        )


def render_plan(result: dict[str, Any]) -> None:
    print(f"mb connect plan  {result['repo']}")
    print("Choose the provider that matches the business job in front of you:")
    for index, step in enumerate(result["steps"], start=1):
        state = "ready" if step["ready"] else step["state"]
        print(f"{index}. {step['name']} ({state})")
        print(f"   why: {step['why']}")
        print(f"   use when: {step['use_when']}")
        if not step["ready"]:
            print(f"   next: {step['next_command']}")


def state_label(state: str) -> str:
    """Human phrasing for a provider state. JSON keeps the machine value."""
    if state == NOT_CHECKED_STATE:
        return "not checked"
    return "stored, unverified" if state == UNVERIFIED_STATE else state


def render_status(result: dict[str, Any]) -> None:
    from mb import connect

    summary = result["summary"]
    print(f"mb connect status  {result['repo']}")
    line = (
        f"configured: {summary['configured']}  "
        f"healthy: {summary['healthy']}  needs repair: {summary['needs_repair']}"
    )
    if summary.get("unverified"):
        line += f"  unverified: {summary['unverified']}"
    if summary.get("not_checked"):
        line += f"  not checked: {summary['not_checked']}"
    print(line)
    github = result.get("github") or {}
    if github:
        state = "ok" if github.get("ok") else "warn"
        print(f"  {state}  github: {github.get('state')}")
        if github.get("repair_command"):
            print(f"       next: {github['repair_command']}")
    if not result["providers"]:
        print("no providers connected")
        return
    for item in result["providers"]:
        state = "ok" if item["ok"] else "warn"
        label = f" ({item['account_label']})" if item["account_label"] else ""
        print(f"  {state}  {item['provider']}{label}: {connect.state_label(item['state'])}")
        if item["repair_command"]:
            print(f"       next: {item['repair_command']}")


def render_provider_status(result: dict[str, Any]) -> None:
    from mb import connect

    state = "ok" if result["ok"] else "warn"
    label = f" ({result['account_label']})" if result["account_label"] else ""
    print(
        f"mb connect status {result['provider']}{label}: {state} "
        f"({connect.state_label(result['state'])})"
    )
    if result.get("summary"):
        print(f"summary: {result['summary']}")
    if result.get("credential_mode") == "oauth":
        connect._render_google_products(result)
    if result.get("repair_command"):
        print(f"next: {result['repair_command']}")


def _render_google_products(result: dict[str, Any]) -> None:
    """One line per Google product: granted or not, and its last recorded check."""

    raw_oauth = result.get("oauth")
    grants = raw_oauth.get("grants") if isinstance(raw_oauth, dict) else None
    granted = set(grants) if isinstance(grants, list) else set()
    raw_validation = result.get("validation")
    raw_products = raw_validation.get("products") if isinstance(raw_validation, dict) else None
    products = raw_products if isinstance(raw_products, dict) else {}
    # A read that Google refused records reauth_required without product checks.
    unchecked = (
        "not checked since the sign-in expired"
        if result.get("state") == GOOGLE_REAUTH_REQUIRED_STATE
        else "not checked yet"
    )
    for name in GOOGLE_OAUTH_PRODUCTS:
        if name not in granted:
            print(f"  {name}: not granted")
            continue
        raw_product = products.get(name)
        product: dict[str, Any] = raw_product if isinstance(raw_product, dict) else {}
        state = product.get("state")
        if not state or state == "not_checked":
            last = unchecked
        elif state in {"ok", "grant_missing"}:
            last = state
        else:
            last = f"{state} ({product.get('rule') or 'no rule'})"
        print(f"  {name}: granted, last check: {last}")


def render_doctor(result: dict[str, Any]) -> None:
    from mb import connect

    print(f"mb connect doctor  {result['repo']}")
    for check in result["checks"]:
        state = "ok" if check["ok"] else "warn"
        print(f"  {state}  {check['name']}: {connect.state_label(check['state'])}")
        if check["repair_command"]:
            print(f"       next: {check['repair_command']}")
    probe_gap = result.get("probe_gap") or {}
    if probe_gap.get("providers"):
        print(f"  note  no provider probe: {', '.join(probe_gap['providers'])}")
        print(f"       {probe_gap['summary']}")


def render_test_result(result: dict[str, Any]) -> None:
    from mb import connect

    if result.get("provider") == "google" and "products" in result:
        from mb import google_probe

        google_probe.render_test_result(result)
        return
    status = result["status"]
    state = "ok" if result["ok"] else "warn"
    validation = result.get("validation") or status.get("validation") or {}
    # An unrecorded check shows its own outcome; status still holds the last one.
    shown = (
        str(validation.get("state") or status["state"])
        if result.get("not_recorded_reason")
        else status["state"]
    )
    print(f"mb connect test {result['provider']}: {state} ({connect.state_label(shown)})")
    summary = validation.get("summary")
    if summary:
        print(f"summary: {summary}")
    upstream = validation.get("upstream") if isinstance(validation, dict) else {}
    if isinstance(upstream, dict) and upstream.get("endpoint_family"):
        details = [f"endpoint: {upstream['endpoint_family']}"]
        if upstream.get("http_status") is not None:
            details.append(f"http: {upstream['http_status']}")
        codes = upstream.get("error_codes")
        if isinstance(codes, list) and codes:
            details.append(f"codes: {', '.join(str(code) for code in codes[:3])}")
        print("provider: " + "  ".join(details))
    scopes = validation.get("scopes") if isinstance(validation, dict) else None
    if isinstance(scopes, dict) and scopes:
        print("reads: " + "  ".join(f"{name}={verdict}" for name, verdict in scopes.items()))
    if result.get("not_recorded_reason") == "connect_yaml_tracked":
        print(
            "recorded: no (.mb/connect.yaml is tracked by git, so checks are not written to "
            f"it; `mb connect status {result['provider']}` shows the last check a person "
            "recorded)"
        )
        next_command = str(validation.get("repair_command") or "")
    else:
        next_command = str(status.get("repair_command") or "")
    if result.get("not_recorded_reason") == "user_scope_read_only":
        connect.render_user_scope_not_recorded()
    elif result.get("not_recorded_reason") == "user_scope_write_failed":
        connect.render_user_scope_write_failed(result)
    if next_command:
        print(f"next: {next_command}")


def not_recorded_line(detail: str) -> str:
    """The ``recorded: no (...)`` line, as ``mb connect test`` shows it."""

    return f"recorded: no ({detail})"


def render_user_scope_write_failed(result: dict[str, Any]) -> None:
    from mb import connect

    detail = result.get("not_recorded_detail") or "the user-scope file was not written"
    print(connect.not_recorded_line(str(detail)))


def render_rotate_result(result: dict[str, Any]) -> None:
    from mb import connect

    stored = "stored" if result["stored"] else "not stored"
    print(f"mb connect rotate {result['provider']}: re-read from 1Password, {stored}")
    connect.render_test_result(result)


def render_hydrate_result(result: dict[str, Any]) -> None:
    print(f"mb connect hydrate  {result['repo']}")
    if result["hydrated"]:
        print(f"hydrated: {', '.join(result['hydrated'])}")
        print(f"metadata: {result['config_path']}")
    else:
        print("no user-scoped provider metadata found for this repo")
    if result["missing"]:
        print(f"missing: {', '.join(result['missing'])}")
    if result.get("repair_command"):
        print(f"next: {result['repair_command']}")


def render_connect_result(result: dict[str, Any]) -> None:
    status = result["status"]
    setup = result.get("setup") if result["provider"] == "meta" else {}
    if isinstance(setup, dict) and setup.get("requirements"):
        print("Meta Ads setup requirements:")
        for item in setup["requirements"]:
            print(f"  - {item}")
    if status["state"] == "ready":
        print(f"connected {result['provider']} and ready")
    elif status["state"] == "unvalidated":
        print(f"stored {result['provider']} credential; validation still needed")
    elif status["state"] == BACKEND_FAILURE_STATE:
        print(f"connected {result['provider']} metadata; credential backend is unhealthy")
        print(f"summary: {status['summary']}")
        print(f"repair: {status['repair']}")
    elif not result["ok"]:
        print(f"connected {result['provider']} metadata; credential still needs repair")
    else:
        print(f"connected {result['provider']} metadata")
    print(f"metadata: {result['config_path']}")
    if result.get("scope") == "user":
        print(f"user scope: {result['user_scope_path']}")
    print(f"secrets: {result['credential_boundary']}")
    rotated = result.get("rotated_sibling_refs") or []
    if rotated:
        print(
            f"rotated {len(rotated)} sibling ref(s) to the new credential (other repos/worktrees)"
        )
    stale = result.get("stale_sibling_refs") or []
    if stale:
        print(
            f"WARNING: {len(stale)} sibling ref(s) could not be updated "
            "and still hold the OLD credential:"
        )
        for ref in stale:
            print(f"  - {ref}")
    source = result.get("credential_source") or {}
    if source.get("type") == "env" and source.get("env_var"):
        print(f"credential source: env {source['env_var']}")
    if status["repair_command"]:
        print(f"next: {status['repair_command']}")


def render_user_scope_not_recorded() -> None:
    from mb import connect

    return connect.render_user_scope_not_recorded()
