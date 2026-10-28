# Codex Stage 1 Dogfood Report

This is a public-safe dogfood note for
[MAIN-304 / #453](https://github.com/dmthepm/mainbranch/issues/453) after
the `mainbranch 0.3.19` package publish. It is not a raw Codex transcript. It
avoids local paths, account data, private business context, and long excerpts.

## Evidence Set

- Date: 2026-05-12
- Published package: `mainbranch 0.3.19` from PyPI
- Codex CLI version observed in interactive smoke: `0.129.0`
- Evidence level: fresh PyPI install fixture, `codex exec` smoke, interactive
  Codex CLI smoke in an existing business repo, and Codex prompt-input
  inspection
- Codex Mac app and Codex cloud: not exercised in this round
- Related implementation: [#405](https://github.com/dmthepm/mainbranch/issues/405)
  and [PR #456](https://github.com/dmthepm/mainbranch/pull/456)
- Public/private boundary: sanitized summary only

## Deterministic Package Fixture

- `pip install mainbranch==0.3.19`: ok
- `mb --version`: `mb 0.3.19`
- `mb onboard --yes --json`: ok
- `mb status --json --peek`: ok
- `mb start --json`: ok
- `mb doctor repair --plan --json`: ok
- Target fact check passed for:
  - `money_path`
  - `money_path.objects.proof.quality`
  - top-level `content_strategy`
  - Codex readiness in status facts
  - Codex readiness in start facts
  - Codex coverage in the repair plan

The fixture proves that the shipped package exposes the deterministic facts the
Codex adapter needs before a runtime tries to advise the operator.

## Codex Exec Smoke

The first `codex exec` smoke completed with exit code `0`. Codex ran the
shipped `mb` commands, grounded its answer in deterministic facts, and routed
the operator toward finishing onboarding work in business language.

A clean-baseline rerun executed the expected read-only commands and left the
fixture repo clean, but the wrapper did not return a useful final assistant
message within the smoke window and was stopped. Treat this as a quality
concern for the harness, not as proof of a product failure.

## Interactive Codex CLI Smoke

Interactive Codex CLI was then run in an existing mature business repo with the
published `0.3.19` package available. The session showed the expected Stage 1
behavior:

- Codex ran `mb --version` and saw `mb 0.3.19`.
- Codex ran `mb status --json --peek`.
- Codex ran `mb doctor repair --plan`.
- Codex identified setup/readiness work before recommending business-output
  work.
- When asked to run `/mb-start`, Codex correctly treated `/mb-start` as a
  Claude Code slash command and used the Codex-native `mb start --json` plus
  `mb status --json --peek` workflow instead.
- Codex asked before repair/write commands instead of mutating the repo
  silently.

Prompt-family coverage was partial and should not be overstated:

- Path-to-money and update-first posture: the interactive "what next" prompt
  used status and repair-plan facts to prioritize setup/readiness before
  business-output work.
- Proof distinctions: `money_path.objects.proof.quality` was verified in the
  package fixture, but no separate interactive prompt proved Codex used that
  nested proof-quality distinction in natural language.
- Content strategy: top-level `content_strategy` was verified in the package
  fixture, but no separate interactive prompt proved Codex preferred the JSON
  content-strategy facts over raw file inspection.
- Bounded writes: the interactive repair/setup path showed Codex asking before
  write or repair commands.

This is the right outcome for the current public claim: Codex has an
experimental CLI-first adapter, not slash-command parity.

## Prompt Input And Skill Discovery

Codex prompt-input inspection showed that the generated repo `AGENTS.md` is in
the Codex context. It did not show Main Branch's Claude Code skills as native
Codex skills, and no `.agents/skills` workflow corpus was present in the tested
business repo.

That matches the current architecture. PR #456 shipped Stage 1:

- generated and repaired Codex `AGENTS.md` guidance;
- Codex readiness facts in `mb status`, `mb start`, and `mb doctor repair`;
- docs and tests for the experimental CLI-first adapter.

It intentionally did not ship:

- Codex slash-command parity;
- copying `.claude/skills` into `.agents/skills`;
- a shared workflow corpus;
- selected native Codex workflow ports.

## Product Call

`mainbranch 0.3.19` is fit for the Stage 1 support claim: Codex can be grounded
through generated repo instructions and deterministic `mb` facts. It should not
be described as full Codex workflow support.

The public product language should remain close to:

> Claude Code is first-class today. Codex has an experimental CLI-first adapter
> for power users.

Do not ask users to expect `/mb-start` to work inside Codex until a native
Codex workflow surface exists and has runtime smoke evidence.

## Follow-Up Route

The right next decision/design issue for moving Codex support forward is
[MAIN-302 / #451](https://github.com/dmthepm/mainbranch/issues/451):
decide the native workflow architecture before selected workflow ports move
into implementation. It should use this dogfood evidence to decide:

- whether `.claude/skills` remains canonical or a runtime-neutral workflow
  source is introduced;
- what gets rendered for Claude Code versus Codex;
- whether Codex `AGENTS.md` is only bootstrap guidance or also indexes native
  workflow entrypoints;
- how tests detect drift between runtime surfaces;
- whether the next durable path is a shared workflow corpus plus native
  renderers, a smaller Codex workflow shell, or another staged approach;
- which first workflow family should be rendered after that decision, likely
  lifecycle start/end before broader skill parity.

After MAIN-302 decides that architecture,
[#125](https://github.com/dmthepm/mainbranch/issues/125) can become an
implementation slice for selected Codex workflow ports instead of a broad
compatibility bucket.

## Remaining MAIN-304 Work

MAIN-304 does not need a new issue. Before closing it, keep the evidence narrow:

- attach this report to #453;
- avoid expanding the branch into shared workflow implementation;
- optionally run one more interactive Codex prompt set if the support decision
  needs more qualitative examples;
- otherwise hand the architecture question to #451.
