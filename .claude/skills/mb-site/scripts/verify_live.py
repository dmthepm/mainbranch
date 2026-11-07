#!/usr/bin/env python3
"""verify_live.py — read-only live smoke test for /mb-site atoms.

Exercises every external dependency the atoms touch, without spending money
or making state changes. Run this after credentials are provisioned in
`mb connect` to confirm all upstreams reach success before merging.

Checks:
  1. domain-check brew CLI: live RDAP query (free).
  2. Cloudflare API auth: lists zones in the account (read-only).
  3. Cloudflare zone lookup: GET /zones?name=<test domain> (read-only).
  4. Porkbun API auth: POST /ping with the keys (read-only; returns yourIp).

Required env (run this script through `mb connect exec cloudflare -- python3 ...`):
  CLOUDFLARE_API_TOKEN  — Zone:Read + DNS:Read minimum (Edit preferred)
  CF_ACCOUNT_ID         — find in dash.cloudflare.com → right sidebar
  PORKBUN_API_KEY
  PORKBUN_SECRET_KEY

Optional env:
  VERIFY_LIVE_CF_ZONE   — domain to lookup at Cloudflare (default: thelastbill.com)

Exit code: 0 if all checks pass, 1 if any fail.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _envelope import log  # noqa: E402

# ---------------------------------------------------------------------------

CF_API_BASE = "https://api.cloudflare.com/client/v4"
PORKBUN_API_BASE = "https://api.porkbun.com/api/json/v3"
DEFAULT_CF_ZONE = os.environ.get("VERIFY_LIVE_CF_ZONE", "thelastbill.com")

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{GREEN}✓{RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{RED}✗{RESET} {msg}")


def _info(msg: str) -> None:
    print(f"{DIM}  {msg}{RESET}")


def check_domain_check_cli() -> bool:
    print(f"\n{YELLOW}[1/4] domain-check brew CLI{RESET}")
    try:
        proc = subprocess.run(
            ["domain-check", "google.com", "--json", "--yes"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError:
        _fail("domain-check not on PATH")
        _info("Fix: brew install domain-check")
        return False
    except subprocess.TimeoutExpired:
        _fail("domain-check timed out (30s)")
        return False

    if proc.returncode != 0:
        _fail(f"domain-check exit {proc.returncode}: {proc.stderr.strip()[:200]}")
        return False

    try:
        rows = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _fail("domain-check returned non-JSON")
        return False

    if not rows or not isinstance(rows, list):
        _fail(f"domain-check unexpected shape: {type(rows).__name__}")
        return False

    google = rows[0]
    if google.get("available") is True:
        _fail("google.com reported as AVAILABLE — RDAP lookup is broken")
        return False

    _ok(f"domain-check works: google.com → TAKEN (method={google.get('method_used')})")
    return True


def _cf_get(path: str) -> tuple[int, dict | None, int]:
    """GET against Cloudflare's API. Returns (status_code, body, latency_ms)."""
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    start = time.monotonic()
    try:
        resp = requests.get(f"{CF_API_BASE}{path}", headers=headers, timeout=15)
    except requests.RequestException as exc:
        return 0, {"_network_error": str(exc)}, int((time.monotonic() - start) * 1000)
    latency_ms = int((time.monotonic() - start) * 1000)
    try:
        return resp.status_code, resp.json(), latency_ms
    except ValueError:
        return resp.status_code, None, latency_ms


def _surface_cf_errors(body: dict | None) -> None:
    if not body:
        return
    for err in (body.get("errors") or []):
        _info(f"  cf code {err.get('code')}: {err.get('message')}")


def check_cf_auth() -> bool:
    """Verify the token has the three scopes the CF-registered path needs.

    Note: we don't use /user/tokens/verify — that endpoint is for User-scoped
    tokens only and returns code 1000 ('Invalid API Token') for Account-scoped
    tokens. Instead, we hit the actual scope endpoints and check the responses.
    """
    print(f"\n{YELLOW}[2/4] Cloudflare API scopes (Registrar + Pages + Zone){RESET}")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account_id = os.environ.get("CF_ACCOUNT_ID")

    if not token:
        _fail("CLOUDFLARE_API_TOKEN not set")
        _info("Fix: create token at https://dash.cloudflare.com/profile/api-tokens")
        _info("     Store it with `mb connect cloudflare --token-stdin`, then use `mb connect exec`")
        return False

    if not account_id:
        _fail("CF_ACCOUNT_ID not set")
        _info("Fix: find it in dash.cloudflare.com → right sidebar of any zone")
        _info("     Set CF_ACCOUNT_ID for this command; it is not a secret")
        return False

    all_pass = True

    # --- Registrar Domains (Admin) ---
    status, body, lat = _cf_get(f"/accounts/{account_id}/registrar/domains")
    if status == 200 and body and body.get("success"):
        count = len(body.get("result") or [])
        _ok(f"Registrar Domains:Admin works ({lat}ms, {count} domains in account)")
    else:
        _fail(f"Registrar Domains:Admin probe returned HTTP {status}")
        _surface_cf_errors(body)
        _info("Fix: token policy 1 must include Cloudflare Registrar:Admin (Entire Account scope)")
        all_pass = False

    # --- Pages Projects (Edit) ---
    status, body, lat = _cf_get(f"/accounts/{account_id}/pages/projects")
    if status == 200 and body and body.get("success"):
        count = len(body.get("result") or [])
        _ok(f"Cloudflare Pages:Edit works ({lat}ms, {count} projects in account)")
    else:
        _fail(f"Cloudflare Pages:Edit probe returned HTTP {status}")
        _surface_cf_errors(body)
        _info("Fix: token policy 1 must include Cloudflare Pages:Edit (Entire Account scope)")
        all_pass = False

    # --- Zone:Read (verifies the second policy is wired) ---
    status, body, lat = _cf_get(f"/zones?account.id={account_id}&per_page=1")
    if status == 200 and body and body.get("success"):
        count = body.get("result_info", {}).get("total_count", 0)
        _ok(f"Zone:Read works ({lat}ms, {count} zones in account)")
    else:
        _fail(f"Zone:Read probe returned HTTP {status}")
        _surface_cf_errors(body)
        _info("Fix: token policy 2 must include Zone:Read+Edit (All Domains scope)")
        all_pass = False

    if all_pass:
        _ok(f"CF_ACCOUNT_ID confirmed: {account_id[:8]}…")
    return all_pass


def check_cf_zone_lookup() -> bool:
    print(f"\n{YELLOW}[3/4] Cloudflare zone lookup ({DEFAULT_CF_ZONE}){RESET}")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account_id = os.environ.get("CF_ACCOUNT_ID")

    if not token or not account_id:
        _fail("Skipped — CF auth check failed")
        return False

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    start = time.monotonic()
    try:
        resp = requests.get(
            f"{CF_API_BASE}/zones",
            headers=headers,
            params={"name": DEFAULT_CF_ZONE, "account.id": account_id},
            timeout=15,
        )
    except requests.RequestException as exc:
        _fail(f"network error: {exc}")
        return False

    latency_ms = int((time.monotonic() - start) * 1000)

    if resp.status_code != 200:
        _fail(f"zone lookup returned HTTP {resp.status_code}")
        try:
            for err in resp.json().get("errors", []):
                _info(f"  cf code {err.get('code')}: {err.get('message')}")
        except ValueError:
            pass
        return False

    try:
        body = resp.json()
    except ValueError:
        _fail("non-JSON response")
        return False

    if not body.get("success"):
        _fail("zone lookup unsuccessful")
        return False

    zones = body.get("result") or []
    if not zones:
        _info(f"No zone found for {DEFAULT_CF_ZONE} in account {account_id[:8]}…")
        _info(f"Override with: VERIFY_LIVE_CF_ZONE=<some-domain-you-own> python3 verify_live.py")
        _info("(This is informational, not a failure — the API call succeeded.)")
        _ok(f"CF zone lookup endpoint works ({latency_ms}ms, 0 results)")
        return True

    zone = zones[0]
    ns_pair = zone.get("name_servers") or []
    _ok(f"CF zone lookup works ({latency_ms}ms): id={zone.get('id', '')[:12]}…")
    _ok(f"  zone status: {zone.get('status')}, ns: {ns_pair}")
    return True


def check_porkbun_ping() -> bool | None:
    """Returns None when Porkbun keys absent (skip, not fail) — CF-registered path doesn't touch Porkbun."""
    print(f"\n{YELLOW}[4/4] Porkbun API auth (POST /ping){RESET}")
    api_key = os.environ.get("PORKBUN_API_KEY")
    secret_key = os.environ.get("PORKBUN_SECRET_KEY")

    if not api_key or not secret_key:
        print(f"{DIM}  Skipped — PORKBUN_API_KEY / PORKBUN_SECRET_KEY not set.{RESET}")
        print(f"{DIM}  Not needed for the CF-registered path. Add only if you want to{RESET}")
        print(f"{DIM}  exercise dns.py's Porkbun NS-swap branch.{RESET}")
        return None

    start = time.monotonic()
    try:
        resp = requests.post(
            f"{PORKBUN_API_BASE}/ping",
            json={"apikey": api_key, "secretapikey": secret_key},
            timeout=15,
        )
    except requests.RequestException as exc:
        _fail(f"network error: {exc}")
        _info("If the URL in the error references porkbun.com (not api.porkbun.com), the host fix didn't apply.")
        return False

    latency_ms = int((time.monotonic() - start) * 1000)

    try:
        body = resp.json()
    except ValueError:
        _fail(f"non-JSON response (HTTP {resp.status_code})")
        return False

    if body.get("status") != "SUCCESS":
        _fail(f"Porkbun rejected ping: {body.get('message', 'unknown')}")
        return False

    _ok(f"Porkbun /ping works ({latency_ms}ms): yourIp={body.get('yourIp')}")
    _ok(f"  host pinned correctly to api.porkbun.com")
    return True


def main() -> int:
    print(f"{YELLOW}=== /mb-site atoms — live verification ==={RESET}")
    print(f"{DIM}Read-only smoke test. No state changes, no spending.{RESET}")
    print(f"{DIM}Run through `mb connect exec cloudflare -- python3 ...`.{RESET}")

    results = [
        ("domain-check CLI", check_domain_check_cli()),
        ("Cloudflare scopes", check_cf_auth()),
        ("Cloudflare zone lookup", check_cf_zone_lookup()),
        ("Porkbun ping", check_porkbun_ping()),
    ]

    print(f"\n{YELLOW}=== Summary ==={RESET}")
    failed = 0
    skipped = 0
    for name, ok in results:
        if ok is None:
            print(f"  {DIM}—{RESET} {name} {DIM}(skipped — not needed for CF-registered path){RESET}")
            skipped += 1
        elif ok:
            print(f"  {GREEN}✓{RESET} {name}")
        else:
            print(f"  {RED}✗{RESET} {name}")
            failed += 1

    total = len(results)
    passed = total - failed - skipped
    print()
    if failed == 0:
        msg = f"{passed}/{total} passed"
        if skipped:
            msg += f" ({skipped} skipped)"
        print(f"{GREEN}{msg} — atoms are live-ready for the CF-registered flow.{RESET}")
        return 0
    print(f"{RED}{failed}/{total} checks failed.{RESET} See messages above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
