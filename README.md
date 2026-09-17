# PBI JOM4 challenge dashboard

Meta cost per Lead event for the September 2026 5-Day Challenge ads in the JOM4 ad account:
Lead Magnet, DTC and all campaigns combined, for today, so far, and day by day.

The workflow in `.github/workflows/refresh.yml` pulls Meta with `refresh.py`, builds the page and
deploys it to GitHub Pages, then starts its own next run 30 minutes later (GitHub's cron is not
reliable on this account, so the cron is only a fallback). The chain stops handing on after
`CHAIN_UNTIL`. To restart it or pull by hand: Actions, refresh, Run workflow.

Credentials are Actions secrets only: `FB_TOKEN`, a read-only Meta token, and the optional
`WINDSOR_API_KEY`, which lets the pull read the ads' creative details (format, image hash, post id)
from Windsor.ai instead of Meta. Every number on the page comes from Meta either way. Nothing
generated is committed; the page deploys as a Pages artifact.

Canonical source lives in Phil's workspace (`PBI/2026-09-17 - JOM4 Challenge Dashboard/`); copy
`dashboard.src.html` and `refresh.py` here after editing them and push, which also redeploys.
