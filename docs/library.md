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
sighting and says which.

## What is stored where

| What | Where | In git |
|---|---|---|
| Source paths, timezone | `.mb/private/library/config.yaml` | no |
| Index of sightings | `.mb/private/library/index.db` | no |
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
an approved deal removes its approval. A deal with no end date must say
`--perpetual`. A revoked deal stays revoked for as long as its record file
keeps saying so.

## Originals are read, never changed

- `source add` and every `scan` refuse a folder this user can write. There is no
  override. Mount the media read-only, or give the business user a read-only view.
- Files are opened read-only without following symlinks. A file is skipped, and
  listed with its reason, if it is writable, has more than one hard link, is a
  symlink or not a regular file, changed while being read, was modified in the
  last minute, or is a cloud placeholder.
- The library's own files are written with no-follow opens, refuse symlink or
  multiply linked destinations, and must be owned by the running user and not
  writable by group or others. Records, index and config inside a source are
  refused.

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
- Reading can update access times; cloud-backed mounts can download on read.
  `scan --verify` compares content now with the index; it shows what the files
  contain, not that nothing wrote to them. Prevention is the read-only mount.
- Not in this version: bytes or links to files, references and clusters,
  image size or format, timers, Drive or bucket sources.
