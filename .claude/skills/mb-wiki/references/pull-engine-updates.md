# Main Branch Update Check

Standard command for checking or applying Main Branch updates at the start of a
skill invocation. CWD is the business folder. **Do not silently swallow
failures.** Users on stale code get broken features.

`mb update` owns the install-mode mechanics. It detects pipx vs source
checkouts, runs the correct update command, and refreshes skill links for the
business folder.

```bash
mb update --repo . --json 2>&1
```

## Handle the Result

| Result | What to say |
|--------|-------------|
| `manual_update_command` is set (whatever `"ok"` says) | **Check this row first.** This install mode is not one the CLI upgrades for you, so never say "Updated Main Branch" here. Then branch on the version. **`old_version != new_version`:** Main Branch did **not** upgrade itself — say so and read `manual_update_command` out verbatim as the command for the user to run themselves. **`old_version == new_version`:** the install is current and needs no upgrade — say nothing, this table's quiet default, and do not offer the command as an action item. Skill links were refreshed either way. If `"ok"` is also false that refresh failed: show the warning below and keep `manual_update_command` in front of the user rather than the pipx advice. |
| JSON `"ok": true`, old_version == new_version | Say nothing |
| JSON `"ok": true`, old_version != new_version | "Updated Main Branch and refreshed skill links." |
| Invalid JSON or missing engine root | "Couldn't find Main Branch. Run `mb skill link --repo .`, then restart Claude." |
| JSON `"ok": false` or command failure | Show the warning below |

## If Update Fails - Show This Warning

> "I wasn't able to update Main Branch. This means you may be running on an old version and missing new features.
>
> Common fixes:
> 1. Run `mb update --check --repo .` to see which install path Main Branch detects
> 2. Run `mb update --repo .` again after fixing the reported error
> 3. **Network issue?** Check your internet connection
>
> You can continue, but some features may not work as expected."

**Do not skip this warning.** A user running stale Main Branch is the #1 cause of "why doesn't X work" support questions.
