"""``mb books check`` — first books safety surface."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import books as books_mod
from mb.cli import app

runner = CliRunner()


def _init_business_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "biz"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    return repo


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git_add_all(repo: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "test"],
        cwd=repo,
        check=True,
    )


def _findings_by_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {finding["id"]: finding for finding in report["findings"]}


def _assert_monthly_report_envelope(payload: dict[str, Any]) -> None:
    assert payload["result_schema"]["name"] == "mainbranch.books.report.v1"
    assert payload["result_envelope_version"] == "1.0"
    assert payload["schema_version"] == "1.0"
    assert "source" in payload
    assert "report" in payload
    assert "totals" in payload
    assert "findings" in payload
    assert "redactions" in payload


def test_books_check_empty_repo_reports_recommendations(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    report = books_mod.run(repo=str(repo))
    findings = _findings_by_id(report)
    assert "books-policy-missing" in findings
    assert findings["books-policy-missing"]["state"] == "info"
    assert findings["books-policy-missing"]["audience"] == "informational"
    assert findings["books-policy-missing"]["operator_summary"]
    assert "chart-of-accounts-missing" in findings
    # No books vault present, but solo-local default applies → warn (not error).
    assert findings["vault-ignore-rule-missing"]["state"] == "warn"
    assert findings["vault-ignore-rule-missing"]["audience"] == "mechanical"
    assert "git ls-files" in findings["unsafe-paths-clean"]["detail"]
    assert report["ok"] is True
    assert report["state"] == "warn"


def test_books_check_passes_with_policy_and_ignore_rule(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
operating_currency: USD
storage_mode: solo-local
vault_location: ".mb/private/books/"
---

# Books
""",
    )
    _write(
        repo / "core/finance/chart-of-accounts.md",
        """---
type: chart-of-accounts
ledger: hledger
---

# Chart
""",
    )
    _write(repo / ".gitignore", ".mb/private/\n")
    _git_add_all(repo)

    report = books_mod.run(repo=str(repo))
    findings = _findings_by_id(report)
    assert findings["books-policy-ok"]["state"] == "ok"
    assert findings["chart-of-accounts-ok"]["state"] == "ok"
    assert findings["vault-ignore-rule-ok"]["state"] == "ok"
    assert findings["unsafe-paths-clean"]["state"] == "ok"
    assert report["state"] == "ok"
    assert report["ok"] is True
    assert report["errors"] == []


def test_books_check_reports_money_path_thresholds(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
operating_currency: USD
storage_mode: solo-local
vault_location: ".mb/private/books/"
money_path:
  scale_basis: rolling_30_day_gross_outflow
  exposure_window_days: 7
  appetite_thresholds:
    small:
      max_amount: 1000
      approval: operator
      ledger_required: true
---

# Books
""",
    )
    _write(repo / ".gitignore", ".mb/private/\n")
    report = books_mod.run(repo=str(repo))

    assert report["money_path_policy"]["thresholds_declared"] is True
    assert report["money_path_policy"]["tiers"]["small"]["max_amount"] == 1000.0
    findings = _findings_by_id(report)
    assert findings["books-money-path-thresholds-ok"]["state"] == "ok"


def test_books_check_flags_committed_ledger_file(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(repo / "core/finance/notes.md", "# notes\n")
    _write(repo / "core/finance/main.journal", "; leaked real journal\n")
    _git_add_all(repo)

    report = books_mod.run(repo=str(repo))
    findings = _findings_by_id(report)
    assert "unsafe-paths-detected" in findings
    leak = findings["unsafe-paths-detected"]
    # Per the foundation decision, unsafe-path detection warns rather
    # than hard-fails so non-finance CSVs and marked fixtures stay
    # usable.
    assert leak["state"] == "warn"
    assert leak["audience"] == "operator_decision"
    assert "git rm --cached <file>" in leak["repair"]
    assert "core/finance/main.journal" in leak["evidence"]
    assert report["ok"] is True
    assert report["state"] == "warn"


def test_books_check_flags_committed_csv_statement(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(repo / "imports/bank-2026-01.csv", "date,amount\n")
    _git_add_all(repo)

    report = books_mod.run(repo=str(repo))
    findings = _findings_by_id(report)
    assert findings["unsafe-paths-detected"]["state"] == "warn"
    assert "imports/bank-2026-01.csv" in findings["unsafe-paths-detected"]["evidence"]


def test_books_check_exempts_marked_fixture(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "docs/examples/sample.journal",
        "; MB-FIXTURE — not a real ledger\n2026-01-01 sample\n",
    )
    _write(
        repo / "research/audience-survey.csv",
        "# MB-FIXTURE — synthetic responses\nq,a\n",
    )
    _git_add_all(repo)

    report = books_mod.run(repo=str(repo))
    findings = _findings_by_id(report)
    assert "unsafe-paths-detected" not in findings
    assert findings["unsafe-paths-fixtures-detected"]["state"] == "info"
    assert "docs/examples/sample.journal" in findings["unsafe-paths-fixtures-detected"]["evidence"]
    assert "research/audience-survey.csv" in findings["unsafe-paths-fixtures-detected"]["evidence"]


def test_books_check_invalid_storage_mode_still_enforces_local_ignore(
    tmp_path: Path,
) -> None:
    """Invalid storage_mode must fail closed: enforce solo-local ignore."""
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: solo-loca
---

# Books
""",
    )
    # Vault directory exists but is not gitignored — must be flagged.
    (repo / ".mb" / "private").mkdir(parents=True)
    (repo / ".mb" / "private" / "main.journal").write_text("; real\n")

    report = books_mod.run(repo=str(repo))
    findings = _findings_by_id(report)
    assert findings["books-policy-storage-mode-invalid"]["state"] == "warn"
    # Critical: invalid mode does NOT route to skip; it routes to
    # enforcement so the leak is caught.
    assert "vault-ignore-rule-skipped" not in findings
    assert findings["vault-ignore-rule-missing"]["state"] == "error"
    assert report["ok"] is False


def test_books_check_team_mode_skips_local_ignore_rule(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: team-private-repo
vault_location: "acme-private-books"
---

# Books
""",
    )
    _git_add_all(repo)

    report = books_mod.run(repo=str(repo))
    findings = _findings_by_id(report)
    assert findings["vault-ignore-rule-skipped"]["state"] == "info"
    # No vault directory exists, so the leftover finding should not appear.
    assert "vault-directory-unexpected" not in findings
    assert report["ok"] is True


def test_books_check_warns_on_unknown_storage_mode(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: not-a-real-mode
---

# Books
""",
    )
    report = books_mod.run(repo=str(repo))
    findings = _findings_by_id(report)
    assert findings["books-policy-storage-mode-invalid"]["state"] == "warn"


def test_books_check_warns_on_broken_frontmatter(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        "---\nstorage_mode: : : not-yaml\n---\n",
    )
    report = books_mod.run(repo=str(repo))
    findings = _findings_by_id(report)
    assert findings["books-policy-frontmatter-error"]["state"] == "error"
    assert report["ok"] is False


def test_books_check_fixture_handles_missing_hledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "")

    report = books_mod.run(repo=str(repo), validate_fixture=True)
    findings = _findings_by_id(report)
    assert findings["hledger-missing"]["state"] == "info"
    assert findings["hledger-missing"]["audience"] == "informational"
    # Missing hledger must not break unrelated repo state.
    assert report["ok"] is True


def _hledger_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
    *,
    returncode: int,
    stdout: str = "",
    stderr: str = "",
) -> list[list[str]]:
    """Fake subprocess.run that only intercepts hledger calls.

    Real git calls (used by ``_run_git`` for ``ls-files``) pass through
    to the real ``subprocess.run`` so a regression that calls the wrong
    binary cannot accidentally satisfy the test.
    """
    real_run = subprocess.run
    seen: list[list[str]] = []

    class _FakeCompleted:
        def __init__(self) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _dispatch(args: Any, *rest: Any, **kwargs: Any) -> Any:
        argv = list(args) if isinstance(args, (list, tuple)) else [args]
        seen.append(argv)
        if argv and Path(str(argv[0])).name == "hledger":
            return _FakeCompleted()
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr("mb.books.subprocess.run", _dispatch)
    return seen


def _hledger_report_dispatcher(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    seen: list[list[str]] = []

    class _FakeCompleted:
        def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _amount(mantissa: int) -> dict[str, Any]:
        return {
            "acommodity": "USD",
            "aquantity": {
                "decimalMantissa": mantissa,
                "decimalPlaces": 2,
                "floatingPoint": mantissa / 100,
            },
        }

    def _periodic(total: int) -> dict[str, Any]:
        return {"prTotals": {"prrTotal": [_amount(total)]}}

    income = {
        "cbrSubreports": [
            ["Revenues", _periodic(25000), True],
            ["Expenses", _periodic(6750), False],
        ],
        "cbrTotals": {"prrTotal": [_amount(18250)]},
    }
    cash = _periodic(125000)
    balance_sheet = {
        "cbrSubreports": [
            ["Assets", _periodic(125000), True],
            ["Liabilities", _periodic(6750), False],
            ["Equity", _periodic(100000), False],
        ]
    }

    def _dispatch(args: Any, *rest: Any, **kwargs: Any) -> Any:
        argv = list(args) if isinstance(args, (list, tuple)) else [args]
        seen.append(argv)
        if not argv or Path(str(argv[0])).name != "hledger":
            raise AssertionError(f"unexpected non-hledger call: {argv}")
        if "check" in argv:
            return _FakeCompleted()
        if "incomestatement" in argv:
            return _FakeCompleted(json.dumps(income))
        if "balance" in argv:
            return _FakeCompleted(json.dumps(cash))
        if "balancesheetequity" in argv:
            return _FakeCompleted(json.dumps(balance_sheet))
        raise AssertionError(f"unexpected hledger report command: {argv}")

    monkeypatch.setattr("mb.books.subprocess.run", _dispatch)
    return seen


def _hledger_exposure_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
    transactions: list[dict[str, Any]],
    *,
    check_returncode: int = 0,
    check_stderr: str = "",
    query_returncode: int = 0,
    query_stderr: str = "",
) -> list[list[str]]:
    real_run = subprocess.run
    seen: list[list[str]] = []

    class _FakeCompleted:
        def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def _dispatch(args: Any, *rest: Any, **kwargs: Any) -> Any:
        argv = list(args) if isinstance(args, (list, tuple)) else [args]
        seen.append(argv)
        if argv and Path(str(argv[0])).name == "hledger":
            if "check" in argv:
                return _FakeCompleted(returncode=check_returncode, stderr=check_stderr)
            if "print" in argv:
                return _FakeCompleted(
                    json.dumps(transactions),
                    returncode=query_returncode,
                    stderr=query_stderr,
                )
            raise AssertionError(f"unexpected hledger command: {argv}")
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr("mb.books.subprocess.run", _dispatch)
    return seen


def _write_books_policy_with_private_journal(repo: Path) -> None:
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: solo-local
vault_location: ".mb/private/books/"
---

# Books
""",
    )
    _write(repo / ".mb/private/books/main.journal", "; PRIVATE_LEDGER_CONTENT\n")


def test_books_check_fixture_runs_when_hledger_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/hledger")
    seen = _hledger_dispatcher(monkeypatch, returncode=0)

    report = books_mod.run(repo=str(repo), validate_fixture=True)
    findings = _findings_by_id(report)
    assert findings["fixture-valid"]["state"] == "ok"
    # The real git ls-files call passed through, so the clean-paths
    # finding came from real evidence, not from the fake.
    assert findings["unsafe-paths-clean"]["state"] == "ok"
    # And at least one of the recorded calls was the hledger invocation.
    assert any(Path(str(call[0])).name == "hledger" for call in seen)


def test_books_check_fixture_reports_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/hledger")
    _hledger_dispatcher(monkeypatch, returncode=1, stderr="balance assertion failed")

    report = books_mod.run(repo=str(repo), validate_fixture=True)
    findings = _findings_by_id(report)
    assert findings["fixture-invalid"]["state"] == "error"
    assert "balance assertion failed" in findings["fixture-invalid"]["detail"]
    assert report["ok"] is False


def test_books_check_cli_emits_json_envelope(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    result = runner.invoke(app, ["books", "check", str(repo), "--json"])
    # warn-state run still exits 0 because no errors.
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mb_command"] == "mb books check"
    assert payload["result_schema"]["name"] == "mainbranch.books.check.result"
    assert payload["result_envelope_version"] == "1.0"
    for finding in payload["findings"]:
        assert "audience" in finding
        assert "operator_summary" in finding


def test_books_check_cli_human_output_mentions_docs(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    result = runner.invoke(app, ["books", "check", str(repo)])
    assert result.exit_code == 0, result.output
    assert "docs/books.md" in result.output


def test_books_check_cli_exits_one_on_error(tmp_path: Path) -> None:
    """A genuine error (broken policy frontmatter) still exits 1."""
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        "---\nstorage_mode: : : not-yaml\n---\n",
    )
    result = runner.invoke(app, ["books", "check", str(repo)])
    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output


def test_books_check_unsafe_paths_warn_does_not_exit_one(tmp_path: Path) -> None:
    """Unsafe-path findings are warn, so the CLI must not exit 1 on them."""
    repo = _init_business_repo(tmp_path)
    _write(repo / "core/finance/main.journal", "; leak\n")
    _git_add_all(repo)
    result = runner.invoke(app, ["books", "check", str(repo)])
    assert result.exit_code == 0, result.output
    assert "WARN" in result.output


def test_books_exposure_json_reports_safe_bet_totals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    _write_books_policy_with_private_journal(repo)
    _write(
        repo / "bets/2026-05-16-offer-test.md",
        """---
status: open
opened: 2026-05-16
deadline: 2026-05-30
appetite: 2 weeks
appetite_tier: small
hypothesis: If we sharpen the offer, calls will increase.
metric: qualified_calls
target: 3 qualified calls
result: ''
money_path:
  required: true
  bet_id: 2026-05-16-offer-test
  exposure_cap:
    amount: 500
    currency: USD
  anchor_required_before: execution
linked_decisions: []
linked_research: []
linked_pushes: []
linked_outcomes: []
public: false
channels: []
tags: []
---
# Offer test
""",
    )
    transactions = [
        {
            "tdescription": "PRIVATE PAYEE",
            "tpostings": [
                {
                    "paccount": "Assets:Bank:PRIVATE_ACCOUNT",
                    "pamount": [
                        {
                            "acommodity": "USD",
                            "aquantity": {"decimalMantissa": -12500, "decimalPlaces": 2},
                        }
                    ],
                },
                {
                    "paccount": "Expenses:Marketing",
                    "pamount": [
                        {
                            "acommodity": "USD",
                            "aquantity": {"decimalMantissa": 12500, "decimalPlaces": 2},
                        }
                    ],
                },
            ],
        }
    ]
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/hledger")
    seen = _hledger_exposure_dispatcher(monkeypatch, transactions)

    result = runner.invoke(
        app,
        [
            "books",
            "exposure",
            "--repo",
            str(repo),
            "--bet",
            "bets/2026-05-16-offer-test.md",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mb_command"] == "mb books exposure"
    assert payload["result_schema"]["name"] == "mainbranch.books.exposure.result"
    exposure = payload["exposures"][0]
    assert exposure["anchor"]["present"] is True
    assert exposure["anchor"]["transaction_count"] == 1
    assert exposure["totals"]["gross_outflow"]["display"] == "$125.00"
    assert exposure["totals"]["remaining_cap"]["display"] == "$375.00"
    assert any("tag:bet=2026-05-16-offer-test" in call for call in seen)
    assert "PRIVATE PAYEE" not in result.output
    assert "PRIVATE_ACCOUNT" not in result.output
    assert "PRIVATE_LEDGER_CONTENT" not in result.output
    assert str(repo) not in result.output
    assert str(repo / ".mb/private/books") not in result.output


def test_books_exposure_flags_over_appetite_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: solo-local
vault_location: ".mb/private/books/"
money_path:
  appetite_thresholds:
    small:
      max_amount: 100
      approval: operator
      ledger_required: true
---

# Books
""",
    )
    _write(repo / ".mb/private/books/main.journal", "; PRIVATE_LEDGER_CONTENT\n")
    _write(
        repo / "bets/2026-05-16-offer-test.md",
        """---
status: open
opened: 2026-05-16
deadline: 2026-05-30
appetite_tier: small
money_path:
  required: true
  bet_id: 2026-05-16-offer-test
linked_decisions: []
linked_research: []
linked_pushes: []
linked_outcomes: []
public: false
channels: []
tags: []
---
# Offer test
""",
    )
    transactions = [
        {
            "tpostings": [
                {
                    "paccount": "Expenses:Marketing",
                    "pamount": [
                        {
                            "acommodity": "USD",
                            "aquantity": {"decimalMantissa": 12500, "decimalPlaces": 2},
                        }
                    ],
                }
            ],
        }
    ]
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/hledger")
    _hledger_exposure_dispatcher(monkeypatch, transactions)

    result = runner.invoke(app, ["books", "exposure", "--repo", str(repo), "--active", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    exposure = payload["exposures"][0]
    assert exposure["scale_gate"]["over_cap"] is True
    assert exposure["scale_gate"]["threshold_amount"]["display"] == "$100.00"
    assert "bet-exposure-over-appetite-threshold" in {
        finding["id"] for finding in payload["findings"]
    }


def test_books_exposure_active_warns_when_required_anchor_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    _write_books_policy_with_private_journal(repo)
    _write(
        repo / "bets/2026-05-16-anchor-missing.md",
        """---
status: open
opened: 2026-05-16
deadline: 2026-05-30
appetite: small
money_path:
  required: true
  bet_id: 2026-05-16-anchor-missing
linked_decisions: []
linked_research: []
linked_pushes: []
linked_outcomes: []
public: false
channels: []
tags: []
---
# Anchor missing
""",
    )
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/hledger")
    _hledger_exposure_dispatcher(monkeypatch, [])

    result = runner.invoke(app, ["books", "exposure", "--repo", str(repo), "--active", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["state"] == "warn"
    assert payload["exposures"][0]["anchor"]["present"] is False
    assert (
        "Add the bet tag to private ledger transactions before execution spend."
        in payload["warnings"]
    )


def test_books_exposure_redacts_private_hledger_check_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    _write_books_policy_with_private_journal(repo)
    _write(
        repo / "bets/2026-05-16-private.md",
        """---
status: open
opened: 2026-05-16
deadline: 2026-05-30
appetite: small
money_path:
  required: true
  bet_id: 2026-05-16-private
linked_decisions: []
linked_research: []
linked_pushes: []
linked_outcomes: []
public: false
channels: []
tags: []
---
# Private
""",
    )
    private_stderr = (
        "PRIVATE PAYEE\nAssets:Bank:PRIVATE_ACCOUNT\nmemo: PRIVATE_MEMO\n2026-05-16 raw ledger row"
    )
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/hledger")
    _hledger_exposure_dispatcher(monkeypatch, [], check_returncode=1, check_stderr=private_stderr)

    result = runner.invoke(
        app,
        [
            "books",
            "exposure",
            "--repo",
            str(repo),
            "--bet",
            "bets/2026-05-16-private.md",
            "--json",
        ],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["findings"][0]["id"] == "hledger-check-failed"
    assert "Private command output is withheld" in payload["findings"][0]["detail"]
    assert "PRIVATE PAYEE" not in result.output
    assert "PRIVATE_ACCOUNT" not in result.output
    assert "PRIVATE_MEMO" not in result.output
    assert "2026-05-16 raw ledger row" not in result.output
    assert str(repo) not in result.output


def test_books_exposure_redacts_private_hledger_query_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    _write_books_policy_with_private_journal(repo)
    _write(
        repo / "bets/2026-05-16-private.md",
        """---
status: open
opened: 2026-05-16
deadline: 2026-05-30
appetite: small
money_path:
  required: true
  bet_id: 2026-05-16-private
linked_decisions: []
linked_research: []
linked_pushes: []
linked_outcomes: []
public: false
channels: []
tags: []
---
# Private
""",
    )
    private_stderr = (
        "PRIVATE PAYEE\n"
        "Expenses:Marketing:PRIVATE_ACCOUNT\n"
        "memo: PRIVATE_MEMO\n"
        "2026-05-16 raw ledger row"
    )
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/hledger")
    _hledger_exposure_dispatcher(monkeypatch, [], query_returncode=1, query_stderr=private_stderr)

    result = runner.invoke(
        app,
        [
            "books",
            "exposure",
            "--repo",
            str(repo),
            "--bet",
            "bets/2026-05-16-private.md",
            "--json",
        ],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["findings"][1]["id"] == "hledger-exposure-query-failed"
    assert "Private command output is withheld" in payload["findings"][1]["detail"]
    assert "PRIVATE PAYEE" not in result.output
    assert "PRIVATE_ACCOUNT" not in result.output
    assert "PRIVATE_MEMO" not in result.output
    assert "2026-05-16 raw ledger row" not in result.output
    assert str(repo) not in result.output


def test_books_status_json_reports_missing_hledger_and_vault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: solo-local
vault_location: ".mb/private/books/"
---

# Books
""",
    )
    _write(repo / ".gitignore", ".mb/private/\n*.journal\n*.hledger\n*.ledger\n*.beancount\n")
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "")

    result = runner.invoke(app, ["books", "status", str(repo), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mb_command"] == "mb books status"
    assert payload["result_schema"]["name"] == "mainbranch.books.status.result"
    assert payload["engine"] == "hledger"
    assert payload["hledger"]["available"] is False
    assert payload["vault"]["location"] == ".mb/private/books"
    assert payload["vault"]["exists"] is False
    assert payload["ignore"]["ok"] is True
    assert "books-vault-missing" in {finding["id"] for finding in payload["findings"]}


def test_books_status_and_doctor_accept_no_slash_private_ignore_entry(
    tmp_path: Path,
) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: solo-local
vault_location: ".mb/private/books/"
---

# Books
""",
    )
    _write(repo / ".gitignore", ".mb/private\n*.journal\n*.hledger\n*.ledger\n*.beancount\n")

    status_result = runner.invoke(app, ["books", "status", str(repo), "--json"])
    assert status_result.exit_code == 0, status_result.output
    status_payload = json.loads(status_result.output)
    assert status_payload["ignore"]["ok"] is True
    assert status_payload["ignore"]["missing"] == []

    doctor_result = runner.invoke(app, ["books", "doctor", str(repo), "--plan", "--json"])
    assert doctor_result.exit_code == 0, doctor_result.output
    doctor_payload = json.loads(doctor_result.output)
    actions = {action["id"] for action in doctor_payload["actions"]}
    assert "add-books-ignore-protections" not in actions


def test_books_status_reports_hledger_and_private_journal_without_reading_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: solo-local
vault_location: ".mb/private/books/"
---

# Books
""",
    )
    _write(repo / ".gitignore", ".mb/private/\n*.journal\n*.hledger\n*.ledger\n*.beancount\n")
    _write(repo / ".mb/private/books/main.journal", "; PRIVATE_ACCOUNT_ID\n")
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/private/bin/hledger")

    result = runner.invoke(app, ["books", "status", str(repo), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["hledger"]["available"] is True
    assert payload["vault"]["exists"] is True
    assert payload["vault"]["journal_placeholder"] == "present"
    assert "/fake/private/bin/hledger" not in result.output
    assert "PRIVATE_ACCOUNT_ID" not in result.output


def test_books_status_sanitizes_external_absolute_vault_path(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    private_path = tmp_path / "private-books" / "main.journal"
    _write(
        repo / "core/finance/books.md",
        f"""---
type: books
ledger: hledger
storage_mode: solo-local
vault_location: "{private_path.parent}"
---

# Books
""",
    )

    result = runner.invoke(app, ["books", "status", str(repo), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["vault"]["location"] == "external private path"
    assert str(private_path.parent) not in result.output


def test_books_readiness_ok_for_configured_fake_books_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: solo-local
vault_location: ".mb/private/books/"
---

# Books
""",
    )
    _write(
        repo / "core/finance/chart-of-accounts.md",
        """---
type: chart-of-accounts
ledger: hledger
---

# Chart
""",
    )
    _write(repo / ".gitignore", ".mb/private/\n*.journal\n*.hledger\n*.ledger\n*.beancount\n")
    _write(repo / ".mb/private/books/main.journal", "; PRIVATE_LEDGER_CONTENT\n")
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/private/bin/hledger")

    readiness = books_mod.readiness(repo=repo)
    payload = json.dumps(readiness)

    assert readiness["state"] == "ok"
    assert readiness["configured"] is True
    assert readiness["mention"] is False
    assert readiness["hledger"]["available"] is True
    assert readiness["ignore"]["ok"] is True
    assert readiness["unsafe_artifacts"]["count"] == 0
    assert readiness["chart_of_accounts"]["present"] is True
    assert readiness["recommended_route"] == {
        "tool": "mb books status",
        "reason": "inspect bookkeeping setup",
    }
    assert "PRIVATE_LEDGER_CONTENT" not in payload
    assert "/fake/private/bin/hledger" not in payload


def test_books_readiness_counts_unsafe_artifacts_without_names(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(repo / "exports/customer-bank-statement.csv", "vendor,amount\nAcme,100\n")
    _git_add_all(repo)

    readiness = books_mod.readiness(repo=repo)
    payload = json.dumps(readiness)

    assert readiness["state"] == "warn"
    assert readiness["mention"] is True
    assert readiness["unsafe_artifacts"]["count"] == 1
    assert readiness["next_command"] == "mb books doctor --plan --json"
    assert readiness["recommended_route"] == {
        "tool": "mb books doctor --plan",
        "reason": "plan bookkeeping setup repairs",
    }
    assert "customer-bank-statement.csv" not in payload
    assert "Acme,100" not in payload


def test_books_readiness_redacts_external_vault_path(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    private_path = tmp_path / "private-books" / "main.journal"
    _write(
        repo / "core/finance/books.md",
        f"""---
type: books
ledger: hledger
storage_mode: solo-local
vault_location: "{private_path.parent}"
---

# Books
""",
    )

    readiness = books_mod.readiness(repo=repo)
    payload = json.dumps(readiness)

    assert readiness["vault"]["location_kind"] == "external"
    assert readiness["vault"]["exists"] is None
    assert str(private_path.parent) not in payload


def test_books_check_status_and_doctor_flag_missing_external_vault_location(
    tmp_path: Path,
) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: team-private-repo
---

# Books
""",
    )
    _write(repo / ".gitignore", ".mb/private/\n*.journal\n*.hledger\n*.ledger\n*.beancount\n")

    check_result = runner.invoke(app, ["books", "check", str(repo), "--json"])
    assert check_result.exit_code == 0, check_result.output
    check_payload = json.loads(check_result.output)
    check_findings = _findings_by_id(check_payload)
    assert check_findings["books-vault-location-missing"]["state"] == "warn"

    status_result = runner.invoke(app, ["books", "status", str(repo), "--json"])
    assert status_result.exit_code == 0, status_result.output
    status_payload = json.loads(status_result.output)
    findings = _findings_by_id(status_payload)
    assert findings["books-vault-location-missing"]["state"] == "warn"
    assert status_payload["vault"]["location"] == "not configured"

    doctor_result = runner.invoke(app, ["books", "doctor", str(repo), "--plan", "--json"])
    assert doctor_result.exit_code == 0, doctor_result.output
    doctor_payload = json.loads(doctor_result.output)
    actions = {action["id"]: action for action in doctor_payload["actions"]}
    assert "configure-private-books-vault-location" in actions
    assert actions["configure-private-books-vault-location"]["writes"] == ["core/finance/books.md"]


def test_books_check_does_not_flag_configured_non_local_vault_location(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: team-private-repo
vault_location: "private-books-repo"
---

# Books
""",
    )

    result = runner.invoke(app, ["books", "check", str(repo), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    findings = _findings_by_id(payload)
    assert "books-vault-location-missing" not in findings


def test_books_doctor_plan_json_lists_safe_repairs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_business_repo(tmp_path)
    _write(repo / "core/finance/main.journal", "; leaked real journal\n")
    _git_add_all(repo)
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "")

    result = runner.invoke(app, ["books", "doctor", str(repo), "--plan", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mb_command"] == "mb books doctor --plan"
    assert payload["result_schema"]["name"] == "mainbranch.books.doctor.plan.result"
    actions = {action["id"]: action for action in payload["actions"]}
    assert "install-hledger" in actions
    assert "create-private-books-vault" in actions
    assert "add-books-ignore-protections" in actions
    assert "move-unsafe-finance-artifacts" in actions
    assert "core/finance/main.journal" in actions["move-unsafe-finance-artifacts"]["evidence"]
    assert payload["safe_to_share"] is True


def test_books_doctor_plan_reports_missing_private_journal_placeholder(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    _write(
        repo / "core/finance/books.md",
        """---
type: books
ledger: hledger
storage_mode: solo-local
vault_location: ".mb/private/books/"
---

# Books
""",
    )
    _write(repo / ".gitignore", ".mb/private/\n*.journal\n*.hledger\n*.ledger\n*.beancount\n")
    (repo / ".mb/private/books").mkdir(parents=True)

    result = runner.invoke(app, ["books", "doctor", str(repo), "--plan", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    actions = {action["id"]: action for action in payload["actions"]}
    assert "create-private-journal-placeholder" in actions
    assert actions["create-private-journal-placeholder"]["writes"] == [
        ".mb/private/books/main.journal"
    ]


def test_books_doctor_requires_plan(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    result = runner.invoke(app, ["books", "doctor", str(repo)])
    assert result.exit_code == 2
    assert "--plan is required" in result.output


def test_books_doctor_requires_plan_json_uses_plan_schema(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    result = runner.invoke(app, ["books", "doctor", str(repo), "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["result_schema"]["name"] == "mainbranch.books.doctor.plan.result"
    assert "--plan is required" in payload["summary"]


def test_books_status_cli_human_output_mentions_plan(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    result = runner.invoke(app, ["books", "status", str(repo)])
    assert result.exit_code == 0, result.output
    assert "mb books status" in result.output
    assert "Ignore rules:      missing" in result.output
    assert f"Run `mb books doctor --plan {shlex.quote(str(repo.resolve()))}`" in result.output


def test_books_doctor_plan_cli_human_output_formats_ignore_entries(tmp_path: Path) -> None:
    repo = _init_business_repo(tmp_path)
    result = runner.invoke(app, ["books", "doctor", str(repo), "--plan"])
    assert result.exit_code == 0, result.output
    assert "mb books doctor --plan" in result.output
    assert "Add books ignore protections" in result.output
    assert "plan: Add these lines to .gitignore: .mb/private/, *.journal" in result.output
    assert "`.mb/private/`" not in result.output


def test_books_check_packaged_fixtures_carry_marker() -> None:
    """The shipped fixtures must continue to carry an explicit marker.

    If a future edit drops the SAMPLE FIXTURE header we want the test
    suite to catch it immediately so the marker contract stays honest.
    """
    repo_root = Path(__file__).resolve().parents[2]
    for rel in (
        "docs/examples/books/acme-fixture.journal",
        "mb/mb/_data/books/acme-fixture.journal",
    ):
        assert books_mod._has_fixture_marker(repo_root / rel), rel


def test_bundled_fixture_matches_docs_fixture() -> None:
    """The packaged journal is a byte-identical mirror of the docs copy."""
    repo_root = Path(__file__).resolve().parents[2]
    docs_bytes = (repo_root / "docs/examples/books/acme-fixture.journal").read_bytes()
    pkg_bytes = (repo_root / "mb/mb/_data/books/acme-fixture.journal").read_bytes()
    assert docs_bytes == pkg_bytes, (
        "mb/mb/_data/books/acme-fixture.journal has drifted from "
        "docs/examples/books/acme-fixture.journal. Re-sync them."
    )


def test_books_report_monthly_json_uses_hledger_envelope_and_sample_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/hledger")
    seen = _hledger_report_dispatcher(monkeypatch)

    result = runner.invoke(
        app,
        ["books", "report", "monthly", "--sample", "--month", "2026-01", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["mb_command"] == "mb books report monthly --sample --month 2026-01"
    _assert_monthly_report_envelope(payload)
    assert payload["safe_to_share"] is True
    assert payload["source"]["kind"] == "packaged_fixture"
    assert payload["source"]["fixture"] is True
    assert payload["source"]["engine"] == "hledger"
    assert payload["source"]["journal"]["path_exposed"] is False
    assert payload["report"]["period"] == {
        "start": "2026-01-01",
        "end": "2026-02-01",
        "label": "January 2026",
    }
    assert payload["totals"]["revenue"]["decimal_mantissa"] == 25000
    assert payload["totals"]["revenue"]["display"] == "$250.00"
    assert payload["totals"]["expenses"]["display"] == "$67.50"
    assert payload["totals"]["net_income"]["display"] == "$182.50"
    assert payload["totals"]["cash"]["display"] == "$1,250.00"
    assert payload["totals"]["credit_card"]["display"] == "$67.50 owed"
    assert payload["redactions"] == {
        "private_paths": True,
        "account_identifiers": True,
        "payees": True,
        "transaction_memos": True,
    }
    assert "not reading your private books" in result.output
    assert "PRIVATE_ACCOUNT_ID" not in result.output
    assert not any("engine_version" in key for key in payload)
    assert any("check" in call for call in seen)
    assert any("incomestatement" in call and "-O" in call and "json" in call for call in seen)
    assert any("balance" in call and "assets:bank" in call and "-H" in call for call in seen)
    assert any("balancesheetequity" in call and "-O" in call and "json" in call for call in seen)
    assert all("-n" in call for call in seen)


def test_books_report_monthly_docs_example_matches_real_hledger_output() -> None:
    if not shutil.which("hledger"):
        pytest.skip("hledger is not installed")
    repo_root = Path(__file__).resolve().parents[2]
    expected = json.loads(
        (repo_root / "docs/examples/books/reports/sample-monthly.json").read_text()
    )

    result = runner.invoke(
        app,
        ["books", "report", "monthly", "--sample", "--month", "2026-01", "--json"],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == expected


def test_books_report_monthly_human_output_is_beginner_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/hledger")
    _hledger_report_dispatcher(monkeypatch)

    result = runner.invoke(
        app,
        ["books", "report", "monthly", "--sample", "--month", "2026-01"],
    )

    assert result.exit_code == 0, result.output
    assert "sample monthly bookkeeping report using fake packaged data" in result.output
    assert "shows the report shape only" in result.output
    assert "does not touch private books" in result.output
    assert "January 2026 sample" in result.output
    assert "Revenue: $250.00" in result.output
    assert "Expenses: $67.50" in result.output
    assert "Net income: $182.50" in result.output
    assert "Checking cash at month end: $1,250.00" in result.output
    assert "Credit card balance: $67.50 owed" in result.output
    assert "This is sample data only. It is not reading your private books." in result.output


def test_books_report_monthly_requires_sample_flag() -> None:
    result = runner.invoke(
        app,
        ["books", "report", "monthly", "--month", "2026-01", "--json"],
    )

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    _assert_monthly_report_envelope(payload)
    assert payload["ok"] is False
    assert payload["mb_command"] == "mb books report monthly --month 2026-01"
    assert "only --sample reports are implemented" in payload["operator_summary"]
    assert "private books reporting is out of scope" in payload["operator_summary"]
    findings = _findings_by_id(payload)
    assert findings["sample-required"]["state"] == "error"


def test_books_report_monthly_requires_month_with_uniform_envelope() -> None:
    result = runner.invoke(
        app,
        ["books", "report", "monthly", "--sample", "--json"],
    )

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    _assert_monthly_report_envelope(payload)
    assert payload["ok"] is False
    assert payload["mb_command"] == "mb books report monthly --sample"
    assert "--month is required" in payload["operator_summary"]
    findings = _findings_by_id(payload)
    assert findings["month-required"]["state"] == "error"


def test_books_report_monthly_rejects_invalid_month() -> None:
    result = runner.invoke(
        app,
        ["books", "report", "monthly", "--sample", "--month", "2026-13", "--json"],
    )

    assert result.exit_code == 2, result.output
    payload = json.loads(result.output)
    _assert_monthly_report_envelope(payload)
    assert payload["ok"] is False
    assert "real calendar month" in payload["operator_summary"]
    findings = _findings_by_id(payload)
    assert findings["month-invalid"]["state"] == "error"


def test_books_report_monthly_missing_hledger_returns_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "")

    result = runner.invoke(
        app,
        ["books", "report", "monthly", "--sample", "--month", "2026-01", "--json"],
    )

    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["safe_to_share"] is True
    findings = _findings_by_id(payload)
    assert findings["hledger-missing"]["state"] == "error"
    assert "Install hledger" in findings["hledger-missing"]["repair"]
    assert "not reading your private books" in result.output


def test_amount_owed_display_keeps_machine_readable_sign() -> None:
    amount = books_mod._amount_from_parts(
        commodity="USD",
        mantissa=-6750,
        places=2,
        owed=True,
    )

    assert amount["decimal_mantissa"] == -6750
    assert amount["display"] == "$67.50 owed"
