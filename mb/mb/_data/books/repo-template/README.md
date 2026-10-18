<!-- MB-FIXTURE: invented books repo; no real transactions or evidence. -->
# Sample Books Repo

This is a synthetic hledger example. All names and amounts are invented.
Keep real records in the private storage mode chosen in `docs/books.md`.

`2026.journal` is the live entrypoint. `2026-accounts.journal` declares its
accounts and commodity. The generated source lane is under `imports/`; its
classification example is under `rules/`. `checks/2026-close.journal` pins the
close candidate. The manifest contains a fake archive pointer and fake hash,
never evidence bytes.

Run `bin/books doctor` from this directory. It checks both entrypoints with
hledger. See `docs/books-workflow.md` in Main Branch for the full operator loop.
