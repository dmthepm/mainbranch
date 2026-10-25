"""Synthetic acceptance checks; never inspect this host's mesh or listeners."""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import codex, skill_validate
from mb.cli import app

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / ".claude" / "skills"
AUDIT = SKILLS / "mb-homelab-tailnet-audit"
POLICY = SKILLS / "mb-homelab-tailnet-policy-review"


def load(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def collector(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = load(AUDIT / "scripts" / "collect.py")
    # All collector calls must avoid real procfs too, including on missing PATH.
    monkeypatch.setattr(module, "openssh", lambda: "not checked: synthetic listener fixture")
    return module


def test_a1_fixed_read_only_argv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, collector
) -> None:
    log = tmp_path / "argv.jsonl"
    fake = tmp_path / "tailscale"
    fake.write_text(
        f"#!{sys.executable}\nimport json, sys\n"
        f"with open({str(log)!r}, 'a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "print(json.dumps({'short':'1.2.3','upstream':'1.2.3','Enabled':True,"
        "'RunSSH':False,'AutoUpdate':{'Apply':True}}))\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    result = collector.collect()
    calls = [tuple(["tailscale", *json.loads(line)]) for line in log.read_text().splitlines()]
    assert calls == list(collector.ALLOWLIST)
    assert all("sudo" not in call for call in calls)
    rows = {r["check"]: r["result"] for r in result["rows"]}
    assert rows["Tailscale SSH"] == "off"
    assert rows["Auto-update"] == "on"
    assert rows["Tailnet lock"] == "on"
    assert "current for track" in rows["Version and track"]
    with pytest.raises(ValueError, match="refused"):
        collector.run(("tailscale", "up", "--ssh"))
    assert len(log.read_text().splitlines()) == len(calls)


def test_a1_missing_command(collector, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    report = collector.collect()
    assert all("not checked" in row["result"] for row in report["rows"])
    assert all(collector.run(argv)["status"] == "not checked" for argv in collector.ALLOWLIST)


@pytest.mark.parametrize("failure", ["permission", "timeout", "invalid"])
def test_a1_command_failure(collector, monkeypatch: pytest.MonkeyPatch, failure: str) -> None:
    def fake_run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("tailscale", 20)
        return subprocess.CompletedProcess(
            args, 1 if failure == "permission" else 0, "invalid-json", "private-error"
        )

    monkeypatch.setattr(collector.subprocess, "run", fake_run)
    result = collector.run(collector.ALLOWLIST[0])
    assert result["status"] == "not checked"
    assert "private-error" not in json.dumps(result)


def test_a1_forward_warnings(collector) -> None:
    assert collector.forwards(
        {"TCP": {"443": {"TCPForward": "localhost:22"}}, "Web": {"Proxy": "unix:tailscaled.sock"}}
    ) == ["Review a forward to a local daemon socket", "Review a forward to a possible admin port"]


def test_a1_linux_listener_fixture(tmp_path: Path) -> None:
    module = load(AUDIT / "scripts" / "collect.py")
    process = tmp_path / "123"
    (process / "fd").mkdir(parents=True)
    (process / "comm").write_text("sshd\n")
    (process / "fd" / "3").symlink_to("socket:[789]")
    (tmp_path / "net").mkdir()
    (tmp_path / "net" / "tcp").write_text(
        "header\n0: 0100007F:0016 00000000:0000 0A 0 0 0 0 0 789\n"
    )
    (tmp_path / "net" / "tcp6").write_text("header\n")
    assert module.openssh(tmp_path) == "OpenSSH listening: 127.0.0.1, TCP 22"


def test_a1_platform_unknowns(collector, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(collector, "run", lambda argv: {"status": "checked", "data": {}})
    monkeypatch.setattr(collector.platform, "system", lambda: "Darwin")
    rows = {r["check"]: r["result"] for r in collector.collect()["rows"]}
    assert "not checked" in rows["macOS build"]
    assert "not checked" in rows["OpenSSH listeners"]


def test_a2_redaction_and_stability() -> None:
    module = load(AUDIT / "scripts" / "redact.py")
    secrets = [
        "100.64.0.7",
        "fd7a:115c:a1e0::7",
        "192.0.2.7",
        "2001:db8::7",
        "nodekey:abc123",
        "mkey:abc123",
        "discokey:abc123",
        "nlpub:abc123",
        "tlpub:abc123",
        "tskey-auth-abc123",
        "desk.example-tailnet.ts.net",
        "synthetic-desk",
        "owner@example.invalid",
    ]
    text = " ".join(secrets)
    payload = {
        "identities": {"Self": {"HostName": "synthetic-desk"}},
        "rows": [{"check": "ssh-section", "result": text}, {"check": "wildcard", "result": text}],
        "notes": [text],
    }
    report = module.render(payload)
    for secret in secrets:
        assert secret not in report
    assert not re.search(
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b|fd7a:|2001:db8|\w+\.ts\.net|"
        r"\b(?:nodekey|mkey|discokey|nlpub|tlpub):|tskey-|\S+@\S+",
        report,
    )
    assert "node-1" in report and "user-1" in report
    values = [
        line.split(" | ")[2]
        for line in report.splitlines()
        if line.startswith(("| ssh-section", "| wildcard"))
    ]
    assert values[0] == values[1]
    assert module.render({"rows": [{"result": {"private-name": "private-value"}}]})
    assert "private-name" not in module.render(
        {"rows": [{"result": {"private-name": "private-value"}}]}
    )


def test_a2_copies_identical() -> None:
    for name in ("scripts/redact.py", "references/safety-contract.md"):
        assert (AUDIT / name).read_bytes() == (POLICY / name).read_bytes()


@pytest.mark.parametrize(
    ("policy", "code", "location"),
    [
        ({"ssh": []}, "ssh-section", "ssh"),
        ({"ssh": [{"action": "accept"}]}, "ssh-accept", "ssh[0]"),
        (
            {"grants": [{"src": ["*"], "dst": ["tag:web"]}], "tagOwners": {"tag:web": []}},
            "wildcard",
            "grants[0]",
        ),
        ({"acls": [{"src": ["autogroup:member"], "dst": ["*:443"]}]}, "member-to-all", "acls[0]"),
        (
            {"grants": [{"src": ["tag:unowned"], "dst": []}]},
            "tag-without-owner",
            "grants[0].src[0]",
        ),
        (
            {
                "acls": [{"action": "accept", "src": ["tag:agent"], "dst": ["tag:admin:22"]}],
                "tagOwners": {"tag:agent": [], "tag:admin": []},
            },
            "agent-to-admin",
            "acls[0]",
        ),
    ],
)
def test_a3_each_rule_class(policy: dict[str, Any], code: str, location: str) -> None:
    module = load(POLICY / "scripts" / "review.py")
    rows = module.review(policy, ["tag:agent"], ["tag:admin"])["rows"]
    matching = [r for r in rows if r["check"] == code]
    assert len(matching) == 1
    assert matching[0]["location"] == location
    assert matching[0]["result"] and matching[0]["safer"]
    assert matching[0]["docs"].startswith("https://tailscale.com/")


def test_a3_clean_hujson_and_urls() -> None:
    module = load(POLICY / "scripts" / "review.py")
    policy = module.parse("""{
      // Keep the source URL intact.
      "note": "https://example.invalid/a/*b*/",
      "tagOwners": {"tag:agent": ["autogroup:admin"], "tag:web": ["autogroup:admin"],},
      /* narrow access */ "grants": [
        {"src": ["tag:agent"], "dst": ["tag:web"], "ip": ["tcp:443"],},],
    }""")
    assert policy["note"] == "https://example.invalid/a/*b*/"
    assert module.review(policy, ["tag:agent"], ["tag:admin"])["rows"] == []


@pytest.mark.parametrize("section", ["grants", "acls"])
def test_a3_agent_to_wildcard(section: str) -> None:
    module = load(POLICY / "scripts" / "review.py")
    rows = module.review(
        {
            section: [
                {
                    "action": "accept",
                    "src": ["tag:agent"],
                    "dst": ["*:22" if section == "acls" else "*"],
                }
            ]
        },
        ["tag:agent"],
        ["tag:admin"],
    )["rows"]
    assert len([r for r in rows if r["check"] == "agent-to-admin"]) == 1


def test_a3_cli_exit_and_redacted_pipeline(tmp_path: Path) -> None:
    script = POLICY / "scripts" / "review.py"
    missing = subprocess.run(
        [sys.executable, str(script), str(tmp_path / "absent")], capture_output=True, text=True
    )
    assert missing.returncode != 0 and "Cannot read policy input" in missing.stderr
    assert str(tmp_path) not in missing.stderr
    policy = tmp_path / "policy.hujson"
    policy.write_text('{"ssh": [{"action": "accept", "src": ["*"], "dst": ["*"]}]}')
    result = subprocess.run(
        [sys.executable, str(script), str(policy)], capture_output=True, text=True
    )
    assert result.returncode == 0
    rendered = subprocess.run(
        [sys.executable, str(POLICY / "scripts" / "redact.py")],
        input=result.stdout,
        capture_output=True,
        text=True,
    )
    assert rendered.returncode == 0 and "ssh-accept" in rendered.stdout
    policy.write_text("invalid policy")
    invalid = subprocess.run(
        [sys.executable, str(script), str(policy)], capture_output=True, text=True
    )
    assert invalid.returncode == 0 and "incomplete" in invalid.stdout


def test_a4_commands_documented() -> None:
    module = load(AUDIT / "scripts" / "collect.py")
    evidence = (AUDIT / "references" / "commands.md").read_text()
    for argv in module.ALLOWLIST:
        line = next(line for line in evidence.splitlines() if f"`{' '.join(argv)}`" in line)
        assert "https://tailscale.com/docs/" in line and "2026-10-25" in line
    for skill in (AUDIT, POLICY):
        docs = (skill / "references" / "commands.md").read_text()
        entrypoints = re.findall(r"python3 scripts/\w+\.py", (skill / "SKILL.md").read_text())
        assert all(entry in docs for entry in entrypoints)
        for script in (skill / "scripts").glob("*.py"):
            source = script.read_text()
            if script.name != "collect.py":
                assert "subprocess" not in source


def test_a5_skill_validation_and_boundaries() -> None:
    for skill in (AUDIT, POLICY):
        report = skill_validate.run(skill.name)
        assert report is not None and report["ok"], report
        assert len((skill / "SKILL.md").read_text().splitlines()) < skill_validate.MAX_SKILL_LINES
        for path in skill.rglob("*"):
            if path.is_file() and path.suffix in {".md", ".py"}:
                text = path.read_text()
                assert "../" not in text
                assert not re.search(r"/(?:home|Users)/", text)
    result = CliRunner().invoke(app, ["skill", "validate", "--all", "--json"])
    assert result.exit_code == 0, result.stdout


def test_a6_claude_only() -> None:
    for name in (AUDIT.name, POLICY.name):
        assert name not in codex.CLAUDE_SKILL_SOURCE_NAMES
        assert name not in codex.CODEX_GLOBAL_SKILL_NAMES
        paths = [
            ROOT / "mb/mb/start.py",
            SKILLS / "mb-start/SKILL.md",
            ROOT / "mb/mb/_data/release_simulations/manifest.json",
        ]
        paths.extend((ROOT / "workflows").rglob("*.md"))
        paths.extend((SKILLS / "mb-start/references").glob("*.md"))
        assert all(name not in path.read_text() for path in paths)


def test_a1_missing_cli_exits_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            'import platform, runpy, sys; platform.system=lambda: "Darwin"; '
            'runpy.run_path(sys.argv[1], run_name="__main__")',
            str(AUDIT / "scripts" / "collect.py"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert all("not checked" in row["result"] for row in json.loads(result.stdout)["rows"])


IDENTITY_CASES = [
    ({"DisplayName": "Synthetic Person"}, "Synthetic Person", "user"),
    ({"LoginName": "owner@example.invalid"}, "owner@example.invalid", "user"),
    (
        {"ProfilePicURL": "https://photos.example.invalid/person.jpg"},
        "https://photos.example.invalid/person.jpg",
        "url",
    ),
    ({"User": "example-user"}, "example-user", "user"),
    ({"User": {"Name": "example-person"}}, "example-person", "user"),
    ({"UserProfiles": {"1234567": {"DisplayName": "example-profile"}}}, "example-profile", "user"),
    ({"UserProfiles": {"1234567": {}}}, "1234567", "id"),
    ({"ID": "opaque-id-abc"}, "opaque-id-abc", "id"),
    ({"StableID": "stable-node-abc"}, "stable-node-abc", "id"),
    ({"NodeID": 9876543}, "9876543", "id"),
    ({"PublicKey": "opaque-public-key"}, "opaque-public-key", "id"),
    ({"HostName": "synthetic-desk"}, "synthetic-desk", "node"),
    ({"DNSName": "desk.example-tailnet.ts.net"}, "desk.example-tailnet.ts.net", "node"),
    ({"CertDomains": ["desk.example.invalid"]}, "desk.example.invalid", "node"),
    ({"MagicDNSSuffix": "example-tailnet.ts.net"}, "example-tailnet.ts.net", "tailnet"),
    ({"CurrentTailnet": {"Name": "example-mesh.invalid"}}, "example-mesh.invalid", "tailnet"),
    ({"TailnetName": "example-mesh"}, "example-mesh", "tailnet"),
    ({"Tailnet": {"Name": "example-network"}}, "example-network", "tailnet"),
]


@pytest.mark.parametrize(("identities", "secret", "kind"), IDENTITY_CASES)
def test_f1_identity_values_everywhere(identities, secret, kind) -> None:
    module = load(AUDIT / "scripts/redact.py")
    # Repeat under a second key and embed without word boundaries in surviving fields.
    payload = {
        "identities": identities,
        "rows": [
            {
                "check": "ssh-section",
                "result": f"prefix{secret}suffix",
                "safer": secret,
                "unknown": secret,
            }
        ],
        "notes": [secret, f"prefix{secret}suffix"],
        "second_key": secret,
    }
    output = module.render(payload)
    assert secret not in output
    assert f"prefix{kind}-1suffix" in output
    assert output.count(f"{kind}-1") == 4


@pytest.mark.parametrize(
    "secret",
    [
        "192.0.2.7",
        "100.64.0.7",
        "fd7a:115c:a1e0::7",
        "2001:db8::7",
        "2001:0db8:0000:0000:0000:0000:0000:0007",
        "fe80::7%eth0",
        "::1",
        "::ffff:192.0.2.7",
        "nodekey:abc123",
        "mkey:abc123",
        "discokey:abc123",
        "nlpub:abc123",
        "tlpub:abc123",
        "tskey-auth-abc123",
        "desk.example-tailnet.ts.net",
        "owner@example.invalid",
        "https://photos.example.invalid/unlabelled.jpg",
        "http://example.invalid/page",
    ],
)
def test_f1_patterns_in_free_text(secret: str) -> None:
    module = load(AUDIT / "scripts/redact.py")
    output = module.render({"rows": [{"check": "wildcard", "result": secret}], "notes": [secret]})
    assert secret not in output
    assert re.search(r"(?:node|user|id|url)-\d+", output)


@pytest.mark.parametrize(
    "text",
    ["prefix192.0.2.7suffix", "addr=192.0.2.7:41641", "[2001:db8::7]:443", "[fe80::7%eth0]:443"],
)
def test_f1_address_boundaries(text: str) -> None:
    module = load(AUDIT / "scripts/redact.py")
    output = module.render({"notes": [text]})
    assert "192.0.2.7" not in output
    assert "2001:db8::7" not in output
    assert "fe80::7" not in output
    assert "node-1" in output


def test_f1_longest_identity_first_and_repeat() -> None:
    module = load(AUDIT / "scripts/redact.py")
    payload = {
        "identities": {
            "HostName": "example-host",
            "DNSName": "example-host.mesh.invalid",
            "DisplayName": "example-host",
        },
        "notes": ["prefixexample-host.mesh.invalidsuffix", "example-host"],
    }
    output = module.render(payload)
    assert "prefixnode-2suffix" in output
    assert "- node-1" in output
    assert "example-host" not in output


def test_f2_allowlisted_table_schema() -> None:
    module = load(AUDIT / "scripts/redact.py")
    output = module.render(
        {
            "unknown": "unknown-top-level",
            "rows": [
                {"check": "unknown-check", "result": "unknown-result"},
                {
                    "check": "Tailscale SSH",
                    "result": "on",
                    "extra": "unknown-extra",
                    "location": "unknown-location",
                    "safer": "unknown-safer",
                    "docs": "https://example.invalid/private",
                },
                {"check": "Auto-update", "result": "unexpected-value"},
            ],
            "notes": [{"extra": "unknown-note"}],
        }
    )
    assert "| Tailscale SSH |  | on |  |  |" in output
    assert "not checked: unexpected field value" in output
    for value in (
        "unknown-top-level",
        "unknown-check",
        "unknown-result",
        "unknown-extra",
        "unknown-location",
        "unknown-safer",
        "example.invalid",
        "unexpected-value",
        "unknown-note",
    ):
        assert value not in output


def test_f1_final_identifying_values_sweep() -> None:
    module = load(AUDIT / "scripts/redact.py")
    identities = [case[0] for case in IDENTITY_CASES]
    secrets = [case[1] for case in IDENTITY_CASES]
    secrets += [
        "192.0.2.7",
        "fd7a:115c:a1e0::7",
        "nodekey:synthetic-secret",
        "https://example.invalid/leftover",
        "other.example.ts.net",
    ]
    text = " ".join(f"prefix{secret}suffix" for secret in secrets)
    payload = {
        "identities": identities,
        "rows": [{"check": "wildcard", "result": text, "safer": text}],
        "notes": [text],
    }
    output = module.render(payload)
    assert "| wildcard" in output
    for secret in secrets:
        assert secret.lower() not in output.lower()


@pytest.mark.parametrize(
    ("check", "result", "expected"),
    [
        ("Serve", {"Web": {"private": "value"}}, "Configuration present"),
        ("Funnel", {}, "No configuration returned"),
        (
            "OpenSSH listeners",
            "OpenSSH listening: 127.0.0.1, TCP 22; 0.0.0.0, TCP 22",
            "all interfaces; loopback",
        ),
        ("macOS build", "App Store", "App Store"),
        ("Version and track", "1.2.3; current for track", "1.2.3; current for track"),
    ],
)
def test_f2_machine_schema_preserves_facts(check, result, expected) -> None:
    module = load(AUDIT / "scripts/redact.py")
    output = module.render({"rows": [{"check": check, "result": result}]})
    assert expected in output


def test_f2_policy_location_and_public_docs() -> None:
    reviewer = load(POLICY / "scripts/review.py")
    redactor = load(POLICY / "scripts/redact.py")
    report = redactor.render(reviewer.review({"ssh": [{"action": "accept"}]}, [], []))
    assert "| ssh-accept | ssh[0] |" in report
    assert "https://tailscale.com/docs/features/tailscale-ssh" in report


def test_f1_ipv4_octet_validation() -> None:
    module = load(AUDIT / "scripts/redact.py")
    assert module.Redactor({}).scrub("prefix999.0.2.7suffix") == "prefix999.0.2.7suffix"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("pre2001:db8::7post", "prenode-1post"),
        # The first valid start is 2001; the longest final hextet is 7bee.
        ("cafe2001:db8::7beef", "cafenode-1f"),
        ("pre2001:0db8:0000:0000:0000:0000:0000:0007post", "prenode-1post"),
        ("pre::ffff:192.0.2.7post", "prnode-1post"),
        # A glued hex e is itself a valid first hextet in these compressed forms.
        ("pre::1post", "prnode-1post"),
        ("prefe80::7%eth0post", "prenode-1"),
        # Zone identifiers permit letters, so the suffix is part of the zone.
        ("pre2001:db8::7%eth0post", "prenode-1"),
        ("[fe80::7%eth0]:443", "[node-1]:443"),
        ("2001:db8::7 and 2001:db8::8", "node-1 and node-2"),
        ("12:30", "12:30"),
        ("::", "::"),
        # A six-group MAC has no valid IPv6 substring and stays unchanged.
        ("aa:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff"),
    ],
)
def test_g1_ipv6_at_every_offset(text: str, expected: str) -> None:
    module = load(AUDIT / "scripts/redact.py")
    payload = {
        "rows": [{"check": "wildcard", "result": text, "safer": text}],
        "notes": [text],
    }
    output = module.render(payload)
    assert f"| wildcard |  | {expected} | {expected} |  |" in output
    assert f"- {expected}\n" in output
    assert module.Redactor({}).scrub(text) == expected
