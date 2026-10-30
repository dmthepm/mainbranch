# Native Linux Secret Service evidence for `mb connect` (0.5.3)

Date: 2026-09-12. Package under test: `mainbranch` 0.5.3 from PyPI.

Every Linux test in the repository suite is simulated, and is named as such.
This report records the first native runtime evidence for the Secret Service
adapter shipped in #959, gathered on an Ubuntu 24.04 host by a separate
operator lane, using synthetic values only.

## Environment

- Ubuntu 24.04 LTS, x86_64, Python 3.12.3, unprivileged user, no sudo.
- `gnome-keyring` 46.1 run from the distribution archive build in a throwaway
  collection under a private D-Bus session (`dbus-run-session`), with
  `XDG_DATA_HOME`, `XDG_RUNTIME_DIR`, and `XDG_CONFIG_HOME` pointed at a fresh
  sandbox directory. The collection held zero items before the run.
- `SecretStorage` 3.5.0, reached through the bounded helper subprocess.
- No prompter (`gcr`) installed.

## What is now proved natively

- **Selection and health.** `SecretStore()` auto-selects `secret-service`;
  `health()` reports `ready` against a live collection.
- **Round trip.** Store, exact read-back, in-place update, and delete, through
  both `SecretStore` and the `mb connect` / `mb connect status` CLI surfaces.
  Values carrying leading spaces, a trailing tab, and embedded newlines came
  back byte-identical. The update reused the same D-Bus item path rather than
  delete-then-add.
- **Locked collection.** With the collection locked, every operation returned
  `secret_service_locked` in roughly 0.08 s. A D-Bus monitor over the whole run
  recorded **zero `Unlock` calls and zero `Prompt` interactions**, and the
  collection remained locked afterwards. A `Lock` call from the harness appears
  in the same trace as a positive control, confirming the monitor captured
  method calls. `mb connect` stored nothing and left repo metadata unchanged.
- **Backend absent.** With no Secret Service on the bus, the state is
  `secret_service_unavailable`: `mb connect` refuses to store, writes no
  metadata, and does not fall back to plaintext.
- **Value confidentiality.** A per-run marker embedded in every stored value
  appeared in no process argv (sampled every 20 ms, with a planted-marker
  positive control proving the sampler worked), no CLI stdout or stderr, no
  exception message, no daemon log, no D-Bus traffic, and no repo file.
- **Transport.** Session negotiation used
  `dh-ietf1024-sha256-aes128-cbc-pkcs7` throughout; no `plain` algorithm.

## What remains unproved on Linux

Carried forward honestly rather than rounded up:

- A PAM-unlocked desktop login keyring activated through the systemd user
  socket. The daemon here was the distribution binary, but started manually
  under a private bus.
- Behaviour when a prompter is installed. Zero `Unlock`/`Prompt` calls is what
  demonstrates Main Branch did not request one; it does not demonstrate what a
  prompter would do if asked.
- Individually locked items inside an unlocked collection. `gnome-keyring` does
  not produce that state, so the corresponding branch stays simulated.
- In-place update of a legacy Python `keyring` item (`application: "Python
  keyring library"`). Only Main Branch-created items were exercised.
- Other Secret Service implementations (KeePassXC, KWallet bridge, oo7) and
  other distributions.

## Defects found

Two, both filed after independent confirmation in the source:

- `mb connect` `--json` failure paths emit no JSON (#973).
- `mb update` prints an upgrade and a Codex refresh that did not happen (#974).

## `mb update` on uv, same run

The uv path added in #963 was exercised against uv 0.12.13 at a real terminal
on a throwaway tool install: `--check` reported mode `uv` and ran nothing;
answering **no** left the install byte-identical and exited 0; answering
**yes** really ran `uv tool install mainbranch@latest`, changing the uv receipt
and the entrypoint, and exited 0. It could not demonstrate a version *change*,
because 0.5.3 is the newest release; repeat when a later version exists.

One consequence worth stating plainly: an install of **0.5.2 or earlier** as a
uv tool cannot reach this path, because uv detection ships in 0.5.3. Those
operators get `unsupported install mode: wheel` and must run
`uv tool install mainbranch@latest` themselves once.
