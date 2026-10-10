# Connect Providers

`mb connect` records safe provider metadata in the business repo and stores
credential material outside git.

Use it when a business workflow needs a durable handle to an external account:
site deploys, ads, email, payment, research, bookkeeping, or a private finance
source. `mb connect` answers whether the credential is present, whether a safe
readiness check has passed where supported, and which command repairs the first
broken step.

## Secret Boundary

Tracked repo metadata may include:

- provider id;
- account label;
- non-secret metadata such as account role or token type;
- secret-store backend name;
- secret refs.

Tracked repo metadata must not include:

- API tokens, keys, refresh tokens, passwords, or service-account JSON;
- raw provider exports;
- account-private finance, customer, member, payroll, legal, or tax data.

By default, Main Branch selects the native secure store for the current host:
the macOS login Keychain or the Linux Secret Service default collection. It
never falls back automatically to plaintext storage. Unknown selectors and
metadata naming a backend from another operating system fail closed.

Use an explicit backend only for controlled setup or tests:

```bash
MB_CONNECT_SECRET_BACKEND=macos-keychain mb connect cloudflare --token-stdin
MB_CONNECT_SECRET_BACKEND=secret-service mb connect cloudflare --token-stdin
MB_CONNECT_SECRET_BACKEND=local-file mb connect cloudflare --token-stdin
```

`local-file` is a legacy compatibility option and must be selected explicitly.
Existing metadata labeled `keyring` is read through the matching native
adapter; new connections record the native backend name.

The public `--token` option remains as deprecated input compatibility. A value
supplied there is visible in the caller's process arguments. Main Branch never
uses that option in generated commands or internal helper invocation; use
`--token-stdin` for real credentials.

## Using a Credential: `exec`

`mb connect exec <provider> [--env NAME] -- <command> [args...]` runs one
command with the stored credential in that command's environment and nowhere
else:

```bash
mb connect exec stripe -- stripe products list --limit 3
mb connect exec cloudflare -- npx wrangler pages deployment list
mb connect exec mercury --env MERCURY_TOKEN -- python3 scripts/import.py
```

- No shell is involved: the words after `--` are the program and its
  arguments, exactly as given.
- The secret is never printed, logged, or returned in JSON. stdin, stdout and
  stderr belong to the command.
- The exit code is the command's own; a command killed by a signal exits
  `128 + signal`, as in a shell. `mb connect exec` itself exits 1 when the
  credential cannot be read, 2 for a refused request, and 127 when the
  command is not found.
- Default variable: the provider's own, which is its first registered
  environment variable (`CLOUDFLARE_API_TOKEN`, `GITHUB_TOKEN`,
  `RESEND_API_KEY`, `APIFY_TOKEN`, Meta's `ACCESS_TOKEN`, and so on). Stripe
  uses `STRIPE_API_KEY`, which the Stripe CLI reads, and Google uses
  `GOOGLE_OAUTH_TOKEN`. Custom ids and providers with no registered variable,
  such as GA4, get `MB_SECRET`. `--env` overrides it.
- `--repo` selects the business repo, and a user-scoped connection resolves
  from a worktree as it does for `status`.

This is the path agents and scripts should use. What the command prints is
still the command's business: avoid commands that echo their environment.

## Raw Read: `token`

`mb connect token <provider>` prints the raw credential with no added newline.
It refuses when stdout is a terminal or a pipe, because both put the secret
into some other process's text: a transcript, a log, a variable an agent later
prints. The refusal points at `exec` on stderr. A plain redirect to a file is
neither, so it works without any flag:

```bash
mb connect token stripe > "$private_tmp/stripe-key"
```

`--print` is needed only for a terminal or a pipe: it lifts the refusal there.
Use it only when nothing reading that output is an agent or a log.

Exit codes, stable for scripts. The checks run in this order, and the first
that fails decides the code:

1. Usage: no provider, or `--json`: exit 2.
2. The stdout gate: stdout is a terminal or a pipe and `--print` was not
   given: exit 3. This comes before any lookup, so a provider that is not
   connected, or not even known, still exits 3 here.
3. The lookup, only once the gate has passed: an unknown provider or one with
   no secret slot exits 2; a provider that is not connected, a missing
   credential, or a store that cannot read it exits 1 (stderr says which and
   names the repair).
4. Otherwise the value is written to stdout: exit 0.

| Exit | Meaning |
| --- | --- |
| 0 | The value was written to stdout. |
| 1 | After the stdout gate passed: no value (not connected, missing, or unreadable). |
| 2 | Usage error, or a refusal other than the stdout gate (unknown provider, no secret slot). |
| 3 | Refused by design: stdout is a terminal or a pipe and `--print` was not given. Checked before the provider is looked up. |

`--json` is not supported: the token is the whole stdout contract. Passing it
exits 2 and prints only a `json_not_supported` error envelope (see
[JSON on failure](#json-on-failure)); the token is never in JSON.

### Breaking in 0.6.0 (not flagged at the time)

0.6.0 made `mb connect token <provider>` refuse a terminal or a pipe. Scripts
that captured the value through stdout stopped working, for example
`TOKEN=$(mb connect token stripe)` (command substitution reads through a pipe)
or `mb connect token stripe | tool`. Through 0.6.1 the refusal exited 2, the
same code as usage errors; from 0.6.2 it exits 3, so a wrapper can tell
"refused by design" from "no credential". To migrate:

- Run the command with the credential instead:
  `mb connect exec <provider> -- <command>`. The value reaches only that
  command's environment (see `exec` above).
- Where a script must hold the raw value, prefer a plain redirect to a private
  file: `mb connect token <provider> > file`. That needs no flag, because a
  file is neither a terminal nor a pipe. Command substitution reads through a
  pipe, so it needs `--print`: `TOKEN=$(mb connect token <provider> --print)`
  works, but keeps the value in the shell.

The product model behind this surface lives in
[connection-model.md](connection-model.md).

## Stored Is Not Verified

`mb connect test` and `mb connect status --json` report three separate facts
per provider:

- `stored`: a credential resolved from the credential backend.
- `provider_verified`: a provider call actually confirmed that credential.
  `false` when Main Branch has no safe read-only probe for the provider.
- `verified_at`: when the credential last worked. `""` if it never has. It
  keeps the earlier timestamp after a later failure, because when a credential
  last worked stays true even once it stops working.

The invariant, stated precisely: **for a provider with `required_secrets`,
`ready` and `ok: true` require `provider_verified: true`.** Cloudflare, Apify,
Meta, Stripe, GitHub and GA4 have real probes (see [Probes](#probes)). Every
other built-in provider, and every custom provider, reports
`stored, unverified`: the credential is present and readable,
and nothing has checked that it works. `mb connect doctor` and `mb status` grade
that as a warning, not a pass.

The scoping matters. A provider with no `required_secrets` sends nothing to a
provider, so there is no credential to confirm and `provider_verified` stays
false. Such a provider is not covered by the invariant and keeps reporting
`ready` from its repo-local metadata — see below. Claiming `provider_verified`
for it would be the same overclaim this behavior exists to remove.

There is no repair command for `stored, unverified` on a provider with no
probe. Rerunning `mb connect test` records the same answer, so confirm the
credential in the provider's own dashboard, or let the first real workflow run
be the check.

### What the exit code means

An exit code from `mb connect test`, `mb connect status`, and `mb connect
doctor` answers one question: **is there something you can act on?** All three
surfaces answer it the same way, so there is no lenient command to run instead.

| Situation | Exit |
| --- | --- |
| `unvalidated`, `invalid`, `missing_secret`, credential-backend failure | 1 |
| `stored, unverified` on a provider **with** a probe | 1 — run `mb connect test` |
| `stored, unverified` on a provider **with no** probe | 0 — nothing to run |
| `ready` | 0 |

The table covers provider readiness. `mb connect doctor` also checks GitHub
context and credential-backend health, and either can still exit 1 on its own —
both name a command to run.

The probe-less case exits 0 on purpose. A red that nobody can clear gets
ignored, and these providers can never turn green until a probe exists
upstream. Only the process exit softens: the provider still reports
`ok: false`, doctor still grades it `warn`, and the verification fields stay
truthful. Each provider carries `has_probe` in `mb connect status --json`, and
`mb connect doctor` names the connected providers that lack one so the gap is
visible and fixable upstream.

A provider that needs no credential at all, such as `hledger`, still reports
`ready` from repo-local metadata, with `stored: false` and
`provider_verified: false`. Its readiness is a statement about repo-local
metadata, never about a provider call. Read `provider_verified` as "a provider
call confirmed a stored credential", not as "this provider is unhealthy".

Metadata written before this behavior existed recorded `ready` without
recording whether a provider was called, so it reads as `stored, unverified`
until `mb connect test` runs once more. Nothing is rewritten, and a provider
with a real probe returns to `ready` after one re-test.

### Configured, connected, present

Each provider in `mb connect status --json` separates what is recorded from
what is stored:

- `configured`: the repo or user scope has an entry for the provider. Status
  counts, `summary.configured`, and the exit code cover every configured
  provider.
- `connected`: a credential was stored when the entry was written. A connect
  without a token for a provider that has none yet, for example
  `mb connect cloudflare --metadata zone_id=...` or
  `mb connect stripe --source op://...`, records the metadata and source only:
  `connected: false`, no secret ref, and state `missing_secret` with the
  connect command as repair. `mb connect rotate` or a connect with
  `--token-stdin` then stores the secret and sets `connected: true`. A
  tokenless reconnect of an entry that already has a secret keeps its ref.
  Entries written by earlier releases with a ref and nothing behind it keep
  reading as `missing_secret`.
- `secrets.<field>.presence`: `present`, `absent`, or `unknown`. `unknown`
  means the credential backend could not answer (`backend_ok: false`, with
  the reason in `backend_state`); `present` is then `null`, never `false`.
  `present: false` always means the credential is known to be absent.
- Optional slots: a provider can have slots it does not require, such as
  Google's `oauth_grant`. One shows in `secrets` with `optional: true` only
  when the entry records it, and a missing optional slot never makes a
  provider `missing_secret` or changes `stored`. Google entries also carry
  `credential_mode`: `oauth` when the entry records an `oauth_grant`,
  otherwise `access_token`.

`mb connect status --json` also carries a top-level `credential_backend`
block (`backend`, `ok`, `state`, `summary`, `repair`, `repair_command`), even
with no provider connected. With recorded secrets it reuses their probes;
otherwise it checks the backend a new connect would use, so a locked or
missing store shows before the first connect fails on it. It is information
only: it does not change `ok`, the summary counts, or the exit code.

## JSON on failure

With `--json`, every `mb connect` failure that exits non-zero without a
result also prints one JSON object on stdout, with the shared
[result envelope](json-output-contract.md) fields. The human message stays on
stderr, and the exit code is the same as without `--json`. Without `--json`
nothing changes: stdout stays empty.

```json
{
  "ok": false,
  "state": "backend_unavailable",
  "backend_state": "keychain_locked",
  "summary": "...",
  "repair": "...",
  "repair_command": "security unlock-keychain ~/Library/Keychains/login.keychain-db",
  "exit_code": 1,
  "safe_to_share": true,
  "errors": [{"code": "backend_unavailable", "message": "..."}],
  "mb_command": "mb connect",
  "result_status": "error"
}
```

`state` (and `errors[0].code`) is stable for scripts:

| `state` | Exit | Meaning |
| --- | --- | --- |
| `usage_error` | 2 | Missing provider, extra argument, or missing `--keychain`. |
| `json_not_supported` | 2 | `--json` on `token` or `exec`, whose stdout belongs to the value or the command. |
| `needs_terminal` | 2 | `repair --keychain` without a terminal. |
| `refused` | 2, or 3 for `token` | A policy refusal; `rule` names it, for example `source_secret_value`. |
| `invalid_request` | 2 | Unknown provider or another rejected request. |
| `config_boundary`, `config_corrupt` | 2 | `.mb/connect.yaml` is outside the repo or cannot be parsed. |
| `backend_unavailable` | 1 | The credential backend failed; `backend_state` is the sanitized reason. Nothing was stored. |
| `missing_env_credential` | 1 | `--from-env` found none of the provider's variables. |
| `connect_failed` | 1 | Another runtime failure. |
| `unexpected_error` | 1 | An unexpected error; details are hidden because they may hold a secret. |

No envelope carries a secret value or raw backend output, and the stderr
message gets the same redaction as the envelope. A failure message never quotes
input that could be a credential: a metadata key, provider name, extra argument
or command that looks like a secret is replaced with
`(not shown: it may be a credential)`, and a refused metadata pair is also
named by its `--metadata` position.
A metadata key that looks like a secret is refused (rule
`metadata_secret_key`) and nothing is stored, and one already in
`.mb/connect.yaml` is left out of status and identity output. Usage errors that
come from argument parsing itself (an unknown option, an unexpected extra
argument, an invalid value) exit 2 with the usage line and no JSON envelope,
and get the same replacement.

## Probes

Every probe is a read-only GET. Response bodies are never returned or stored;
only the outcome, the HTTP status, and the facts listed here.

| Provider | Probe | Extra facts recorded |
| --- | --- | --- |
| Cloudflare | token verify (user or account token) | none |
| Apify | current user | none |
| Meta | Meta's Ads CLI read smoke | per-command results |
| Stripe | list products, prices, customers and charges (`limit=1`) and read the balance | `scopes`: `allowed`, `refused` or `unknown` per resource |
| GitHub | authenticated user | `token_kind`; `token_scopes` for classic tokens |
| GA4 | the configured property, from the Admin API | none |

Stripe: a 2xx means the key may read that resource, a 403 means the key is
valid but restricted from it, and a 401 on any probe means Stripe rejected the
key itself. A restricted key that reads products and prices but not customers
is `ready`, with the refusals named in the summary and in `scopes`.

GitHub: classic tokens report their scopes through the `X-OAuth-Scopes`
header. GitHub does not list a fine-grained or app token's permissions through
the API, so the probe says so instead of guessing. The GitHub entry stores its
token in an `api_key` slot, which keeps a GitHub token connected earlier with
`--custom` readable.

GA4: the probe needs the numeric property id as metadata. Without it the test
reports `unvalidated` and names the command:

```bash
mb connect ga4 --token-stdin --metadata property_id=<property-id>
mb connect test ga4
```

The GA4 credential is an OAuth access token with Analytics read scope.

## Metadata Is Judged by Value

`--metadata key=value` is for labels and ids. A value that looks like a secret
is refused, and nothing is stored. The value is judged whole and word by
word, so a short label in front of a key (`note: <key>`) does not hide it. The
rules:

- `credential_prefix:<prefix>`: a public credential grammar matched in full,
  prefix and generated part together (for example `sk_live_`/`sk_test_`,
  `rk_`, `pk_live_`, `whsec_`, Resend `re_<8>_<16+>`, `ghp_` and the other
  GitHub token prefixes, `github_pat_`, `glpat-`, `xox?-`, `AKIA`, `AIza`).
  A word that only shares a prefix, such as `re_engagement` or
  `pk_test_publishable`, passes;
- `jwt_shape`: three dot-separated base64url segments starting `eyJ`;
- `bearer_credential`: a value starting `Bearer `, or `Bearer <long token>`
  after a label;
- `high_entropy`: 24 or more token characters, mixed case, enough entropy, and
  at least 30% of its CamelCase/digit segments look generated (a single
  letter, a letter run with no vowel, or a lone digit). Labels are made of
  words, so `UsEuUkCaAuNzApiKeyName2026` and `HTTPSRedirectCheckerProdV2`
  pass. A short letter-digit code between words counts as a word when the
  rest of the value reads as words (a final version digit is allowed), so
  `CloudflareR2StorageBucket`, `B2BMarketingCampaignOctober2026` and
  `S3ProductionBucketUsWest2` pass too, and a code next to a generated tail
  is judged letter by letter.

A value is judged whole and word by word. URLs, emails and env references
stay whole. Each part of a URL (user name, password, host labels, path
segments, query keys and values, fragment pieces) is percent-decoded until
stable (at most three passes) before it is split, then split on `:` and
`=` and judged like a bare value; a URL nested in a part is judged the same
way, up to three levels deep. So `?campaign=CloudflareR2StorageBucket`,
`/docs/getting-started`, IP addresses and `xn--` host labels pass, and a
token in `?token=`, `/token=`, `#token:`, a path segment, a user name, a
host label or behind an encoded `%2F` is refused. A URL that does not
parse, such as one with a bad port, is judged from its decoded raw pieces.

Measured limits of `high_entropy`, 10,000 random values each from
`random.Random(987)` (the test `test_metadata_high_entropy_miss_rates_match_docs`
keeps these numbers current): it misses 33 of 10,000 (0.33%) 24-character
alphanumeric values, 37 of 10,000 (0.37%) 24-character base64-alphabet values
and 168 of 10,000 (1.68%) 40-character mixed-case values with no digits.
Values shorter than 24 characters, and all-lowercase or all-uppercase random
strings, are not judged by entropy at all: hex ids and UUIDs look the same.
Metadata detection is a heuristic, not complete token detection: a value
built only from invented pronounceable words around a short code, for
example `AmoriavenaR2UlenavopiraPavirelona`, reads as a label and passes,
because it looks like `CloudflareR2StorageBucket`. Metadata is a label
field, not a secret scanner; pass credentials with `--token-stdin`.

Hex ids, UUIDs, numeric ids, URLs, emails, paths, `op://` references,
`${VAR}` references and CamelCase labels pass. The key name alone never
refuses, so labels such as `key_name=Main restricted key` or
`onepassword_item=Stripe restricted` are fine. The refusal names the rule and
the key, never the value.

## Refusals Are Logged Locally

Each refusal above that ends an `mb connect` command appends one line to the
local feedback log (see [feedback.md](feedback.md)): the rule name as
`connect.<rule>`, the command path, the repo kind, the time and the mb
version. It never holds the refusal message, the value, a path or a token, and
nothing is sent anywhere. `mb feedback rollup` counts them by rule. Set
`MB_FEEDBACK_LOG=0` to turn this off; a log that cannot be written never
changes the refusal or its exit code.

## Custom Providers

Use `--custom` when the provider is not in the built-in registry yet. Custom
provider ids use lowercase letters, digits, and hyphens. They get one
`api_key` secret slot and the same status, doctor, list, token, repo-scope, and
user-scope behavior as built-in providers.

Example: a read-only finance provider token.

```bash
MB_CONNECT_SECRET_BACKEND=macos-keychain \
  mb connect mercury \
    --custom \
    --token-stdin \
    --account "Mercury Operating Account" \
    --metadata role=operating_cash_source \
    --metadata auth_state=api_token
```

This writes safe metadata and a secret ref under `.mb/connect.yaml`; the token
goes to the selected local secret backend.

Check it without printing the token:

```bash
mb connect status mercury --json
mb connect status --all --json
mb connect doctor --json
mb connect list --json
mb connect identity --json
```

Run a local importer or scheduled collector with the token in its
environment:

```bash
mb connect exec mercury --env MERCURY_TOKEN -- python3 scripts/import_mercury.py
```

The script reads the variable and keeps the token in memory and out of
child-process arguments:

```python
import os
import urllib.request

request = urllib.request.Request(
    "https://api.example.invalid/accounts",
    headers={"Authorization": f"Bearer {os.environ['MERCURY_TOKEN']}"},
)
with urllib.request.urlopen(request, timeout=10) as response:
    payload = response.read()
```

Do not place a credential in a command argument, use `set -x`, echo it, write a
committed `.env` file, or log request headers. Raw exports should go to a private
workspace or an ignored local staging path, not to a public repo.

If metadata exists but the secret is missing, Main Branch reports
`missing_secret` and gives a reconnect command that includes `--custom`, for
example:

```bash
mb connect mercury --custom --token-stdin
```

## When the credential backend itself is unhealthy

A missing provider secret and an unusable secret backend are different
problems, and only the first is fixed by reconnecting. Main Branch reports
locked, unavailable, incompatible, and timed-out stores as sanitized backend
states. Every native call runs in a helper process, and an aggregate status,
test, or doctor command shares one eight-second credential-store deadline;
unattended reads suppress operating-system unlock UI.

On macOS, unlock the login Keychain interactively inside the reader's owning
user security session, then leave that session running:

```bash
mb connect doctor --json
security unlock-keychain ~/Library/Keychains/login.keychain-db
```

A desktop unlock does not necessarily unlock an already-running remote security
session. Scheduled macOS readers should run as a user `LaunchAgent` in the
logged-in user's GUI launchd domain; Main Branch does not install a daemon,
broker, or launchd job. A new security session or reboot can require another
interactive unlock in that owning session.

Keychain item access control is separate from Keychain lock state. A macOS
Keychain item trusts the program that created it. Main Branch reads and writes
its items through Apple-signed `/usr/bin/security`, whose identity stays the
same across Python, uv, `mb` and macOS updates, so changing the Python under
`mb` does not bring back an access dialog. Values reach `security` only on
stdin, hex-encoded (`security -i`), never in process arguments; a value too
long for one `security -i` line is written as an empty item by `security` and
filled in through the Security framework, which keeps the same access list.

Items stored by `mb` before this change trust the Python that created them.
The first read that this Python can do moves the item to `security` as a staged
move, so no step can lose the credential:

1. the full value is written to a temporary `security` item next to the old one
   and read back;
2. the old item is removed;
3. the final `security` item is written and read back;
4. the temporary item is removed.

If a step fails, the old item is put back and the temporary copy is kept. If
the process is killed between steps, the next access of that credential, in
any command, finishes or undoes the move from the temporary copy before doing
anything else. A move starts only when at least 3 seconds remain before the
command's deadline; otherwise the read returns the value without moving it,
and the next read moves it. This happens silently in any command, including
unattended ones, with keychain interaction off.

Unattended reads do not wait on a keychain dialog. Every command reads with
keychain interaction turned off, so an item this Python is not trusted to read
fails at once with the `keychain_prompt_pending` state instead of running into
the safety deadline. A locked keychain fails at once with `keychain_locked`,
since unlocking would also need a dialog. Main Branch runs `security` only on
items whose access list already trusts it, because `security` itself cannot be
told to fail instead of showing a dialog.

One case is not detected: an item whose access list was edited by hand (in
Keychain Access, or with `security set-generic-password-partition-list`) so
that `/usr/bin/security` comes first while its partition list lacks
`apple-tool:`. Main Branch never creates such an item. Telling it apart needs
the item's partition list, which the public Security API does not expose, so
Main Branch reads it like any other `security`-owned item; `security` may then
raise a dialog. The command's deadline bounds it: it stops waiting, kills
`security`, and reports `keychain_prompt_pending`. To fix such an item, delete
it in Keychain Access and connect the provider again.

`ready` in `mb connect status` means the credential can be read now; it does
not prove the item has moved to `security`. An item still owned by the old
Python reads as `ready` until a Python change, then as
`keychain_prompt_pending`. `mb connect repair --keychain` is the check that
reports whether each item has moved.

When an item reports `keychain_prompt_pending`, run this once from a terminal
in the hub, at the screen, and choose **Always Allow** for each dialog (Allow lets only that one read
through):

```bash
mb connect repair --keychain
```

It is the only command that lets macOS show the keychain dialog. It refuses to
run without a terminal, waits up to 60 seconds per credential, moves each
credential it can read to `security`, and never prints a value. It reports a
credential as `repaired` only after a fresh unattended read succeeds and shows
the item owned by `security`. A credential it can read but could not move
reports `readable_not_migrated`: it works now but would ask again after a
Python change, so run the command again. Otherwise it says the prompt is still
pending. A credential already owned by `security` reports `ready`. After every
credential reports `ready` or `repaired`, Python and `mb` updates do not ask
again. Never reset or delete the login keychain to repair one item.

With several business repos, repair every item on the machine in one pass:

```bash
mb connect repair --keychain --all
```

It lists the `mainbranch` items in the keychain by their attributes only (no
values are read and no dialog can appear while listing), then repairs each one
exactly as above: a dialog only for an item that needs one, the same
`repaired` / `readable_not_migrated` / `still_pending` verdicts, and one
summary with the count per state and what is still pending. Each item is
labelled with its hub and provider when this repo or a hub checkout in the
`mb fleet` hub list records it (reading the hub list needs Python 3.11 or
newer, as `mb fleet` does), otherwise by its keychain ref. A staged copy
left by an interrupted move is not repaired on its own: its item is read,
which finishes or undoes the move. One pass lists at most 2000 items; past
that it says the pass is incomplete, with how many items it did not check,
exits 1, and names `mb connect repair --keychain` to run in each hub for the
rest. Like the per-repo repair, it needs a
terminal, refuses to run without one, and never prints a value.

To move an existing install, in this order, from a terminal in the hub:

1. `mb update`. It runs `uv tool install --refresh-package mainbranch
   mainbranch@latest`, which keeps the Python the tool already uses; `uv tool list --show-python` shows it before
   and after. Do not upgrade or reinstall uv's Python until step 3 reports
   nothing pending: a new Python cannot read items that have not moved yet.
2. `mb connect status`. Every credential this Python can read moves to
   `security` silently; the rest report `keychain_prompt_pending`.
3. `mb connect repair --keychain`, at the screen, choosing **Always Allow** for
   each dialog. Run it again until every credential reports `ready` (already
   owned by `security`) or `repaired`, and nothing is pending. With several
   hubs, `mb connect repair --keychain --all` does every hub in one run.

On Linux, Main Branch uses the existing Secret Service default collection. It
checks collection and item lock state and never calls an unlock method. Unlock
the collection in the user's desktop keyring application before starting the
unattended reader.

A connect attempt that fails on the backend stores nothing and leaves repo
metadata unchanged. Replacement updates an existing Keychain item in place; an
item stored before the `security` change is updated in place first and then
moved with the staged move above, which keeps a verified copy until the final
item reads back. New Keychain items are written through the same staged move,
so a failed write never leaves an empty credential. Secret Service updates a
matched item in place while preserving its attributes, including legacy Python
keyring attributes. New Secret Service items use its replacement contract.
Helper stderr and raw exceptions are discarded.

Reconnecting an already configured custom provider also works without
`--custom`, but keeping the flag in repair output makes the command safe to
reuse from a fresh or partially repaired repo.

For rotation, run the same command with the new token:

```bash
MB_CONNECT_SECRET_BACKEND=macos-keychain \
  mb connect mercury --custom --token-stdin
```

Rotation updates only the selected business's `repo_id`-scoped reference. A
same-named provider in another business is not a sibling and is never rewritten.

### Storing a secret again

Storing a new secret for a provider that is already connected, custom or
built in, in repo or user scope, replaces the secret only. The recorded account
label and metadata stay unless the command gives new ones:

```bash
mb connect <provider> --token-stdin                       # keeps label and metadata
mb connect <provider> --token-stdin --account "New label" # replaces the label
mb connect <provider> --token-stdin --account ""          # clears the label
mb connect <provider> --token-stdin --metadata region=eu  # sets one key, keeps the rest
mb connect <provider> --token-stdin --metadata region=    # removes that key
```

`--json` adds a `reconnect` key saying whether the label was `kept`,
`replaced` or `cleared`, and which metadata keys were kept, set or removed
(names only). A first connect and a metadata edit without a secret record
exactly what they are given, as before. A kept `mode=live` still refuses a
Stripe test key; pass `--metadata mode=test` with it.

### Rotate from a recorded source

Record where the credential lives once, as a non-secret reference:

```bash
op read "op://Business/Stripe restricted/credential" \
  | mb connect stripe --token-stdin --source "op://Business/Stripe restricted/credential"
```

`--source` stores the reference as `metadata.source`. Given on its own, with
no `--metadata`, it keeps the existing metadata and adds the source. A source
that looks like a secret itself is refused.

After the key is rolled in the provider and updated in 1Password:

```bash
mb connect rotate stripe
```

`rotate` re-reads the credential with `op read <ref>` (no shell; the value is
never printed), stores it through the same path as a connect, keeps the
account label, metadata, scope and backend, and runs the provider probe. The
exit code follows `mb connect test`. It refuses, with exit 2 and the next
step, when no source is recorded, when the source is not an `op://`
reference, when the 1Password CLI is missing, and when it is not signed in.

A Google sign-in has no source to re-read, so `mb connect rotate google`
refuses and names the sign-in instead. With no connection, or only metadata,
it names `mb connect google --oauth`. On a sign-in, it names the `--reauth`
that renews it, as status does. Only a connection made with a plain access
token keeps the `--token-stdin` and `--source` path.

Then verify readiness without printing the token:

```bash
mb connect status mercury --json
mb connect doctor --json
mb connect identity --json
```

Recommended custom metadata for finance providers:

```text
role=operating_cash_source
access_level=read_only
data_domain=banking
auth_state=api_token
source_system=mercury
account_ref=operating-cash
```

Use `account_ref` as a business-readable handle. Do not commit raw account
numbers, routing numbers, statements, transaction rows, tax records, or provider
payloads.

## Google: Search Console and GA4

`mb connect google --oauth` signs a business repo in to Google once, for
read-only Search Console and GA4 (scopes `webmasters.readonly` and
`analytics.readonly`). A person runs it, never a skill or an agent: it ends
in a Google consent screen that only the account owner can answer. Plain
`mb connect google` is unchanged and never opens a browser.

Once signed in, `mb connect token google` and `mb connect exec google`
hand out a short-lived access token minted from the sign-in (see "Reading
with the sign-in" below), and `mb connect test google` checks the sign-in
with one read-only call to each product it granted (see "Checking the
sign-in"). To read reports without handling a token, use the typed
read-only commands in [`google.md`](google.md): `mb google sc query`,
`mb google sc sitemaps list` and `mb google ga4 report`.

### One-time setup in Google Cloud

Do this once per operator, not once per business. One OAuth client can
serve every business repo you run.

1. Create (or pick) a Google Cloud project you own.
2. Enable the **Google Search Console API** and the **Google Analytics Data
   API** in that project.
3. Set the OAuth consent screen to user type **External** and publishing
   status **In production**. A project left in **Testing** gets refresh
   tokens that expire after 7 days, so every repo would need a new sign-in
   each week.
4. Create an OAuth client of type **Desktop app** and download its JSON.
   Keep that file out of every repo.

The app can stay unverified. Google then shows a "Google hasn't verified this
app" screen once per sign-in; choose to continue, since it is your own app.

The Google account you sign in with must already see the Search Console
property and have at least read access to the GA4 property.

### Sign in

From the business repo:

```bash
mb connect google --oauth --client-file ~/Downloads/client_secret_<id>.json \
  --metadata search_console_site=sc-domain:example.com \
  --metadata ga4_property_id=123456789
```

What you see:

```text
Google sign-in (read-only: Search Console, Analytics)
Opening your browser. If it does not open, visit:
  https://accounts.google.com/o/oauth2/v2/auth?...
Waiting for Google on http://127.0.0.1:<port> (5 min)...
Granted (read-only): Search Console, Analytics (GA4)
Stored: yes (stored in the macOS login Keychain)
metadata: .../.mb/connect.yaml
Checked with Google (read-only): ok
summary: Google sign-in verified: Search Console and Analytics (GA4) read with it.
  search_console: ok
  ga4: ok
See it with `mb connect status google`.
```

The sign-in's last step is the same check as `mb connect test google`, made
with the access token from the sign-in itself (no extra token request). The
sign-in is already stored when it runs, so the command's exit code is the
sign-in's; a failed check prints its rule and a `next:` line instead.

- `search_console_site` is the property as Search Console names it:
  `sc-domain:example.com` for a domain property, or a URL prefix such as
  `https://www.example.com/` (it must end in `/`).
- `ga4_property_id` is the numeric property id; `properties/123456789` is
  accepted and stored as `123456789`. A measurement id (`G-...`) is refused.
  The separate `ga4` provider (an access token checked against the Admin
  API) keeps its own `property_id`; the two do not share a connection.
- `--client-stdin` reads the client JSON from stdin instead of a file. The
  client JSON is never an argument value.
- `--timeout SECONDS` (default 300) bounds the wait for the browser.
- The redirect comes back to `http://127.0.0.1:<port>` on this machine only.
  The URL carries no secret; PKCE and a one-time `state` protect the code.

What is stored: one credential-store item holds the grant (client id, client
secret when the client file has one, refresh token), a second holds the
access token from the sign-in, and `.mb/connect.yaml` records their refs plus
`search_console_site`, `ga4_property_id` and `oauth_grants` (which products
you allowed). No token or client secret is ever written to the repo.
`mb connect status google` then shows `stored` with `credential_mode: oauth`,
and `oauth.refresh_token_expires_on` (a UTC date) when Google put a time
limit on the sign-in; it is `""` otherwise.

With no Google connection, `mb connect status google`, `mb connect test
google`, `mb connect token google` and `mb connect exec google` name
`mb connect google --oauth` as the next step (`repair_command` in `--json`).
On a sign-in connection whose stored sign-in can still be read (only the
access token is missing, or the check failed), they name
`mb connect google --oauth --reauth`. When the stored sign-in itself is gone or
can't be read (for example, after the credential store was reset), they name
`mb connect google --oauth --reauth --client-file <Desktop client JSON>`:
`--reauth` reads the OAuth client from the stored sign-in, so without it the
client file must be passed. Only a connection made with a plain access token
keeps `--token-stdin`, the one way to replace that token.

Status, `--reauth`, `mb connect test`, `token` and `exec` judge the stored
sign-in by one rule. It is usable when it holds its OAuth client and a
refresh token. If it still holds the client but not the refresh token, the
next step is `mb connect google --oauth --reauth`. If it is gone or its client
can't be read, the next step is the `--client-file` form. A stored sign-in
that is gone reads `missing_secret`. One that can't be used reads `invalid`,
unless an earlier check already recorded `reauth_required`, which it keeps
reading. A locked or unavailable credential store reads `backend_unavailable`
and names the store repair first, because the sign-in can't be read until the
store unlocks. None of these reads `ready`, whatever an earlier check
recorded. The OAuth client's `client_secret` in the stored sign-in is a
string, or is left out. `null` and `""` read as left out (a client with no
secret); any other value (a list, an object, a number, `true` or `false`)
makes the stored sign-in unreadable, with the same next step on every path.
`--json` shows this
as two booleans under `secrets.oauth_grant`: `readable` (the client can be
read) and `usable`. The stored values are never shown.

### Reading with the sign-in

On a sign-in connection, `mb connect token google` and
`mb connect exec google -- <command>` read the stored grant, ask Google's
token endpoint for a fresh access token, and use that token. The refresh
token and client secret stay inside the `mb` process: they never reach the
command, its arguments, stdout, stderr or any JSON. The minted token is not
written back to the credential store, and one `mb` process asks Google once
(it reuses the token until a minute before Google says it expires).

```bash
mb connect exec google -- python3 scripts/search_console_report.py
```

The command gets one variable, `GOOGLE_OAUTH_TOKEN`, holding an access
token that lives about an hour. A command that puts it into an argument,
such as `curl -H "Authorization: Bearer $GOOGLE_OAUTH_TOKEN" ...` inside
`sh -c`, shows it to anything that can list processes for as long as that
command runs, and the token stays usable for up to an hour. Prefer a script
that reads the variable itself, or the typed `mb google ...` read commands,
which keep the token inside `mb` (see [`google.md`](google.md)).

When minting fails, `token` and `exec` exit 1 (the command never runs), print
one line naming the problem and, where one helps, a `repair:` line. Google's
own error text is never shown.

| Rule | Meaning | What to do |
| --- | --- | --- |
| `reauth_required` | Google refused the stored sign-in: revoked, the 7-day Testing expiry, six months unused, past the 100-token limit, or a session-control policy (`invalid_rapt`). | A person runs `mb connect google --oauth --reauth`. |
| `oauth_client_rejected` | Google refused the OAuth client in the sign-in (deleted, or its secret changed): `invalid_client`. | `mb connect google --oauth --reauth --client-file <Desktop client JSON>` with the current client file. |
| `oauth_client_unauthorized` | Google says the client may not use this grant (`unauthorized_client`), usually not a Desktop app client. | Check the client type, then `--reauth --client-file <Desktop client JSON>`. |
| `oauth_scope_rejected` | Google refused the recorded read-only scopes (`invalid_scope`). | `--reauth --client-file <Desktop client JSON>`. |
| `token_request_rejected` | Google refused the refresh request for another reason (`invalid_request` or a code `mb` does not know; the code itself is never shown). Nothing about the sign-in is known to be wrong. | Try again later. Nothing is recorded. |
| `oauth_grant_malformed`, `oauth_grant_missing` | The stored grant can't be read or has no refresh token (`malformed`), or is gone from the credential store (`missing`). | `mb connect google --oauth --reauth --client-file <Desktop client JSON>`. If the grant still holds its OAuth client, `mb connect google --oauth --reauth`. |
| `token_unreachable`, `token_request_failed`, `token_response_malformed`, `token_unexpected_redirect` | Google's token endpoint could not be reached; answered with a server error, a timeout (408), a rate limit (429) or an error carrying no OAuth code; sent an unreadable answer; or answered with a redirect (never followed, so the grant never reaches a second URL). Nothing about the sign-in is known to be wrong. | Try again later. Nothing is recorded. |

A credential store that is locked or unavailable reads as
`backend_unavailable`, as for every other provider.

`reauth_required` is recorded in the connection metadata when a read sees
it, so `mb connect status google` (which never calls Google) shows
`state: reauth_required` with the `--reauth` repair and exits 1. A later
successful read, or the `--reauth` sign-in, clears it. The other failures
are not recorded, so a network blip never changes status.

### Checking the sign-in

```bash
mb connect test google
```

On a sign-in connection this mints an access token (as `token` and `exec`
do), then makes one read-only call for each product the sign-in granted and
whose id is recorded:

- Search Console: `searchAnalytics.query` on `search_console_site`, for one
  past day, `rowLimit: 1`, no dimensions;
- GA4: `runReport` on `ga4_property_id`, metric `activeUsers`, one explicit
  past date, `limit: 1`.

No row, number or Google message is shown or recorded; only which rule
fired. Verified (`ready`, exit 0) means every recorded product passed. A
product you did not grant at sign-in is skipped (`grant_missing`) and does not
fail the other.

```text
$ mb connect test google
mb connect test google: ok (ready)
summary: Google sign-in verified: Search Console and Analytics (GA4) read with it.
  search_console: ok
  ga4: ok

$ mb connect test google        # no ga4_property_id recorded
mb connect test google: warn (unvalidated)
summary: Analytics (GA4) is granted, but no ga4_property_id is recorded.
  search_console: ok
  ga4: unvalidated (ga4_property_not_recorded)
    Find the numeric property id under GA4 Admin > Property details, then run `mb connect google --metadata ga4_property_id=<property-id>` and `mb connect test google`.
next: mb connect google --metadata ga4_property_id=<property-id>
```

`mb connect google --metadata KEY=VALUE` on a sign-in connection updates
that key and keeps the other recorded ones (and the sign-in). An empty value
removes a key: `mb connect google --metadata search_console_site=` or
`--metadata ga4_property_id=`. The reads then refuse with `site_not_recorded`
or `property_not_recorded`, and the check reports the id as not recorded.
Either edit clears the recorded check, so run `mb connect test google` again
afterwards.

Each product outcome has a stable rule (`search_console_...` or `ga4_...`):

| Rule | Meaning | What to do | Recorded |
| --- | --- | --- | --- |
| `ok` | The read worked. | Nothing. | yes |
| `grant_missing` | Not granted at sign-in; skipped. | To add it, a person runs `mb connect google --oauth --reauth` and ticks its box. | yes |
| `search_console_site_not_recorded`, `ga4_property_not_recorded` | Granted, but no valid id is recorded. | `mb connect google --metadata search_console_site=<site>` or `--metadata ga4_property_id=<property-id>`. | yes (`unvalidated`) |
| `*_no_access` | HTTP 403 or 404: the signed-in Google account cannot read that site or property, or the id is wrong. | Search Console: add the account under Settings > Users and permissions (Restricted is enough). GA4: give it at least Viewer under Admin > Property access management. Or record the right id. Then `mb connect test google`. | yes (`invalid`) |
| `*_api_disabled` | HTTP 403 because the Google Search Console API or the Google Analytics Data API is not enabled in the Cloud project that owns the OAuth client. | Enable it under APIs & Services > Library, wait a few minutes, test again. | yes (`invalid`) |
| `*_auth_rejected` | HTTP 401 on a freshly minted token. | A person runs `mb connect google --oauth --reauth`. | yes (`invalid`) |
| `*_request_rejected` | Another 4xx. | Check the recorded ids with `mb connect status google`. | yes (`invalid`) |
| `*_quota_exhausted`, `*_server_error`, `*_unreachable`, `*_response_malformed`, `*_unexpected_redirect` | 429 or a quota reason, 5xx, no answer, an unreadable answer, or a redirect (never followed: the access token is never sent to a second URL). Nothing about the sign-in is known to be wrong. | Test again later. | no |

When the token cannot be minted, the token rules in the table above apply:
`reauth_required` is recorded as before; `oauth_client_rejected`,
`oauth_client_unauthorized`, `oauth_scope_rejected`, `oauth_grant_malformed`
and `oauth_grant_missing` (facts about the client or the grant) are recorded
as `invalid`; the rest, `token_request_rejected` included, are not recorded.

An outcome that is not recorded leaves `mb connect status google` exactly as
it was (it may still read `ready` from an earlier check), but the test itself
exits 1 and prints `recorded: no`. `mb connect status google` and
`mb connect doctor` never call Google; they show the last recorded check.
On a sign-in connection, `mb connect status google` adds one line per
product, such as `search_console: granted, last check: ok`,
`ga4: granted, last check: invalid (ga4_no_access)` or `ga4: not granted`.
After a read records `reauth_required`, a granted product reads
`granted, last check: not checked since the sign-in expired`.
`--json` adds `oauth.grants` (the granted products) and
`validation.products` (each product's last recorded `state` and `rule`).

`.mb/connect.yaml` is ignored by git in a business repo. If an older or
hand-made repo tracks it, nothing writes to it on its own: a read that sees
`reauth_required` still exits 1 with the `--reauth` repair but does not
record it, and `mb connect test <provider>` (any provider) reports
`recorded: no (.mb/connect.yaml is tracked by git ...)` with
`not_recorded_reason: connect_yaml_tracked` in `--json`; a failed check still
exits 1. When git cannot answer (it is missing, times out, or refuses the
repo, for example over `safe.directory` ownership) and the repo is inside a
git checkout, the file is treated as tracked. `GIT_DIR`, `GIT_WORK_TREE` and
`GIT_INDEX_FILE` from the environment are ignored for this check. Commands a
person runs to change the connection (`mb connect google --oauth`,
`--metadata`, `mb connect rotate`) still write it, and their own check is
recorded with it.
In such a repo, the Agent Access Dossier row in `mb doctor` shows what the
check found, followed by `(not recorded: .mb/connect.yaml is tracked by git)`,
not the stale recorded status. When the check was not recorded because the
user-scope connect file is read-only, the row says
`(not recorded: the user-scope connect file is read-only)` instead.

The probe is conditional. A sign-in (OAuth) connection has one, so
`stored, unverified` or `unvalidated` on it exits 1 and points at
`mb connect test google`. A `google` connection made with a plain access
token (`--token-stdin`) still has no probe: `mb connect test google` records
`stored, unverified`, exits 0, and doctor lists it under the probe gap, as
before.

If Google refuses the sign-in's one-time code exchange, nothing is stored
and the rule names the class, never Google's text: `oauth_client_rejected`
(`invalid_client`: the client was deleted or the file is out of date),
`oauth_client_unauthorized` (`unauthorized_client`: not a Desktop app
client), `oauth_scope_rejected` (`invalid_scope`),
`authorization_code_rejected` (`invalid_grant`: the code expired, was used,
came from another attempt, or did not match the sign-in request; sign in
again), and `token_request_failed` for
anything else.

If you untick one product on the consent screen, the sign-in is stored with
the product you allowed, exits 1, and names the missing one; sign in again
with `--reauth` and tick both boxes. If you decline, the browser wait times
out, Google returns no refresh token, or the response does not match this
sign-in, nothing is stored.

### Renew only when asked

Google keeps at most 100 refresh tokens per Google account per OAuth client
and silently revokes the oldest beyond that. With one client shared by many
business repos, every extra sign-in can end another repo's access without
warning. So:

- sign in once per repo; never script retries;
- renew with `mb connect google --oauth --reauth` only when
  `mb connect status google`, `token` or `exec` says `reauth_required` (or
  names `--reauth` in its repair). `--reauth` reuses the client and metadata
  already recorded; pass `--client-file` again only if it asks.

Running `--oauth` again on a repo that already has a sign-in refuses with
`oauth_use_reauth`.

### Which Google account

One personal Google login may serve every business you run. For client or
agency work, a dedicated Google user with view-only access to just that
client's properties is recommended.

The scopes are account-wide: Google lets the token read every Search Console
property and GA4 property that account can see, not only this business's.
`mb` limits its own reads to the site and property recorded in this repo, but
anything run through `mb connect exec google -- <command>` is not bound by
that rule. A view-only user is how you narrow what the token itself can read.

### Without a local browser (SSH, headless)

- `--paste`, in a real terminal (not through an agent and not with `!` in a
  chat): `mb connect google --oauth --client-file <path> --paste`. Open the
  printed URL in a browser on any machine and allow access. That browser
  then fails to load a `http://127.0.0.1:...` page; copy that page's whole
  address and paste it at the hidden prompt. Never paste that address into
  a chat or an issue: it carries a one-time code. Paste mode refuses when
  stdin is not a terminal.
- Or keep the browser redirect and tunnel the port:
  `mb connect google --oauth --client-file <path> --no-browser --port 8085`
  on the server, `ssh -L 8085:127.0.0.1:8085 <server>` from your laptop, then
  open the printed URL on the laptop.

### What it will not do

- Request indexing in Search Console has no API. It stays in the browser.
- Nothing is written to Google: no sitemap submit, no property or user
  changes.

### Refusals

Each exits 2 with fixed text and changes nothing:

| Rule | When |
| --- | --- |
| `oauth_replaces_access_token` | The repo stores a plain Google access token. `--oauth` would replace it and its Drive, Docs and Sheets use would stop; add `--replace-access-token` to proceed. |
| `oauth_use_reauth` | The repo already has a Google sign-in; renew it with `--reauth` only when asked. |
| `oauth_reauth_without_grant` | `--reauth` with no sign-in to renew. |
| `oauth_connection_exists` | `mb connect google --token-stdin` (or `--token`, `--from-env`) on a sign-in connection; it would drop the grant. |
| `rotate_oauth_use_reauth` | `mb connect rotate google` on a sign-in connection; there is no source to re-read. It names the `--reauth` that works (with `--client-file` when the stored sign-in is gone or can't be read). |
| `oauth_client_required` | No `--client-file` or `--client-stdin`. |
| `oauth_client_malformed`, `oauth_client_not_desktop`, `oauth_client_unreadable` | The client file is not a Desktop app client JSON, or cannot be read. |
| `search_console_site_format`, `ga4_property_id_format`, `oauth_metadata_reserved` | A metadata value is not in the shape above, or sets `oauth_grants`. |
| `paste_needs_tty` | `--paste` without a terminal on stdin. |
| `oauth_scope_kept` | `--scope` names a scope other than the one the existing Google connection is recorded in; a renewal keeps the recorded scope. An entry with no stored credential yet (only `--metadata`) is a first sign-in, and `--scope` is honoured there; signing it in with `--scope repo` removes the leftover user-scope entry, whose metadata the repo entry now holds. |
| `oauth_backend_kept` | `MB_CONNECT_SECRET_BACKEND` names a store other than the one the existing Google connection uses; a renewal writes to the recorded store. A connection recorded under the older `keyring` name accepts `auto` or `keyring` when they resolve to the same native store. |
| `oauth_option_without_oauth` | `--timeout`, `--client-file`, `--reauth` or another sign-in option without `--oauth`. `--timeout` is refused even at its default (`--timeout 300`); `--port 0`, the default, is not. |

A credential-store failure part way through says exactly what is stored. If
the grant write fails, nothing changed. If a later write fails on a first
sign-in, the repo does not record the new items and the connection is not
set up; sign in again once the store is healthy. If it fails during
`--reauth`, the new grant has already replaced the old one; the message says
so and points at `mb connect test google`. With `--scope user`, if the
user-scope entry was written but `.mb/connect.yaml` was not, the sign-in is
already usable: `mb connect hydrate --repo .` records it in the repo without
a new sign-in (`--reauth` also works; a second plain `--oauth` refuses).
Ctrl-C, or an unexpected error, after the first write gives the same
account of what is stored instead of "Nothing was stored". Ctrl-C while the
grant itself is being written says the grant "may have been stored": on a
first sign-in the repo does not record it, so sign in again; on `--reauth`
it may have replaced the old grant, so run `mb connect test google`.

## User Scope

Writing the user-scope file keeps its other top-level keys as they were. It
does not keep YAML comments: a rewrite drops them. A read-only file, including
one protected by ownership or an access-control list, is never made writable
or replaced. Every command that would write it
(`mb connect <provider> --scope user`, `rotate`, and `mb connect google --oauth
--scope user`) checks first, before it stores any credential, and refuses with
rule `user_scope_read_only` (exit 2, `--json` included). The message names the
file and says to make it writable or move it and rerun; nothing is stored or
changed. If writing is denied after a token was stored by connect or rotate,
Main Branch restores the previous credential (or removes the newly created
one) before returning that refusal. If restoration also fails, it exits 1 with
`metadata_write_failed`: the message says the credential was stored or replaced
but not recorded, names the file, and gives a retry command that keeps user
scope and the selected repo. Make the file writable first, then supply the
credential again with that command.

Any other failure to write that file after a token was stored (a full disk,
an I/O error, a failed rename, or a file that no longer parses) gets the same
restore. Connect and rotate then exit 1 with `metadata_write_failed`: the
message names the file and what went wrong, says the previous credential was
restored (or the new one removed), and that the repo metadata is unchanged. If
the restore also fails, the message is the stored-but-not-recorded one above
with that cause and its fix in place of the read-only file. No backend error
text or credential value is shown.
The replacement file has mode `0600` before it becomes visible. A blocked
parent folder is named as the cause and the repair points to that folder.
Recovery commands show repos under your home folder with a `~/` path.

`mb connect test` only reads that file to run its check: the check still
runs and the repo metadata is still recorded, and the result says
`recorded: false` with `not_recorded_reason: user_scope_read_only` in `--json`.
Human output says `recorded: no` and names the read-only file. When the file
cannot be written for another reason (a full disk, an I/O error), the check
still runs, the exit code is the one a successful check would give, and the file
is left as it was. `--json` then says `recorded: false` with
`not_recorded_reason: user_scope_write_failed` and a sanitized
`not_recorded_detail` sentence naming the file and the cause; the agent-access
check in `mb doctor repair --plan` shows "not recorded: the user-scope connect
file could not be written", or, when the file cannot be read or parsed,
"not recorded: the user-scope connect file is unreadable or invalid" (for a
non-Google provider; a Google row keeps the first wording, and a file that is
already bad when doctor starts is reported as `unreadable_file`, below, instead). The same
applies to a Google read that cannot record an expired sign-in in the
user-scope file, whether it is full, read-only, unreadable or invalid: the repo
metadata is put back as it was, and the read result carries a
`not_recorded_note`. `mb connect token google` and
`mb connect exec google` print that note on stderr as `recorded: no (...)`,
never in the token or the command's own output, and only when it applies. If
putting `.mb/connect.yaml` back also fails, the note says so, and the file may
still show the check. During `mb connect google --oauth --scope user`, any
failure to write the file, including a file that turns read-only after the
check, restores the previous sign-in (or removes the new one) and exits 1 with
`metadata_write_failed`, like the other providers. If a restore fails, the
message says which part stayed changed (the Google grant, the access token, or
both; for other providers, that provider's credential). A user-scope file that
cannot be read or parsed (including one that is not valid UTF-8) does the same,
and the message says to fix or move it. `mb connect test` with such a file
puts `.mb/connect.yaml` back as it was and says the check was not recorded;
the exit code follows the check itself, not the stale stored status, by the
same rule as when `.mb/connect.yaml` is tracked by git: a failed check exits 1.
In `--json` that case carries `needs_action` (the check's own result, which the
exit code follows) and `exit_follows_check: true`, which says so. A passing
check still exits 0 there while the file needs fixing: read `recorded` and
`not_recorded_detail`, not the exit code alone.
`mb doctor`, `mb doctor repair --plan` and their `--json` forms name that file
(`~/...`) in one `unreadable_file` error and exit 1, rather than failing, when it
is invalid YAML, is not a YAML mapping, is not valid UTF-8, cannot be opened or
is a folder.
Fresh sign-in retries keep `--scope user`, the selected repo and any
access-token replacement flag; use the same OAuth client and metadata again.
When the folder is what refuses a write (permission denied on the folder, not on
the file), the message names that folder, not a read-only file.

Use user scope when several worktrees for the same business repo should read
the same credential metadata from local Main Branch state:

```bash
mb connect mercury --custom --scope user --token-stdin
```

A fresh worktree can see that user-scoped metadata exists and can hydrate the
repo-local `.mb/connect.yaml` copy:

```bash
mb connect hydrate --repo .
```

Secret material remains outside git in both repo and user scope.

User-scope lookup is indexed by `repo_id`. Worktrees and scheduled jobs for the
same business can reuse the entry; another business with the same provider id
cannot.

## External 1Password option

Main Branch does not yet implement a 1Password credential-store adapter. An
operator may use an existing 1Password CLI or service-account workflow outside
`mb` and pipe a selected field into `mb connect ... --token-stdin`, keeping the
value in memory and off argv. Recording the reference with `--source` lets
`mb connect rotate` repeat that read later. Vault choice, service-account creation, token
storage, desktop integration approval, and reapproval remain operator-owned
bootstrap. An unlocked desktop integration is not evidence that unattended
access will remain available.
