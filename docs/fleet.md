# Fleet Status

`mb fleet` answers questions that span every repo an operator runs, across
every business, with one command:

- which framework and version each site is on, or which engine ref it pins;
- whether each repo's main branch is green in CI;
- what is live: which commit each site's production deploy came from, whether
  it was uploaded from a dirty working tree, and whether it is behind main;
- how many Dependabot alerts and Dependabot pull requests each repo has open.

It is read-only. Nothing in `mb fleet` writes to a repo, a provider or an
account. It needs Python 3.11 or newer, because it reads its hub list with
the standard library's TOML reader.

## Commands

```bash
mb fleet hubs list        # the hubs mb fleet reads
mb fleet refresh          # read GitHub and Cloudflare, cache one snapshot
mb fleet status           # print the cached snapshot (never reads the network)
mb fleet status --json    # the same, for scripts and dashboards
mb fleet checkin          # one read-only card per business
```

`refresh` exits `0` when every hub, repo and provider read worked and `1` when
something could not be read; the snapshot is cached either way, and `status`
shows the failures as warnings. A missing or invalid hub list exits `2`.
`status` exits `1` only when there is no snapshot yet. JSON output follows
[the JSON output contract](json-output-contract.md).

## The hub list

The hub list is a user-level file, never a repo file, because it names private
repos and local paths:

```text
$XDG_CONFIG_HOME/mainbranch/fleet.toml   (default ~/.config/mainbranch/fleet.toml)
```

One `[[hubs]]` table per hub:

```toml
[[hubs]]
name = "example-co"                    # optional label, defaults to the remote
remote = "github:example-co/example"   # required: the hub's GitHub owner/repo
checkout = "~/src/example-co/example"  # optional local checkout
cloudflare = "cloudflare"              # optional mb connect id for Cloudflare Pages
connect_checkout = "~/src/example"     # optional; defaults to checkout
```

- `checkout` is a speed-up. When it holds the registry, mb reads the registry
  there; otherwise it reads the registry from the hub's default branch on
  GitHub.
- `cloudflare` names the `mb connect` provider or custom id whose token can read
  Cloudflare Pages deployments for this hub's sites. Credentials are resolved
  from a local checkout, so a hub with `cloudflare` needs `checkout` or
  `connect_checkout`. The token is used in memory only; it is never cached,
  logged or printed. A read-only token (Pages read) is enough.

Edit this file by hand. `mb fleet hubs list` shows what mb understood.

## Where repos and sites come from

1. Each hub's registry, `core/operations/repo-topology.md`, lists its repos
   (see [child repo descriptors](child-repo-descriptors.md#relation-to-hub-topology)).
   Archived and superseded entries are skipped, and so is a `proposed` entry
   whose repo does not exist yet.
2. Each repo's `.mainbranch/repo.json` is read from GitHub. A repo with a
   [`sites` list](child-repo-descriptors.md#sites-several-sites-in-one-repo)
   gets one row per site; any other repo gets one row.
3. Framework and engine pin come from `package.json`: the site's `dir` when it
   has its own `package.json`, else the repo root. The root is used only after
   GitHub confirms the site's file is absent (404); a denied, rate-limited or
   failed read, or a file that is not a JSON object, leaves the row's
   `framework` and `engine_pin` `unavailable` or `malformed` and is a refresh
   error. The same holds for `.mainbranch/repo.json`: when it cannot be read
   the repo gets one row with `sites_state` saying why, not guessed sites. An engine pin is a
   dependency installed from a git ref or a local path (`github:owner/repo#v1.2.3`,
   `git+https://…#<sha>`, `file:../engine`). The newest semver tag of the engine
   repo is read so a pin can be flagged as behind it.
4. Main's SHA, its commit time and the check runs on it come from the GitHub
   API. Every page of check runs is read; when any page fails, `ci.state` is
   `unknown` and the refresh reports an error.
5. For a hub with a Cloudflare connection, the current production deployment of
   every Pages project is read once. A site uses the project named in its
   `deploy.project`. A repo with no `sites` list falls back to a project with
   the same name as the repo, then to a project serving the registry `domain`;
   `deploy.project_source` says which rule matched (`declared`,
   `project_name_match`, `domain_match`).
6. Dependabot: open alerts counted by severity, and open pull requests opened
   by Dependabot (count and the oldest one's age in days). Both are per repo,
   not per site. The alerts API needs a token allowed to read security alerts;
   when it answers 403 or 404 the repo shows `unavailable` with the HTTP
   status, and the refresh carries on.

About eight GitHub calls per repo, so a few dozen repos fit easily in GitHub's
hourly limit.

## What a row says

| Field | Meaning |
| --- | --- |
| `hub`, `repo`, `site`, `role` | Where the row comes from. `site` is empty for a repo without a `sites` list. |
| `sites_state` | `ok`, or `unavailable` / `malformed` when the descriptor could not be read and the repo's sites are unknown. |
| `package` | Which `package.json` gave the facts (`path`), its read `state` (`ok`, `absent`, `unavailable`, `malformed`) and `http_status`. |
| `framework` | `name`, the `spec` from package.json, its `version` number and the read `state`. |
| `engine_pin` | `state` (`ok`, or `unavailable` / `malformed` with `http_status`), `package`, `kind` (`tag`, `commit`, `branch`, `path`, `none`), `ref`, `latest_tag`, `on_latest`. |
| `ci` | `state` (`success`, `failure`, `pending`, `none`, `unknown`), `total` check runs, names of `failing` ones. |
| `main_sha`, `days_since_commit` | Head of the default branch and its age when `status` ran. |
| `deploy` | `state`, `project`, `deployed_sha`, `dirty`, `matches_main`, `compare` (GitHub's compare of deployed against main: `ahead` means main has moved on) and `behind_by` (commits on main not in the deploy). |
| `flags` | `facts_unavailable`, `ci_failing`, `deploy_dirty`, `deploy_behind_main`, `deploy_differs_from_main`, `engine_unpinned`, `engine_behind_latest`. |

`deploy.state` is `ok` when a production deployment was read. Other values say
why not: `undeclared` (no project known for this row), `no_connection` (the hub
has no Cloudflare connection), `provider_error` (the Pages read failed: an
HTTP error, an envelope without `success: true`, or a malformed body; no
partial project list is kept), `project_not_found`,
`no_production_deployment`, `no_commit_hash`, `unsupported_provider`, and
`descriptor_unavailable` / `descriptor_malformed` (the repo's sites are unknown).

## The cache

Snapshots are stored in SQLite under the user state directory:

```text
$XDG_STATE_HOME/mainbranch/fleet.db   (default ~/.local/state/mainbranch/fleet.db)
```

The last ten snapshots are kept. `status` reads the newest and reports its age
(`age_seconds`); it suggests `mb fleet refresh` when the snapshot is more than a
day old or had read failures. Only the facts above are stored. Deployment
objects also carry build environment variables, and those are dropped before
anything is written.

## Check-in: one card per business

```bash
mb fleet checkin [--json] [--hub NAME] [--timeout SECONDS]
```

`checkin` answers "which business needs me today?" for every hub in the hub
list. It writes nothing and stores nothing: no history, no trends, no cache of
its own.

**What it reads.** For each hub with a `checkout` it runs
`mb status <checkout> --json --peek` in a child process of the same Python
(never the `mb` on `PATH`), so the last-status-seen marker is not touched and
your own "since last check" stays yours. Each child is bounded by `--timeout`
(default 60 seconds) and killed with its process group when it runs out, so one
slow or broken hub never blocks the others. It also reads the cached fleet
snapshot, opened read-only. Because `status` makes its own unattended reads, a
card may reflect GitHub state that `status` fetched.

**The card.** `--json` follows the v1 envelope with `schema: "mb.fleet.checkin"`,
`schema_version: 1`, `generated_at`, `hub_list`, `fleet_snapshot`, `overview`
(`needs_you`, `on_track`, `cannot_see`, `text`) and `cards[]`. Each card has
`hub`, `display_name`, `remote`, `checkout` (as `~/...`), `checkout_state`
(`ok`, `missing`, `not_on_this_machine`, `not_a_business_repo`), `state`
(`ok`, `unavailable`, `remote_only`), `verdict`, `freshness`, `text` and seven
sections: `loop`, `bets`, `exposure`, `checkpoint`, `github`, `connections`,
`sites`. Every section has `state` (`ok`, `attention`, `not_checked`,
`unavailable`, `not_applicable`), `as_of`, `source` and a short `text`. Bets
pass through `stage` and `commitment` when status provides them. Exposure shows
counts and cap state only, never amounts. `safe_to_share` is `false`. Without
`--json` you get the overview line and one short card per business, ready to
paste into a message.

`verdict` is `needs_you` when the loop is `needs_attention` or `not_ready`,
`on_track` when it is `ready`, and `cannot_see` when the business could not be
read. A remote-only card is judged from its site flags in the snapshot.

A local checkout whose head differs from the cached `main_sha` (on the default
branch) is marked `local_matches_remote: false`: it may miss work saved
elsewhere. `checkin` never fetches. Bet counts are capped at five by `status`.

**Exit codes.** `0`: every business produced a card it could read. `1`: cards
were produced but a business could not be read (missing checkout, not a
business repo, or status failed or timed out); stdout is still complete and
should still be delivered. `2`: the hub list is missing or invalid, `--hub`
names no hub, or `--timeout` is below 1; no cards. A business that needs you is
not a failure.

**What it never does.** Fetch, write any file, prompt, repair a keychain, call
a paid API or a model, send a message, or schedule itself. Delivery and timing
belong to the caller (a scheduler or a hook), which should deliver on `0` or
`1` and report on `2`.

## Not in this slice

- `mb fleet run` (recipes such as an engine pin bump or a framework upgrade,
  one pull request per repo).
- Deploy providers other than Cloudflare Pages.
- Combined commit statuses (only GitHub check runs are read).
