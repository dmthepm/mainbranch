# Minisite Setup

Load this for step 5 of the minisite flow: infrastructure provisioning.

This step does not change the brief. It creates or repairs the empty deploy target and links the site repo back to the business repo.

## 5a. Name And Project Repo

Ask the operator:

- Site name, such as `thelastbill`. This becomes the Cloudflare Pages project name.
- Project repo location. Default to a sibling repo the operator can inspect, such as `~/Documents/GitHub/<name>`.
- Apex domain. If they do not have one, route to [`naming-heuristic.md`](naming-heuristic.md).

Use an empty repo. Do not merge a template into the minisite shape.

## 5b. Prerequisites

Hard-gate Cloudflare-dependent setup before tool dispatch:

```bash
mb connect doctor --json
```

If `provider:cloudflare` is not `ready`, stop and offer three choices:

- **connect now (in your own terminal; the token prompt is hidden):** `mb connect cloudflare --metadata token_type=account --metadata account_id=... && mb connect test cloudflare`. Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check.
- **continue read-only:** domain availability, naming, brief, and research only; no buy, DNS, Pages, custom-domain, or deploy calls.
- **skip for now:** record the Cloudflare blocker in the push/site notes and stage a follow-up.

Prefer Cloudflare account-scoped tokens for multi-business operators. User API
tokens remain supported as a fallback by omitting `token_type=account`.

After `mb connect` reports Cloudflare ready, `verify_live.py` can be used as a
deeper manual smoke for Cloudflare scopes, zone lookup, and domain-check CLI.

## 5c. Domain: Existing Or New

Ask:

- Already own the domain? Skip to DNS ensure with the domain name.
- Need to buy? Run an availability check first:

```bash
python3 .claude/skills/mb-site/scripts/domain.py check <name> --tlds .com,.co,.io
```

Main Branch cannot buy domains through `domain.py` yet. If the operator needs a
new domain, route them to https://dash.cloudflare.com/registrar after the
availability check, then resume once they confirm they own the full domain.

## 5d. DNS Ensure

Once the domain is owned:

```bash
python3 .claude/skills/mb-site/scripts/dns.py ensure <domain> --registrar cloudflare --skip-propagation-poll
```

## 5e. GitHub Repo And Placeholder Push

Ask the operator one visibility question before creating the repo:

> "Should the source files and full change history be public? The deployed
> Cloudflare site is public either way. Most people choose private here so
> drafts, copy iterations, and revision history stay out of public view.
> Choose public only when the source itself is meant to be public — an
> open-source tool, template, demo, or build-in-public project."

Default to **private**. Only pass `--public` when the operator explicitly
answers that the source is intentionally public. The engine docs ship the
full rubric (`repo-visibility-rubric`) — refer to it if the operator wants
more detail.

```bash
# Default (private source, public deployed site):
gh repo create <owner>/<name> --private --add-readme

# Only when the operator explicitly chose public source:
gh repo create <owner>/<name> --public --add-readme

git clone https://github.com/<owner>/<name>.git ~/Documents/GitHub/<name>
cd ~/Documents/GitHub/<name>
```

Do not pass `--public` because the deployed site will be public. Visibility
is about source/history; deploy is about Cloudflare.

Create the placeholder with normal file-edit tooling, then:

```bash
git add -A
git commit -m "[add] placeholder"
git push
```

## 5f. Cloudflare Pages Project

```bash
python3 .claude/skills/mb-site/scripts/pages.py create-project <name> --repo-owner <owner> --repo-name <repo> --branch main
```

If you hit `github_app_not_installed`, the envelope's `suggestion` field walks through the dashboard handshake step. See [`cloudflare-pages-link.md`](cloudflare-pages-link.md).

## 5g. Custom Domain Attach

```bash
python3 .claude/skills/mb-site/scripts/pages.py set-domain <name> <domain> --timeout-seconds 300
```

Expect roughly 3-4 minutes. This path was live-tested end-to-end in PR #97.

## 5h. Link Records

Prefer repo-local links over global config.

Write `<site_repo>/.mainbranch/repo.json`:

```json
{
  "schema": "mb.child_repo.v0",
  "role": "site",
  "display_name": "Flagship site",
  "github_owner": "example-co",
  "repo_name": "flagship-site",
  "safe_purpose": "Public paid-traffic site for the flagship offer.",
  "parent": {
    "display_name": "Example Business",
    "github_owner": "example-co",
    "repo_name": "example",
    "remote": "github:example-co/example",
    "local_checkout": "../example"
  },
  "linked": {
    "offers": ["core/offers/flagship/offer.md"],
    "pushes": ["pushes/2026-05-06-paid-minisite/push.md"]
  },
  "return_to_hub_command": "cd ../example && claude",
  "safe_to_share": true
}
```

Use the real GitHub owner/repo, display names, linked offer path, linked push
path, and optional relative `parent.local_checkout` for the operator's sibling
checkout layout. Do not commit absolute local paths, secrets, raw provider
caches, or permission claims.

Existing site repos may still use `.mainbranch/source.json` with
`business_repo`, `offer_path`, and `campaign_path`; treat that as compatibility.
The `campaign_path` key is a historical name and should point at the current
push record.

The business repo should keep the reverse site record in the relevant `pushes/`
record or offer note: site repo path or URL, domain, Cloudflare project,
environment, measurement state, launch status, and the next manual approval
step.

After writing or updating that business-repo record, checkpoint it before
continuing:

```bash
cd <business_repo>
mb checkpoint --plan --json
mb checkpoint --validate "[connected] site repo -- <slug>" --json
mb checkpoint --message "[connected] site repo -- <slug>" --yes
```

Treat `~/.mainbranch/sites.json` as legacy fallback only when no repo-local link exists. If needed, write or extend:

```json
{
  "name": "<name>",
  "site_repo": "/absolute/path/to/repo",
  "business_repo": "/absolute/path/to/business-repo",
  "shape": "minisite",
  "hosting": "cloudflare",
  "domain": "<full apex>"
}
```

After setup, move to [`minisite-conversion.md`](minisite-conversion.md).
