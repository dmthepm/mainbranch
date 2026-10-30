# OpenSEO Upgrades, Backups, and Rollback

Every command here is NOT VERIFIED at the current pin. No restore drill has
passed, so never tell an owner a copy can be fully recovered.

## What a backup covers

A D1 export is not a full backup. It leaves out R2 files, KV, in-app chat history
in Durable Objects, and the Alchemy state store with its secrets. Upstream has no
complete backup and restore runbook.

The real protection is that durable findings live in the business repo. Keep
`.env.selfhost` values in the owner's password manager, including
`BETTER_AUTH_SECRET` if Google is connected.

## Choose a release

Upgrade only to a reviewed release SHA, never a floating `git pull`. The review
covers:

- release notes between the current pin and the target;
- changes under `deploy/`, `AUTH_MODE` defaults, and `.env.selfhost.example`;
- new Cloudflare permissions, new required values, and paid-plan needs;
- whether upstream issue 304 still applies.

Confirm the tag's SHA, record it in the setup record, and get the owner's yes.

## Before upgrading

Pause any approved schedules and writers. Then, in a separate private wrangler
config outside git, bind the **deployed** D1 ID. Never use the IDs in the root
`wrangler.jsonc`, because they belong to upstream.

```json
{
  "name": "open-seo-selfhost",
  "d1_databases": [{
    "binding": "DB",
    "database_name": "open-seo-db-selfhost",
    "database_id": "<DEPLOYED_D1_UUID>",
    "migrations_dir": "<CHECKOUT>/drizzle/sqlite"
  }]
}
```

Use the deploy setup from setup step 5, with `<PRIVATE_BACKUP>` mode 0700 and
outside git. The export holds private business data. Do not print it.

```bash
mb connect exec cloudflare-openseo --repo "<BUSINESS_REPO>" \
  --env CLOUDFLARE_API_TOKEN "${KEEP[@]}" \
  -- pnpm exec wrangler d1 export DB --remote --config "<PRIVATE_D1_CONFIG>" \
  --output "<PRIVATE_BACKUP>/pre-upgrade.sql" >"<PRIVATE_BACKUP>/export.log" 2>&1
mb connect exec cloudflare-openseo --repo "<BUSINESS_REPO>" \
  --env CLOUDFLARE_API_TOKEN "${KEEP[@]}" \
  -- pnpm exec wrangler d1 time-travel info DB --config "<PRIVATE_D1_CONFIG>" \
  --json >"<PRIVATE_BACKUP>/bookmark.json" 2>&1
```

**Expected:** both exit 0, and the export file is not empty.

## Upgrade

Do not recopy the example env file. It would turn on password accounts, and a
deploy in that mode removes the Access application.

```bash
cd "<CHECKOUT>"
git fetch --tags origin
git checkout --detach "<REVIEWED_SHA>"
test "$(git rev-parse HEAD)" = "<REVIEWED_SHA>"
pnpm install --frozen-lockfile
```

Check `AUTH_MODE` is not `password`. A copy with no `AUTH_MODE` line stays on
Access, because that is the default when the value is unset.

Run the deploy command from setup step 5. Alchemy applies pending migrations.

**Then redo setup steps 6 and 7.** Managed OAuth is cleared by every deploy, so
it is never skipped. Save the old and new pins and the results.

Moving a copy from a release before v0.1.13 with a Shopify signature: add
`CRAWLER_ACCESS_SECRET`, deploy, and save the signature again.

## Rollback

A deploy of the old SHA is safe only if its code supports the current database.
Alchemy does not undo SQL migrations, and rolling back one Worker version is not a
whole-copy rollback.

When the database changed, stop writers, then restore the bookmark and deploy the
old pin with its old config. Writes after the bookmark are lost. Time Travel keeps
7 days on Free and 30 on Paid.

```bash
mb connect exec cloudflare-openseo --repo "<BUSINESS_REPO>" \
  --env CLOUDFLARE_API_TOKEN "${KEEP[@]}" \
  -- pnpm exec wrangler d1 time-travel restore DB --bookmark "<BOOKMARK>" \
  --config "<PRIVATE_D1_CONFIG>" >"<PRIVATE_BACKUP>/restore.log" 2>&1
```

Get the owner's yes first. Redo setup steps 6 and 7 afterward.

**Never run `alchemy destroy`, as a rollback or a cleanup.** It deletes the copy's
data, and these resources have no retain policy.

## Leaving OpenSEO

The business keeps everything in its repo. To stop using a copy, remove its MCP
server and leave the DataForSEO balance unfunded. Deleting the Cloudflare
resources is the owner's choice, made in their own dashboard after they have saved
what they need.
