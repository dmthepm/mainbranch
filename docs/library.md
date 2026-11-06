# Media Library

`mb library` answers three questions about a business's own media: what
exists, where it is, and whether a given use is cleared. It reads folders you
point it at, keeps a rebuildable index, and keeps one small text record per
asset you have decided something about. It hands out no files, links or copies.

## Commands

Run these from the business folder. No verb takes another business folder.

```bash
mb library source add studio /srv/acme/media   # register a folder to read
mb library scan [--verify]                     # fingerprint files; list skipped and duplicates
mb library find "candle pour" [--kind photo] [--any]
mb library find --for paid-ad --platform meta --from 2026-12-01 --to 2026-12-15
mb library show <full asset id>                # every sighting, provenance, tags, deals
mb library check <full asset id> --use paid-ad --platform tiktok --from 2026-12-10 --to 2026-12-20
mb library deal propose <id> --use paid-ad --platform meta --from 2026-12-01 --to 2026-12-31 \
    --music original --said-by "Rowan Vale, email 2026-10-02"
mb library deal approve <deal id>              # a person at a terminal types the deal id
mb library deal revoke <deal id> --reason "creator withdrew"
```

`check` prints one line per sighting (a file at one place) and exits 1 unless
every sighting is cleared. `find --for` lists only assets with a cleared
sighting and says which, then prints how many more matched but are not
cleared; run `check` on those to see why. `--any` only widens the word match
(any word instead of all); it never shows uncleared assets.

## What is stored where

| What | Where | In git |
|---|---|---|
| Source paths, timezone | `.mb/private/library/config.yaml` | no |
| Index of sightings | `.mb/private/library/index.json` (and `index.lock`) | no |
| Provenance, tags, creator, deals | `library/records/<asset id>.yaml` | yes |

The asset id is the SHA-256 of the file's bytes, so the same photo in two
folders is one asset with two sightings. Delete the index and run `scan` again
to rebuild it. Records are plain YAML. Set `provenance` (`own`, `licensed`,
`third_party`, `unknown`) and any `tags` or `creator` by editing the record in
review, like any other file in the repo.

## When a use is cleared

A sighting is cleared only when all of these hold:

- the asset's provenance is `own` or `licensed` (the default, `unknown`, and
  `third_party` are never cleared, so a downloaded inspiration image found in a
  scanned folder is never cleared);
- an approved deal names that sighting, the use and the platform;
- the whole `--from`..`--to` window sits inside the deal, ends included, using
  the business timezone (default UTC; `timezone:` in the config);
- the deal states where the music came from (`unknown` is not cleared);
- for licensed paid ads, a platform code for that platform that does not expire
  inside the window (record the platform and expiry, never the code itself).

Tags and creator never change the answer. A proposed deal clears nothing. Editing
an approved deal's terms removes its approval, and so does changing the asset
or the `provenance` it was approved under; approve again after such a change.
A record's `asset` must match its file name. This catches accidents; a person
who can edit the file can still rewrite every field. A deal with no end date must say
`--perpetual`. A revoked deal stays revoked for as long as its record file
keeps saying so.

## Originals are read, never changed

- `source add` and every `scan` refuse a folder this user can write. There is no
  override. Mount the media read-only, or give the business user a read-only view.
- Files are opened read-only without following symlinks. A file is skipped, and
  listed with its reason, if it is writable, has more than one hard link, is a
  symlink or not a regular file, changed while being read, was modified in the
  last minute, or is a cloud placeholder. A folder more than 64 levels deep is
  skipped and listed as `too-deep`; the rest of the scan carries on.
- The library's own files are written with no-follow opens through the
  already-checked folder, refuse symlink or multiply linked destinations, and
  must be owned by the running user and not writable by group or others. The
  business folder and every folder on the way to the library's files must be
  owned by you and closed to group and others, or the library refuses. The
  index is one plain file replaced whole, with no database side files, so a
  folder swapped for a symlink mid-run cannot redirect a write. A scan holds a
  lock; a second scan is refused while it runs. Records, index and config inside
  a source are refused. The folders above the business folder are resolved once,
  when the command starts.
- Every line `mb library` prints goes through one function that writes out
  control characters and line breaks (`\x0a`) in the whole line, so no name,
  creator, id, date, label or error can fake a line of output. Source names,
  asset ids, kinds, deal ids and approval times are also checked where they are
  read, and a record or index row that fails is refused.
- Records and config are read with exact types (a quoted `"false"` is not
  `false`), up to 1 MiB and 12 levels deep; anything else is refused by name.

## Limits

- This is same-OS-user accident prevention. A process running as the same user
  can edit records, the index and the config. Separate businesses should run as
  separate OS users; the library relies on the operating system for that and
  adds only cheap checks.
- `deal approve` needs a terminal and the typed deal id. It is a speed bump and
  an audit record, not a human-approval gate: any process with a terminal and
  the same OS user can run it. Reviewing the git diff of the record is the check.
- Nothing here enforces rights at publication. Image generation and ad upload
  do not consult the library.
- The index is held in memory whole, for queries as well as scans. It has no size
  limit, so a very large library costs memory on every command.
- Reading can update access times; cloud-backed mounts can download on read.
  `scan --verify` compares content now with the index; it shows what the files
  contain, not that nothing wrote to them. Prevention is the read-only mount.
- Not in this version: bytes or links to files, references and clusters,
  image size or format, timers, Drive or bucket sources.
