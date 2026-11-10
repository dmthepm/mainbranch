# Reports playbook

Upstream skill: `seo-report` (OpenSEO v0.1.26). Every other upstream skill ends by saving through it. Load `seo-report` for the HTML rules, the starter template and the title format. This file adds the business layer.

## Use it for
- Giving the owner one page that answers "did search help the business, what broke, what do you need to approve".
- A monthly check-in that compares like with like.
- Handing a finished audit, keyword or competitor readout to someone who will not open chat.
- Saving a named, repeatable layout (a report template) for a recurring brief.
- Producing a page the owner can print to PDF.

## Cost before you run
| Tool | Paid? | What drives cost | Source price |
|---|---|---|---|
| `save_report`, `list_reports`, `get_report` | No | none | "Uses no credits" (`report-tools.ts:118,314`) |
| `list/save/delete_report_template` | No | none | `report-template-tools.ts:39,131,190` |
| `set_report_sharing` | No | none; hosted only | `report-sharing-tools.ts:35` |
| `delete_report`, `delete_report_template` | No, but permanent | none | `report-tools.ts:387` |

Worked estimate (derived): a monthly report built from Search Console and Analytics reads, an audit already saved, and the month's spend note costs $0 in credits and DataForSEO. A report only costs what the research behind it cost. Put that figure in the report, from the log, not from memory.

Estimate tool: none needed. Nothing here recurs. The one real risk is non-financial: public sharing, covered below.

## Run it well
1. Start from the question. Write the decision the owner must make before collecting anything. A report with no decision is a table of metrics.
2. Call `list_reports` first. Reusing a title is refused. If the subject and period match, pass the `reportId` and replace it. A new month is a new report (`report-tools.ts:118`).
3. Replacing is final. There is no version history and the old content is gone (`report-tools.ts:86,124`). Before replacing, copy the old summary into the business repo.
4. Read a report back from its summary. Pass `includeHtml` only to edit a passage. If the returned HTML looks cut off, do not save over it.
5. Keep the page small: aim under 80 KB. The hard limits are 500,000 bytes of HTML and a 2,500-character summary (`reports.ts:13,37`).
6. Lead with the verdict and the one thing to approve or do. Then outcomes (sign-ups, installs, purchases) before visibility, then technical health, then work done, then next month's actions with owner, cost and approval needed.
7. Compare with the previous period every time, with the same data sources and the same windows. Say when a source was missing.
8. Split branded and non-branded search. Branded growth can hide a non-branded decline.
9. Label every figure: measured, tool estimate, or your own inference. Search volume and difficulty are estimates.
10. Add the month's data spend: estimated per run, and the actual by provider when the owner can read it (the DataForSEO dashboard is one; OpenRouter, Cloudflare and Context.dev are others, see [costs.md](costs.md)). Write "unknown" where a provider's figure is missing. Self-hosted OpenSEO shows neither estimates nor actuals.
11. Follow a report template only when the owner names it. Templates belong to one project.
12. New reports are private. Share publicly only when the owner asks in so many words, and only on hosted OpenSEO. A self-hosted copy has no public link; the app link needs a sign-in. Never offer a public link as a default.
13. Cadence: monthly for the owner. Weekly, send a short alert only if a threshold trips. The report itself is free, but any paid research behind it still needs the owner's yes. Quarterly, add what worked, what to stop and the budget.

## Read the result
Worth sending:
- It names one decision, the evidence for it, and what it costs.
- Numbers match the sources, and each has a date and a source.
- Every claim of effect is labelled as hypothesis unless a before and after exists.
- The owner can act without opening another tab.

What this does not prove:
- A report is evidence, not a decision. Saving one does not approve spend, edits or outreach.
- Rankings are not outcomes. Report revenue, leads or sign-ups first.
- A month of better results after a change does not show the change caused it. Season, ads, email and brand demand all move organic traffic.
- Analytics credits the last touch, so search-assisted sales do not show.
- A saved HTML report is not a record of the data. If the copy is lost, so is the report.
- A pretty chart is no more correct than its table. Print the numbers.

## Save
The report lives in OpenSEO; the record lives in the business repo. Write `research/YYYY-MM-DD-seo-report-<period>.md` with the verdict, the top action, key numbers with source and date, market, spend (estimated and actual, or unknown), coverage, what was missing, and the report title and saved date. Do not store the report link as the only copy. Owner choices go to `decisions/`. If the owner approved public sharing, say so and record the date. No raw exports, no secrets.

## App business vs store business
App business with a website:
- Lead with sign-ups or installs that started on the website. App store conversion sits outside the web reports; say how it is measured, or that it is not.
- Web organic is a small part of app growth. Say so.
- Quiet weeks are normal. Report monthly.

Small store:
- Lead with organic purchases and revenue from Analytics ecommerce, then add-to-cart.
- Add a short check after each theme change or sale period.
- Note seasonality before praising or blaming a month.

## Sources
- OpenSEO: `plugins/openseo/skills/seo-report/SKILL.md`; `src/server/mcp/tools/report-tools.ts`, `report-sharing-tools.ts`, `report-template-tools.ts`; `src/types/schemas/reports.ts`; `docs/maintainers/specs/0012-dynamic-reports.md`.
- Search Engine Land, "SEO reporting: how to track, prove and improve performance." https://searchengineland.com/guide/seo-reporting (accessed 9 Nov 2026).
- Google Search Console Help, "What are impressions, position, and clicks?" https://support.google.com/webmasters/answer/7042828 (accessed 9 Nov 2026).
