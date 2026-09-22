# PBI JOM4 challenge dashboard

Meta cost per Lead event for the September 2026 5-Day Challenge ads in the JOM4 ad account:
Lead Magnet, DTC and all campaigns combined, for today, so far, and day by day, with link clicks
broken out by landing page.

Scope is **every campaign delivering in the JOM4 account since the start date, minus an explicit
exclusion list**: `EXCLUDED_CAMPAIGNS` in `refresh.py` is the only way spend leaves the report
(currently just the $17 MOF VIP upsell), and `CAMPAIGN_GROUP` puts a campaign in a group its name
does not announce. Both are keyed by campaign **id**, so renaming a campaign in Meta changes
nothing. A campaign matching no group rule lands in "other": its spend and clicks count in the
combined totals and it gets its own row, the pull warns about it with its id, and `daily.csv`
carries an `Unclassified spend` column that is normally `0.00`. Do not reintroduce a campaign-name
filter on the Meta reads: that is what quietly dropped $804 of spend by 2026-09-22.

`url_days.json` is deployed beside the page and read back by the next run: it is where the
landing-page day grid keeps the days that have dropped out of the window each pull re-reads.

The workflow in `.github/workflows/refresh.yml` pulls Meta with `refresh.py`, builds the page and
deploys it to GitHub Pages, then starts its own next run 30 minutes later (GitHub's cron is not
reliable on this account, so the cron is only a fallback). The chain stops handing on after
`CHAIN_UNTIL`. To restart it or pull by hand: Actions, refresh, Run workflow.

DTC leads come from GHL itself: every opt-in on the six DTC funnels (/newclients1 to /newclients6),
one per person on the day of their first opt-in, credited to an ad by the Meta ad id in its link. Only
counts reach the page, never a name or an email. When GHL cannot be read the pull falls back to Hyros
(campaign level, last click); `hyros.json` deploys beside the page and is read back by the next run,
so a failed Hyros read carries the last good one forward. Lead Magnet leads come from GHL too: people
who reach the "Opt in 2" step (the challenge opt-in on the PDF thank-you page) of the Prelaunch | Paid
funnel, one per person; without GHL they fall back to Meta scaled to GHL.

`daily.csv` also deploys beside the page: one row per Central day plus a Total row, both groups
combined (leads, spend, link clicks, conv. rate, cost per lead and per click, Meta-pixel purchases,
revenue and ROAS) with the Lead Magnet / DTC split beside it. A Google Sheet imports it with
IMPORTDATA. Revenue is Meta's pixel Purchase value and is labelled as such.

Credentials are Actions secrets only: `FB_TOKEN`, a read-only Meta token, `GHL_API_KEY` (the PBI
location's GHL Private Integration Token, which counts the DTC opt-ins), `HYROS_API_KEY` (the
PBI-scoped Hyros key, the DTC fallback; with neither, the page falls back to Meta scaled to GHL), and the optional
`WINDSOR_API_KEY`, which lets the pull read the ads' creative details (format, image hash, post id)
from Windsor.ai instead of Meta. Spend and clicks come from Meta either way. Nothing
generated is committed; the page deploys as a Pages artifact.

Canonical source lives in Phil's workspace (`PBI/2026-09-17 - JOM4 Challenge Dashboard/`); copy
`dashboard.src.html` and `refresh.py` here after editing them and push, which also redeploys.
