---
title: mb books check hledger cleanup dogfood
date: 2026-05-12
linked_issue: https://github.com/dmthepm/mainbranch/issues/501
release: next patch candidate after v0.3.16
status: complete
tags: [bookkeeping, dogfood, hledger, package-smoke]
---

# `mb books check` Hledger Cleanup Dogfood

## Summary

The post-v0.3.16 hledger cleanup passes the installed-package and fresh business
repo smoke. The dogfood also found one stale active skill-reference family that
still used Beancount as the bookkeeping example; this branch updates those
examples to hledger.

## Environment

- Branch: `dmthepm/books-dogfood`
- Package built from the branch with `python3 -m build`
- Wheel installed into `/tmp/mainbranch-books-dogfood-venv`
- Fresh business repo created at `/tmp/mainbranch-books-dogfood-business`
- Installed CLI reported `mb 0.3.16`

## Commands Run

- `mb --version`
- `mb skill list`
- `mb educational hledger`
- `mb educational beancount`
- `mb onboard --yes --name "Books Dogfood" --path /tmp/mainbranch-books-dogfood-business --json`
- `mb books check /tmp/mainbranch-books-dogfood-business --json`
- `mb books check /tmp/mainbranch-books-dogfood-business`
- `mb books check /tmp/mainbranch-books-dogfood-business --fixture --json`
- `mb connect status --repo /tmp/mainbranch-books-dogfood-business --all --json`
- `mb connect list --repo /tmp/mainbranch-books-dogfood-business --json`
- `rg -n -i 'beancount' ...`

## Results

- Package/install smoke passed: the installed CLI ran and listed bundled skills.
- `mb educational hledger` is present and has no Beancount references.
- `mb educational beancount` exits with topic-not-found and suggests the current
  topic list, including `hledger`.
- Fresh `mb onboard --yes` created the business repo and linked packaged skills.
- Generated `.gitignore` contains `.mb/private/`, `*.journal`, `*.hledger`,
  `*.ledger`, and defensive `*.beancount`.
- `mb books check` on the fresh repo exits 0 with expected info findings for
  optional `core/finance/books.md` and `core/finance/chart-of-accounts.md`.
- `mb books check --fixture` exits 0 and validates the bundled hledger fixture on
  this machine.
- `mb connect status --all --json` exposes `hledger`, not Beancount.
- `mb connect list --json` exposes `hledger`, not Beancount.

## Beancount Search Classification

Remaining Beancount mentions after this branch are intentional:

- release history and changelog entries;
- the hledger-vs-Beancount research report and books foundation decision;
- superseded dependency-choice rows;
- defensive ignore and ledger-extension coverage for `.beancount` files;
- tests that assert Beancount is no longer an active provider or educational
  topic.

The active bundled skill archetype examples were not in that category. They now
use hledger for the bookkeeping example and describe the safe current product
shape as plain-text books plus repo-backed summaries.
