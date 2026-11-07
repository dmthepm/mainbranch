# Cloudflare Pages Git Link

Two scenarios live in this doc, in order of how often you'll hit them:

0. **Provider readiness check** (must be green before Pages/DNS/domain tool calls)
1. **First time on this Cloudflare account: bind the GitHub App** (the OAuth handshake step that gets you out of CF code `8000011`)
2. **Manual Pages project creation via dashboard** (rare — `pages.py create-project` is the default; this is the dashboard fallback)

---

## 0. Provider readiness check

Before Cloudflare Pages, DNS, custom-domain, deploy, or domain-purchase work,
run this from the business repo:

```bash
mb connect doctor --json
```

If `provider:cloudflare` is not `ready`, connect the account token before
continuing:

```bash
mb connect cloudflare --metadata token_type=account --metadata account_id=...
mb connect test cloudflare
```

`cfat_` account tokens route automatically when `account_id` metadata is
present; `token_type=account` stays in the command because it is explicit and
works on older `mb` versions. User API tokens remain supported as a fallback by
omitting `token_type=account`.

---

## 1. Bind the Cloudflare Pages GitHub App to your account (first-time-per-account)

You only need this once per Cloudflare account. Skip if `pages.py create-project` is already working without `github_app_not_installed` errors.

**Background.** CF Pages needs two things:

- The **GitHub App** installed on the GitHub account/org that owns your site repo (so CF can read commits)
- An **OAuth handshake** between that install and your CF account (so CF knows which install to use for *your* projects)

Just installing the App on GitHub isn't enough. The OAuth handshake fires from the CF dashboard, not from GitHub. The non-obvious part: the dashboard never has a stand-alone "set up Git integration" button. The handshake gets triggered only as a side-effect of starting the Workers/Pages **Create application** flow. You don't have to actually create anything — connecting the repo in the flow is enough; the OAuth side-effect is what we want.

**The path that works (Devon's verified discovery):**

1. Go to https://dash.cloudflare.com — confirm the right account is selected (top-left switcher)
2. Left sidebar: **Build** group → **Compute** → **Workers & Pages**
3. Click **Create application** (blue button, top-right)
4. Click **Continue with GitHub** (or "Continue with GitHub" — wording varies by recent UI updates)
5. Authorize the **Cloudflare Workers and Pages** GitHub App when GitHub asks. Choose the GitHub account or org that owns your site repo.
   - If GitHub asks "All repositories" vs "Only select repositories" — pick "All repositories" for least friction across future sites, or pick the specific repo if you want to scope tightly.
6. After GitHub redirects you back to Cloudflare, you'll see a list of your repos. **Connect a repo** — any repo is fine; the connection itself is what completes the OAuth handshake.
7. **Don't finish creating the application.** Close the tab or click cancel. The handshake already fired the moment GitHub redirected back to CF.

Once that's done, `pages.py create-project` (or any API call to `POST /pages/projects` with `source.type=github`) will work for repos owned by the account you authorized.

**If you have multiple GitHub accounts/orgs**: install on each one that owns repos you'll deploy from. Each install fires its own OAuth handshake, so repeat the steps above per account.

**Direct install URL** (only useful if you've already done the dashboard handshake at least once): https://github.com/apps/cloudflare-workers-and-pages — visit this to add the App to additional GitHub accounts/orgs after the initial bind.

**Symptom you should never see again:** `pages.py create-project` returning `error.code: github_app_not_installed` with CF error code `8000011`. If you do, the OAuth handshake hasn't fired for the GitHub account that owns the target repo — repeat the steps above.

---

## 2. Manual Pages project creation via dashboard (fallback)

Only use this if `pages.py create-project` can't be used for some reason (CI environment, no API access). The tool is the default path.

1. Go to https://dash.cloudflare.com
2. Left sidebar: under the **Build** group, click **Compute** → **Workers & Pages**. (Cloudflare moved this entry under Compute; if you remember it as a top-level link, look one level deeper.)
3. Click **Create application**
4. Click the small link at the bottom: **Pages: Get started**. Do not choose the Worker option.
5. Select **Connect to Git**
6. Authorize GitHub if prompted, then select the site repository.
7. Configure build settings:
   - Project name: the intended Pages project name, for example `thelastbill`
   - Production branch: `main`
   - Build command: empty for plain static HTML, or the template's build command
   - Build output directory: `/` for plain static HTML, or the template's output directory
8. Click **Save and Deploy**

First build usually takes 1-2 minutes. After the deploy succeeds, Cloudflare shows the `*.pages.dev` URL. The custom domain attachment is handled separately by `pages.py set-domain`.
