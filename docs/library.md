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
    --music original --said-by "Rowan Vale, email 2026-10-02" --subject none-shown
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
- the deal states whether the person shown agreed (see below); `unknown` is not
  cleared, and the reason `check` prints is `subject-unknown`;
- for licensed paid ads, a platform code for that platform that does not expire
  inside the window (record the platform and expiry, never the code itself).

The **subject** is a person shown in the media other than whoever said yes: a
client, customer or guest. `deal propose` needs `--subject`:

- `none-shown`: no one is shown, so nothing needs agreeing;
- `agreed`: the subject agreed, with `--subject-proof "<where the proof sits>"`,
  for example `signed release, Releases/2026-10`. Say where it is, never who
  they are;
- `unknown`: not known yet. This never clears.

The deal's uses, platforms and window are the scope the subject agreed to, so if
a client agreed to organic posts only, propose a deal limited to organic posts.
The creator's okay never covers the person shown: `said_by` is not read for the
subject, so a photographer saying yes does not clear a photo of their client.
The subject and the proof are terms of the deal; editing them after approval
removes the approval. A deal approved before this field existed keeps its
approval and shows as not cleared with `subject-unknown` until a new deal states
the subject. While the subject is `unknown` the keys are not written to the
record. An engine older than this one drops the subject keys when it rewrites a
record, so upgrade every install that touches a business's records together.

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
- Every line the `mb library` commands print themselves (results, listings, the
  approval prompt and their own errors) goes through one function that writes
  out control characters and line breaks (`\x0a`) in the whole line, so no name,
  creator, id, date, label or error taken from a record can fake a line of
  output. Escapes are fixed width (`\x0a`; the line separator U+2028 as a
  backslash, `u` and 2028; `\U000e0001`), so two different names never print
  alike. Usage errors for a mistyped option or an
  extra argument, and `--help`, are written by the command framework (Typer), not
  by this function; they can echo back what was typed on the command line.
  Source names,
  asset ids, kinds, deal ids and approval times are also checked where they are
  read, and a record or index row that fails is refused.
- Records and config are read with exact types (a quoted `"false"` is not
  `false`), up to 1 MiB and 12 levels deep; anything else is refused by name.
  Only a missing or empty (null) field takes its default; `tags: false`,
  `creator: 0`, `deals: false` or `sources: false` are refused, not read as empty.
  The same goes for the whole file: an empty or null file reads as an empty
  mapping, but a file that is only `false`, `0`, `[]` or `''` is refused as not
  a mapping. A field the library does not know, in a record, in a deal or in the
  config, is refused by name, and the file is left as it was, because every
  command that writes a record writes back only the fields it knows and would
  delete the rest. Put business-only facts in `tags`; they are searchable and
  never change the answer. A value the YAML reader cannot build (an impossible date, a number
  of thousands of digits) is refused by name, and a `records_dir` with a NUL
  character is refused.
  A file over 1 MiB is refused without reading past the limit. YAML aliases
  (`*name`) and merge keys (`<<:`) are refused before anything is built, because
  a few hundred bytes of them can expand past the memory the process has. Depth
  (12 levels) and size (50,000 values and keys) are counted as the parser
  produces them, and the parse stops at the first one past the limit, before
  anything is built. These bounds cap what is built and how far a deep or long
  document is parsed. They do not cap the time to scan a file up to 1 MiB, and
  they give no named refusal if the process is already out of memory: that
  failure is not caught. A
  record or config is checked against these same limits before it is saved; one
  that would be refused on reading is not written, and the earlier version stays.

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
