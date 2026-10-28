# Machine Setup: An Always-On Box For Your Agents

This guide is for operators who want their agents to keep working while the
laptop is closed. You set up one small computer that stays on, run Main Branch
and Claude Code there, and use your laptop and phone only to look in and steer.

Read the concepts first. They decide most of the steps, and they stay the same
whichever machine or operating system you pick.

If you are brand new to Main Branch, start with
[`beginner-setup.md`](beginner-setup.md) on your laptop. Come back here when
you want the work to run without you.

---

## Part 1: Concepts

### Foundation first, interface last

Set up the parts that keep the work safe and running first: the machine, its
accounts, sessions that survive a reboot, credentials, backups and updates.
Pick how you talk to it last. The Claude app, a terminal, a text bot or a phone
client are all interfaces, and you can swap them at any time. No update,
restart or health check should depend on one of them.

### The box works; the laptop is a remote control

Start every agent session on the always-on box, never on the laptop. The
laptop and phone only view and steer. The test is simple: close the laptop for
30 minutes in the middle of a task, then reconnect. If anything stopped, the
setup is not finished.

### One user account per business

Give each business its own Linux (or macOS) user account, with its own home
folder, business repo, sign-ins and keys. Make the home folder private (only
its owner can open it) and give each account its own private temporary
folder. Creating the account alone doesn't do this; check the permissions.

With private homes, separate accounts give you:

- one business's agent can't read another business's private files or keys;
- a mistake, a runaway test or a leaked key is far more likely to stay inside
  one account;
- you can remove one business without touching the others.

Separate accounts are a strong wall between neighbours, not separate
machines. They don't protect against:

- a shared kernel, CPU, memory and disk: one account can still slow or crash
  the box for everyone;
- a shared network: every account can reach the same local services, other
  accounts' local ports, your home network and the internet;
- local services that every account can talk to, some of which act with more
  authority than the caller;
- anything in a world-readable place, such as system service definitions:
  never put a secret there;
- root: your admin account, or anyone who gains root, can read every
  account.

Controls that narrow these gaps (per-account network fences, process
restrictions, a reviewed local gate) are still in design and are not part of
this guide.

Running a single business? Still use a separate agent account, apart from your
own login.

### Admin account and agent accounts

- **Your admin account** is the only one with `sudo`. You use it to install
  system packages, change firewall rules and create users.
- **Agent accounts** never have `sudo`, and none is in a powerful group such
  as `sudo`, `adm` or `docker` (membership in `docker` is effectively root).
  When an agent needs a root step, it writes the exact command and you run it
  from the admin account. `sudo` always asks for your password.
- Sign-ins are yours too. An agent can prepare a sign-in command; you complete
  it.

### Shared tools, private data

Tools every account uses (a Python runtime, `uv`, `gh`, `hledger`, a terminal
multiplexer) can be installed once in a shared tree that root owns and no other account
can write to. Pin each tool to an exact version (never `latest`) and put the
tree first on every account's PATH. Data never goes there: repos, tokens,
caches and transcripts stay in each account's home folder.

### Sessions that survive a reboot

Agents run inside a terminal multiplexer such as `tmux`, or Herdr if you want
a client built for coding agents. Run the multiplexer as a systemd **user
service** and turn on **linger** for that account, so it starts at boot and
keeps running after everyone logs out. Give each account its own slice with
memory and process limits, sized from the box's RAM with room left for the
system, so one business is much less likely to starve the others or the
desktop.

### One heavy job at a time

Full test suites, builds and local transcription can take the machine down if
several run at once. Use one lock for heavy work, shared by every account
including yours, so only one heavy job runs at a time. Run each job with its
own memory cap and time limit, so a runaway job is killed alone. Never hold
the lock while waiting on a model, a dev server or a watch mode. A small box
is fine when heavy work takes turns.

### Accounts talk through a gate, not shared folders

Don't give accounts read access to each other's home folders, and don't
set up a shared folder that several accounts write to. Anything one agent
drops there, another may act on.

The intended pattern is a gate: a small program with a narrow, fixed set of
messages that stamps who sent each one. That gate is deferred: it needs its
own reviewed design and is not part of this setup yet. Until then, when one
business needs something from another, you carry it across yourself.

### Credentials

- Each key does one job: read-only when reading is enough, test mode until
  live is needed, and its own key per machine and per agent account.
- Set an expiry date when the vendor offers one.
- Keep keys in the OS keychain or a password manager and hand them to one
  command at a time (see [`connect.md`](connect.md)). Never put a key in a
  repo, a chat, a screenshot or a prompt.
- The box holds its own credentials. Closing the laptop must not break
  anything on it.

### Backups and updates

- **Backups:** business repos push to GitHub, which is the first backup. Also
  back up every account's home folder, plus a record of users, groups and
  permissions, to a place off the box (keys and local state excluded or
  encrypted). Pass one real restore test before any business data goes on the
  box, then repeat it on a schedule.
- **Updates:** on Ubuntu LTS, security updates install automatically but the
  box never reboots itself; on a rolling release such as Omarchy, nothing
  updates by itself and you run the full update about weekly (see Part 3).
  Turn off agents' self-update and move tool versions one at a time, testing
  after each; on a box with a shared tool tree, update Main Branch by moving
  its pin there rather than running `mb update` in each account. Reboot in a
  window you choose. Firmware and BIOS updates happen only with
  you at the machine. The reboot test below is what makes scheduled reboots
  safe.

### Mac or Linux for the box

| | Linux (Ubuntu LTS, Omarchy) | macOS (Mac mini) |
|---|---|---|
| Runs with nobody logged in | Yes, with linger and user services | Needs care: user agents start at login, background work needs launchd setup |
| Separate agent accounts | Standard | Possible; less common |
| Remote admin | SSH | SSH or Screen Sharing |
| Power draw | Low on mini PCs | Very low |
| Best when | You want the most control per dollar | You already live on Apple and want iMessage-based tools |

This guide's steps are written for Linux. A Mac mini works as the box for one
business, but plan extra time for running background services without a
logged-in user. For several businesses, Linux gives you more to work with,
such as per-account memory caps. Choosing Linux doesn't separate the
businesses by itself: the limits under
[One user account per business](#one-user-account-per-business) apply on
both.

---

## Part 2: Picking a machine

Small and quiet is enough. Most of the work is waiting on the network. What
matters most is RAM (agents, browsers and local tools add up), a fast SSD, and
a BIOS setting that powers the machine back on after an outage.

Prices and specs below were checked on vendor pages on 28 Oct 2026. Prices
change; check before you buy.

| Budget | Example | Notes |
|---|---|---|
| Used, low cost | Lenovo ThinkCentre Tiny or Dell OptiPlex Micro (8th gen Intel or newer) | Plenty for several businesses with 32 GB RAM. Buy the adapter wattage the vendor recommends for that CPU. |
| New, mini PC | Lenovo ThinkCentre M70q Gen 4 | Up to 64 GB DDR4 in two slots, one M.2 plus one 2.5" bay. Lenovo certifies Ubuntu 22.04 LTS for it. |
| New, mini PC | Beelink SER8, 32 GB / 1 TB | $859 on the vendor page. Two M.2 slots, 2.5 GbE, auto power-on. |
| Apple | Mac mini (M6) | From $899 with 16 GB, configurable to 32 GB. About 4 W at idle. See the macOS notes above. |
| Higher end | Framework Desktop | From $1,269 (32 GB). CPU and RAM are soldered, so buy the RAM you will need. |

**A measured data point.** On a 2018 ThinkCentre Tiny (Intel i7-8700T,
32 GB class), local transcription with faster-whisper large-v3-turbo on the
CPU processed 1 hour of audio in about 25 minutes, peaking at 2.5 GB of RAM.
That was one measurement on one file, but every new pick above has a faster
CPU.

**Power-on after an outage.** Set it in the BIOS before the box goes in a
closet:

- Lenovo: Power menu, *After Power Loss*, set to *Power On* (the default is
  *Last State*).
- Dell OptiPlex: *AC Recovery*, set to *Power On* (the default is *Power
  Off*).

---

## Part 3: The operating system

### Ubuntu LTS (recommended default)

Use the server edition or a minimal desktop install, with full-disk
encryption. You get long-term support, automatic security updates
(`unattended-upgrades`, with automatic reboot left off) and AppArmor.

Disk unlock is a trade-off between coming back alone and protecting a
stolen box:

- **Passphrase only:** a stolen box stays locked, but the box waits at the
  prompt after every reboot or power cut, and the reboot test fails.
- **TPM unlock:** the box comes back by itself. It protects a stolen box only
  if the boot chain is verified: Secure Boot on, and the key enrolled through
  your distribution's supported procedure so the TPM releases it only to the
  expected, measured boot. A TPM unlock without that can hand the disk to
  whoever boots the box. Anyone with physical access still gets more chances
  than with a passphrase.
- **Either way:** keep the recovery key in your password manager, and read it
  back from a second device before you rely on unattended reboots. A
  firmware or BIOS update can make the TPM refuse and fall back to the
  recovery key, so do those only when you are at the machine.

### Omarchy (Arch-based)

Omarchy is an Arch Linux setup with a rolling release, so updates arrive
continuously instead of in yearly versions.

- **Recognize it:** `/etc/os-release` has `ID=omarchy`, and
  `pacman -Q omarchy` shows the installed package. On Omarchy 4 and later it
  is a system package, so older checks for a folder in your home directory
  give a false "no".
- **Update it** with `omarchy update`, not raw `pacman -Syu`, so its own
  migrations run. Nothing updates by itself: run it about weekly, never
  upgrade a single package on its own, and reboot after a kernel, systemd or
  glibc update. It takes a filesystem snapshot first, so a bad update can be
  rolled back. Treat the AUR as untrusted code, and keep it out of the shared
  tools.
- **Turn off auto-login and lock the screen.** Omarchy logs in automatically
  by default. On a box that is always on, that leaves an open desktop for
  anyone who walks up. Turn auto-login off and turn on the idle lock. The
  desktop is your session only; agents never run in it.
- **Disk unlock.** The same trade-off as Ubuntu applies. On Arch-based
  systems, TPM unlock is often set up with Secure Boot off, which binds the key
  to less of the boot chain. If you can't set it up with Secure Boot, a
  passphrase is the safer choice, and the box will wait for you after a
  reboot.
- **Security modules differ.** There is no AppArmor; Landlock is available.
  Checks written for Ubuntu's AppArmor don't apply.
- Because it is rolling, check after each update that the multiplexer service
  and your agents came back.

### Managing it from a Mac

Your MacBook is the remote control.

- Connect over a private network such as Tailscale. Use Tailscale as the
  network only and log in with OpenSSH, not Tailscale's own SSH feature.
- **Installing Tailscale doesn't close anything else.** `sshd`, a dev server
  or any other program can still listen on the box's other network
  interfaces. The box needs an inbound firewall that:
  - denies incoming connections by default;
  - allows SSH only from your tailnet, or narrower, from the devices you
    administer from;
  - is changed only while you keep a tested way back in (a working session
    or the console), so you never lock yourself out by removing the broad
    rule first.

  The exact firewall rules depend on your system; this guide doesn't ship
  them yet. Dev servers and debug ports should listen on loopback only.
- Use SSH with keys only and turn off password logins. Keep the admin key on
  the Mac, ideally in a password manager that approves each use.
- If you need the screen, reach a VNC server that listens only on the box's
  loopback through an SSH forward. Never open a VNC port.
- Open the multiplexer over SSH, or use Claude Code Remote Control from the
  browser or the Claude app to steer a session that is running on the box.
  See the Claude Code docs for its current requirements.

---

## Part 4: First week

Have your agent prepare each command in a terminal pane. You read it and
press Enter. Root steps run from your admin account.

1. Install the OS with disk encryption, and choose how it unlocks (see
   Part 3). Set the BIOS to power on after an outage. Read the disk recovery
   key back from a second device.
2. Install Tailscale on the box, the laptop and the phone. SSH by key only.
   Set up the inbound firewall described in
   [Managing it from a Mac](#managing-it-from-a-mac), keeping a tested way
   back in.
3. Create your admin account and one agent account per business. No `sudo`
   for agent accounts. Check that each home folder and temporary folder is
   private.
4. Install shared tools once, read-only for agent accounts. In each agent
   account, install Main Branch and set up the business repo
   ([`beginner-setup.md`](beginner-setup.md)).
5. Turn on linger for each agent account and run the multiplexer as a user
   service.
6. **Reboot test:** reboot the box, and from the laptop check that every
   account's multiplexer came back without anyone logging in.
7. Start one Claude Code session per business on the box. Reach it from the
   laptop and from the phone. Keep the interface you like.
8. **Lid-closed test:** start a capped test run, close the laptop for 30
   minutes, reopen it and check that the run finished.
9. Practice a key roll once with a fake key, so a real leak is routine.
10. Set up backups and pass one restore test before real business data goes
    on the box.

---

## What comes next

A read-only `mb machine doctor` is planned. It will check the items in this
guide (accounts, linger, services, updates, power-on, screen lock) and report
them as JSON with exit codes, without changing anything or using `sudo`.
Until it ships, the reboot and lid-closed tests above are the check.
