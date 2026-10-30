# Security Policy

Main Branch is local-first software. It installs the `mb` CLI, writes files into
business repos you choose, and wires Claude Code to bundled skills. There is no
hosted Main Branch service in the open-source engine.

## Supported versions

| Version | Supported |
|---|---|
| 0.6.x | Yes |
| 0.5.x | Security fixes only when practical |
| 0.4.x | Security fixes only when practical |
| 0.3.x and older | No |

Security fixes ship in the next patch release when practical.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability.

Report privately by one of these paths:

- Use GitHub's private vulnerability reporting flow if it is available on this
  repository.
- Email `devon@noontide.co` with the subject `Main Branch security`.

We aim to acknowledge reports within 7 days and ship a fix within 30 days when practical.

Include:

- The affected version (`mb --version`)
- Operating system and install mode (`pipx` or clone)
- Reproduction steps
- Expected impact
- Any logs or screenshots that do not expose private business data

## Supply chain

Main Branch publishes to PyPI through a GitHub Actions workflow using trusted
publishing (OIDC) gated by a GitHub Environment with a required reviewer. The
durable policy — including the `id-token: write` boundary, dependency update
posture, release-time supply-chain checks, and post-compromise response — is
documented in [`docs/supply-chain-policy.md`](docs/supply-chain-policy.md) and
locked in
[`decisions/2026-05-11-supply-chain-security-gates.md`](decisions/2026-05-11-supply-chain-security-gates.md).

If you suspect a Main Branch release, dependency update, or workflow has been
compromised, follow the private report path above rather than opening a public
issue.

## Scope

In scope:

- Unsafe file writes outside the requested repo
- Unsafe handling of symlinks or bridge links
- Path traversal in `mb init`, `mb skill link`, `mb resolve`, or related CLI
  commands
- Accidental exposure of private business data in generated files or logs
- GitHub Actions, packaging, or release workflow issues that could affect users
- Supply-chain issues in the published `mainbranch` package, the publish
  workflow, or pinned GitHub Actions used by this repo

Out of scope:

- Bugs in Claude Code or Anthropic accounts
- Bugs in GitHub, pipx, Python, or operating-system package managers
- Prompt-injection reports that require a user to intentionally paste hostile
  content into their own private business repo, unless Main Branch amplifies that
  content into an unsafe action
- Social engineering against maintainers or community members

## Response expectations

Per the commitment near the top of this file: acknowledge within 7 days, fix
within 30 days when practical. For valid reports we coordinate a fix, publish
a patch release when needed, and credit the reporter unless they prefer to
remain anonymous.

There is no paid bug bounty program.
