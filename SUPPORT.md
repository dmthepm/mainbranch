# Support

Use the narrowest support path that matches the problem.

## Setup or usage help

Start local:

```bash
mb doctor
```

If Claude Code does not see `/mb-start`, run this from your business repo:

```bash
mb skill link --repo .
```

Then restart Claude Code and run:

```text
/mb-start
```

For step-by-step setup, read [docs/beginner-setup.md](docs/beginner-setup.md).
For platform support, read [docs/compatibility.md](docs/compatibility.md).
For the supported Claude Code slash-command behavior, read
[docs/claude-code-invocation-contract.md](docs/claude-code-invocation-contract.md).

## Where to ask

| Need | Best place |
|---|---|
| Bug in `mb` or bundled skills | [GitHub Issues](https://github.com/dmthepm/mainbranch/issues) |
| Setup help as a Main Branch member | [Skool community](https://skool.com/main) |
| Feature request or roadmap discussion | GitHub Issues |
| Security concern | Private report; see [SECURITY.md](SECURITY.md) |
| General Claude Code account problem | Anthropic support |

## Before opening an issue

Please include:

- Check [CHANGELOG.md](CHANGELOG.md) to see if your issue is fixed in a newer version.
- `mb --version`
- Operating system
- Install mode (`pipx` or clone)
- The command or slash skill you ran
- What happened
- What you expected
- Any relevant output from `mb doctor`

Do not include private business data, member information, API keys, Stripe IDs,
or unreleased client work in a public issue.

## What the paid community covers

The open-source repo gives you the `mb` CLI, bundled skills, schema, and public
docs.

The paid community is for operator-specific help: curated examples, calls,
classroom material, live bets, and support for applying the system to your own
business. The open-source engine remains usable without joining the community.
