<!-- MB-FIXTURE: synthetic books repo agent instructions. -->
# Books Repo Instructions

This marked example contains invented records only. For a real private books
repo, read its current protocol before work.

- Run `git pull --rebase` before work and again before push.
- Allow one writer at a time in this books repo.
- Run the declared `bin/books doctor` before every push. Push only after it passes.
- Archive evidence outside git. Record each evidence pointer and SHA-256 in
  `manifests/`. Never commit statements or provider exports.
- Propose rules changes as a diff and obtain operator approval before applying.
- Keep close state in `docs/blockers.md` and `reports/doctor-receipt.json`.
- Keep journal, payee, account, amount, and tax details inside this restricted repo.
