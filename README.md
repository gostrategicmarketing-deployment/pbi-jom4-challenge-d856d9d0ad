# JOM4 Challenge Dashboard (September 2026, Portrait Client Fill-Up)

**Claude page (live via connector):** https://claude.ai/artifact/GTUGvyaNHEJzsFfhipZXca (private artifact, Phil's account)
**Shared link (GitHub Pages, public but noindexed):** https://gostrategicmarketing-deployment.github.io/pbi-jom4-challenge-d856d9d0ad/
(repo `gostrategicmarketing-deployment/pbi-jom4-challenge-d856d9d0ad`, pushed 2026-09-17)

Built 2026-09-17 on Phil's brief: Meta's **Lead standard event** cost is the headline, plus link clicks,
cost per link click, conversion rate (leads / link clicks) and spend; a Lead Magnet section, a DTC section
and all campaigns combined; a "So far" view and a daily view. **Landing pages** (added 2026-09-17, Phil:
"include the link clicks for each URL in the report daily") splits it all by destination URL.

This page deliberately departs from two PBI reporting defaults in `PBI/CLAUDE.md`, because Phil asked for it:
it headlines **Meta** (not Hyros), and it shows **conversion rate**. Do not "fix" either.

**Target is $20 for this dashboard (Phil, 2026-09-19)**, not PBI's standing $15 cold CPL target.
`CFG.target` in `dashboard.src.html` is the single source; the chip text and chart label derive from it.
Mentions of "the $15 target" below this point are historical (written while it was $15).

## What it reads

- Account `act_1059453438345899` (JOM4, America/Chicago days), from 2026-09-17 (first delivery day) to today.
- **Scope: the whole account, minus an explicit exclusion list.** Every campaign delivering in
  `act_1059453438345899` since START counts. `EXCLUDED_CAMPAIGNS` in `refresh.py` is the only way
  spend leaves the report, and `CAMPAIGN_GROUP` puts a campaign in a group its name does not
  announce. Both are keyed by **campaign id**, so renaming a campaign in Meta changes nothing.
  Currently excluded: **MOF | September 2026 | VIP** (`120251185599730642`), the $17 upsell sold to
  people already registered, which is a paid step rather than a challenge lead source (Phil,
  2026-09-22); and **MOF | September 2026 | Group** (`120251208389810642`), the FB-Group ask, a
  downstream step for people already registered rather than a challenge lead source (Phil,
  2026-09-23); and **MOF | September 2026 | Reminder** (`120251264640210642`), attendance reminders
  to registrants, launched 2026-09-26 and excluded on the same precedent.
- **Groups:** the id in `CAMPAIGN_GROUP` wins; failing that, "Lead Magnet" + "September 2026" or
  "LM Retargeting" + "September 2026" is **Lead Magnet** and "September DTC" or "September 2026 DTC" is **DTC**. A campaign
  matching neither is **"other"**: its spend and clicks count in the combined totals and it gets its
  own row under "Other campaigns", but it is in neither group card. Every pull prints the spend per
  group and warns, with ids, about anything in "other"; `daily.csv` carries an **Unclassified spend**
  column that is normally `0.00` and is the one cell showing Lead Magnet + DTC failing to add up to
  the total. "Other" contributes **no leads**, because GHL counts a person once per group whichever
  campaign sent them, so an unclassified campaign's registrants are already inside the group totals.

  **Why, and what it cost (2026-09-22).** The pull used to filter Meta on `campaign.name CONTAIN
  "September"` and then drop anything the group rules did not match. By 2026-09-22 that hid
  **$804.06** of challenge spend, 1.9% of the account, with no warning anywhere: two CBOs launched
  on 9-21 without "September" in their name (`DTC Untested Grids`, `DTC Ad #79 Carousel`) were never
  fetched, and `September 2026 Warm Audience`, `MOF | September 2026 | VIP` and
  `MOF | September 2026 Retargeting Viewers` were fetched and then discarded by `group_of`. All but
  VIP send traffic to funnels GHL already counts (`/newclients1`, and `/newclients`, which 301s onto
  the FB Ads 6 funnel), so their **registrants were in the headline while their spend was not**, and
  every cost per lead on the page read low: all campaigns $20.66 against a true $21.06, DTC $22.93
  against $23.86. Meta's own Lead event showed the same hole, 3,675 on the page against 3,710 in the
  account: exactly Warm Audience's 30 plus Retargeting Viewers' 5.
- **Leads are credited to a campaign by id, never by name.** Campaign names are not unique: five
  campaigns were called "TOF | September DTC V12 | B-Roll + Skits - Full Sweep" on 2026-09-22, and
  the old name-keyed lookup in `credit_campaigns` gave all of their opt-ins to whichever id was read
  last.
- Leads = Meta's `lead` action, which on these website campaigns equals `offsite_conversion.fb_pixel_lead`
  (checked per campaign 2026-09-17). The Lead Magnet campaigns optimise for CompleteRegistration, not Lead.
  It is still what the **Meta leads** column shows, unscaled, beside whatever the Leads column counts.
- **Leads are scaled to GHL, per group, from a dated calibration pair.** `CFG.leadCal` in
  `dashboard.src.html` holds `{meta, actual, asOf}` for `lm` and `dtc`; the factor is `actual / meta`, so
  the pair is its own record of where the number came from. Re-calibrate by replacing a pair, never by
  editing a percentage. `LEAD_CAL` in `refresh.py` mirrors it (there it only orders the baked previews).
  Every cost per lead and conv. rate on the page uses the adjusted whole-lead count; the baked snapshot
  keeps Meta's raw count, and the card note prints Meta's number beside the factor.

  **Calibrated 2026-09-17 ~14:25 CT** against the counts Phil read off GHL, paired with a live Graph read
  the same moment:

  | Group | Meta `lead` | GHL actual | Factor | Meta runs |
  |---|---|---|---|---|
  | Lead Magnet | 352 | 186 | 52.84% | 1.89x |
  | DTC | 179 | 147 | 82.12% | 1.22x |
  | Combined | 531 | 333 | 62.71% | 1.60x |

  This replaced the first-pass 75% Lead-Magnet factor (set that morning off Meta 37 = GHL 27) and it gave
  **DTC a factor for the first time**: DTC was being shown at Meta's raw count, which overstated it by 22%.
  The correction matters for the $15 target: real CPL is **$11.50 Lead Magnet and $16.69 DTC** ($13.79
  combined) where the old page read $8.10 / $13.70 / $10.37, so DTC is over target, not under it.

  **Three explanations were ruled out before fitting a ratio**, because a structural fix would beat a factor:
  - **No Meta action equals GHL's number.** Lead Magnet: `lead` 352, `complete_registration` 444,
    `fb_pixel_custom` 389, `landing_page_view` 1,886, against GHL's 186. DTC: `lead` 179,
    `fb_pixel_custom` 139, against 147. Nothing lands on it, so the event choice is not the bug.
  - **Not cross-campaign double counting.** An account-level read filtered to each group returns exactly
    the sum of its campaigns (352 and 179), so Meta is not crediting one person to several campaigns.
  - **Not repeat fires being counted.** Meta returns `unique_actions` only for `link_click` here (about 5%
    under the total), and none at all for the conversion events, so no de-duplicated Meta count exists.

  So the gap is the funnel pixel genuinely firing the event more often than GHL creates a contact, and a
  measured ratio is the only route. It is **one calibration point on one day**, and the two groups differ
  by a lot, so re-check it against GHL every few days while the campaigns run and replace the pairs.
- **Whole leads are rounded, not floored** (changed 2026-09-17 with the calibration). Flooring biased every
  row and every day downwards, and would have read the calibration point itself back as 185 of Meta's 352.
  Days are still rounded one at a time, so the daily rows can land a lead or two either side of the total.

## Daily totals spreadsheet (2026-09-17)

**Google Sheet:** [PBI JOM4 Challenge Daily Totals](https://docs.google.com/spreadsheets/d/1R0rzPt3FFkTiiKJUrSXXOiCtSs-lr3uNCLnZ4nmnX6s/edit)
(gostrategicmarketing Drive, My Drive root; a Daily tab and a Notes tab). Cell A1 of Daily is
`=IMPORTDATA(".../daily.csv")` against the Pages
site, so it keeps itself current (Sheets re-fetches roughly hourly; Pages caches 10 min). Phil asked for
it the same evening: "a combined total of leads each day, revenue, spend, link clicks, conversion rate".

- `daily_csv()` in `refresh.py` writes `daily.csv` (site) and `data/daily.csv` (local): one row per CT
  day since START plus a Total row. Combined leads, spend, link clicks, conv. rate (%), cost per lead,
  cost per link click, purchases, revenue, ROAS; then the Lead Magnet / DTC split, Meta's own Lead event,
  and a "Leads source" column saying which count each day used (GHL, or the fallbacks).
- Leads mirror the page exactly (GHL per group, else Hyros / Meta scaled). Plain numbers only, no `$`
  or `%` in cells, so the Sheet reads them as numbers.
- **Revenue is Meta's pixel Purchase value** (`offsite_conversion.fb_pixel_purchase` in `action_values`),
  labelled in the column name. Day one: 90 purchases, $1,570, all at $17. Hyros read $0 sales for these
  six campaigns, and the GHL token 401s on `/payments/orders` and `/payments/transactions` (no payments
  scope). **To switch revenue to GHL's real orders, Phil adds payment read scopes to the Private
  Integration in GHL**, then filter orders to the challenge funnels. Meta over-counted leads on these
  funnels, so treat pixel revenue as an upper estimate until then.
- Phil approved publishing revenue in the public (noindexed) `daily.csv` on 2026-09-17.
- **Built from an .xlsx, not a CSV.** Drive's CSV-to-Sheet conversion stores `=IMPORTDATA(...)` as plain
  text (the first attempt did); an .xlsx upload keeps it a formula. Until someone opens the Sheet and
  clicks "Allow access" for the external URL, an export reads `#REF!`.

## Leads: GHL's own count, both groups (from the evening of 2026-09-17)

Phil handed over the PBI location's GHL Private Integration Token "to pull the stats for the challenge from
GHL for opt ins each day", with the six DTC funnel stats pages. `pull_ghl()` in `refresh.py` does it.

- **Source:** `GET /forms/submissions` (LeadConnector API v2, `Version: 2021-07-28`, location
  `GmBTEcbq9PN9YY99gncv`), once per opt-in form, all pages, since `GHL_SINCE`. Each submission carries
  `others.funneEventData.funnel_id` (sic) and the landing URL's `h_ad_id` / `fbc_id` in
  `others.eventData.url_params`. About 2 seconds a pull. The funnel stats screen itself has no public API.
- **Funnels (`GHL_FUNNELS`):** "PCFU | Sept 2026 | Straight | Broad Paid | FB Ads 1"-"6" =
  `/newclients1`-`/newclients6`, checked 2026-09-17 by fetching each page and finding its funnel id.
- **Credit by funnel, not by form.** Every page also embeds the FB Ads 1 form (a pop-up); on day one one
  of those was submitted on FB Ads 5. Pulling the six forms and keeping only submissions whose funnel is
  one of the six catches it; a new form added to a page would not be seen until it joins `GHL_FUNNELS`.
- **A lead is a person**, counted once, on the Central day and in the funnel of their first opt-in into
  any of the six. Day one: 194 submissions from 184 people. Days, funnels, campaigns and ads all add up to
  the same total. People first seen before `START` (the team's test opt-ins on Sep 14-16) are left out.
- **Ad credit** is the `h_ad_id` Meta fills into the link: 178 of 184 matched a JOM4 DTC ad on day one.
  The other 6 (direct, organic, or an unfilled `{{ad.id}}`) count in the totals and the funnel grid only,
  and the campaign note and method say how many. So the campaign table, Best creative and Landing pages
  now rank DTC on GHL's real opt-ins per ad instead of Meta × 82%.
- **Cross-checks on day one:** Phil's hand-read GHL 147 at ~14:25 CT against the API's 151 people by
  14:25 (the read time is approximate); Hyros had 142; Meta's Lead event 179 then, 242 by 19:23.
- **The funnel grid** ("DTC opt-ins by day, from GHL") is the six stats screens in one table.
- **Key:** `GHL_API_KEY`, else `~/Documents/Claude/Projects/PBI 2/ghl_key.txt` (chmod 600, gitignored,
  outside the repo). The Pages copy needs `GHL_API_KEY` as an Actions secret. Unset or failing, the pull
  falls back to Hyros exactly as before, and the page labels whichever source it used.
- **Meta instant-form leads are added to the GHL count (2026-09-26).** "TOF | September 2026 DTC |
  Lead Form" (`120251246118210642`) is the first instant-form campaign: its leads submit on Meta and
  never reach a funnel page, so GHL saw none of them and the campaign first read as unclassified spend
  ($562 by 10:39 CT, pushing All campaigns' cost per lead above both cards). `add_form_leads()` adds
  every campaign's `onsite_conversion.lead_grouped` to its group's GHL count by day, campaign and ad,
  and the card note prints the two halves ("GHL opt-ins, one per person, plus N Meta instant-form
  leads"). No double count: an instant-form lead never submits a GHL funnel form. Day one: 28 form
  leads against 2 pixel leads on that campaign.
- **Only counts leave `pull_ghl()`.** The API returns names, emails and phones; none of it reaches the
  snapshot or the public page. Keep it that way.
- **The Lead Magnet counts GHL too (Phil, 2026-09-17, same evening): the "Opt in 2" step.** Its funnel,
  "PCFU | Sept 2026 | Prelaunch | Paid" (`hTYEAkpzET9QE2oRFGce`), is a two-step opt-in: the PDF form on
  the landing page (both split versions), then the challenge opt-in, form `EDTzBgd6y72Tp5cKCvE3` on
  step `438bd0ab-...` (`/pixel-thank-you-page-2-8368vcds2`, one page, no split), which GHL names
  "Opt in 2". The lead is that second step, one per person. The morning's hand-read "GHL 186" was this
  count (187 people had submitted it by 14:00 CT, against 459 landing-page PDF opt-ins). Day one at
  19:35 CT: 250 submissions from 249 people, 231 credited to a Lead Magnet ad by `h_ad_id` (92% carry
  one), against Meta × 53% = 273. Only that step is pulled and filtered on its step id, so a form
  swapped onto the thank-you page would read as zero until it joins `GHL_GROUPS`.
- **Groups live in `GHL_GROUPS`** (`step`, `model`, `label`, funnels). The snapshot's `leadsrc` is
  `{group: counts}`; when GHL fails it becomes `{dtc: Hyros}` and the Lead Magnet returns to
  `CFG.leadCal`. The page handles every shape (checked 2026-09-17 on four builds: GHL, Hyros fallback,
  an old Hyros-only snapshot, and no source at all).
- **Someone in both groups counts once in each** (2 people on day one), so All campaigns can run a
  lead or two above the number of distinct people.

## Leads: Hyros (DTC fallback), Meta scaled to GHL for the Lead Magnet

- **Superseded the same evening by GHL (section above); this is now the fallback path.**
  **DTC leads came from Hyros** (Phil, 2026-09-17: "that seems to be pretty accurate"). On the day
  it went in, Hyros counted 142 DTC leads where GHL had 147 and Meta's Lead event 179, so it lands
  on GHL's number without a ratio fixed on one morning. The Lead Magnet stays on Meta scaled to GHL
  by `CFG.leadCal` (53% that day). `HYROS_GROUP` in `refresh.py` and `CFG.leadCal` in the template
  are the two places that decide this.
- **Two reads, and the order matters.** Campaign rows (`SOURCE_LINK`) first, then the day-grouped
  read (`timeGroupingOption=DAY`, buckets in the account's CT day, which is the page's own clock).
  Hyros locks every source id a day-grouped read touched and answers anything else for those ids
  with `400 Already processing a request for id: ...`; measured 2026-09-17, that lock outlasts 105
  seconds, while plain campaign reads never collided. So: one day-grouped read per pull, last, and
  a collision waits 20s, 40s, 60s… A pull every 30 minutes sits comfortably outside the lock.
- **The day bucket de-duplicates and the campaign rows do not**, so the campaign table can add up a
  lead or two above the DTC total (145 against 144 on 2026-09-17). The campaigns note says so; do
  not "fix" it by summing the rows.
- **A failed read carries the last one forward** from the site's published `hyros.json`
  (`published_hyros`), but only within the same day, and the page then prints "its last good read:
  spend has moved on since" beside its pull time. Falling back to Meta would step the series
  mid-campaign, which is the thing Hyros was brought in to avoid.
- **Ad-level blocks stay on Meta**, scaled to GHL: Hyros is read at campaign level, so Best creative
  and Landing pages cannot use it, and both say so on the page.
- Key: `HYROS_API_KEY`, else `~/Documents/Claude/Projects/PBI 2/hyros_key.txt` (the PBI-scoped key;
  Lance's key returns an empty result here). **The Pages copy needs `HYROS_API_KEY` as an Actions
  secret** — without it the pull warns and the page falls back to Meta scaled to GHL, which is a
  clean fallback, not a broken page.
- Model is `last_click` with `sourceConfiguration=ALL_SOURCES`, which is how the account's own
  report screens attribute. `cost` comes back 0 under day grouping, so spend stays Meta's.

## Landing pages

- The split is **by the link on each ad**, read from its creative (`object_story_spec`, then
  `asset_feed_spec`), not by ad set name. An ad set can mix pages: the DTC builds from V4 on set the
  page per ad, and two ads named "- Copy" sitting in the "Sarah Gardner | newclients3" set point at
  /newclients2: 218 of that set's 269 link clicks on day one were that pair, not the page the set
  is named for. `page_key` drops
  the scheme, `www.`, the query string (the UTM tags) and the trailing slash, so a page is `/newclients5`
  on the main domain and `host/path` anywhere else.
- The **so far** table runs off the same ad rows as Best creative, so it re-splits on a live read in
  Claude too. The **day grid** needs ad-by-day rows, which only the pull has, so it is snapshot-only
  and says when it was pulled.
- **The day grid is windowed (`URL_DAYS`, 7) and carried forward.** One row per ad per day is the only
  way to split a day by page, and at a few hundred delivering ads a fortnight of them would be a dozen
  calls every half hour against a token Meta meters by CPU. Each pull re-reads the last week and takes
  the older days from the site's own published `url_days.json` (`published_url_days`); a day is long
  finished before it leaves the window. If that file cannot be read the grid simply starts at the
  window, and a warning says so.
- Windsor supplies the destination as its `link` field (checked against Meta's creative read on
  2026-09-17: identical on all four sampled ads, images and videos). A Windsor row without a link is
  dropped so Meta's by-id read maps that ad instead.
- Link clicks are `inline_link_clicks` in this pull and the `link_click` action in the ad totals: the
  two matched ad for ad on 2026-09-17 (3,862 each), and `inline_link_clicks` is much cheaper to read.
  Cross-checked the same day: the page split summed to 3,880 link clicks against 3,880 at ad set level.

## Best creative

- **A running tally per creative, top 10** (Phil, 2026-09-18: "all the creative that isn't just for today ... a
  running tally of the best creatives from when the ad started ... top 10, not just the top 5", for both groups).
  The same image or video runs under several ads: V1-V3 were rebuilt as V4-V6, and the 2026-09-18 hook-page fix
  paused ads and replaced them with new ones carrying the same media. Ranked per ad, each rebuild restarted a
  creative's count from zero and split its history across ad ids (on the 14:22 CT pull, 100 DTC image ads held
  only 48 distinct images). So every ad since START that used the same **image hash** (images) or **video id**
  (videos) is added up into one card, paused and replaced ads included; `creativeKey()` in the template and
  `creative_key()` in `refresh.py` define the match, and an ad with neither stands alone rather than merge by
  guess. The card's name, preview and "View post" come from its highest-spending ad; **Ads** on the card is how
  many ads with spend it ran in. The tally starts at START (2026-09-17), the first day these campaigns ran: a
  video that also ran in older promos brings none of that history, because those promos counted a different lead.
- Ranking: leads desc (GHL's per ad when GHL was read, else Meta scaled to GHL, unrounded), then cost per lead
  asc, then spend desc, over creatives with **at least $20 spent** in total since START (`CFG.minSpend` /
  `MIN_SPEND`, Phil 2026-09-17); top `CFG.topN` / `TOP_N` = 10 per block, images and videos ranked separately;
  backfilled by link clicks when fewer than 10 creatives have leads. Thin data = under $25 spend or 20 link
  clicks. PBI's two retired webinar image hashes are excluded (none are in these campaigns; the guard is cheap).
- **Video ids: the uploaded video's, not the creative's.** A creative's own `video_id` is a copy Meta makes per
  ad: three ads of "Ad #2 Throwing Cameras v2 5DBB.mp4" carried three different ids on 2026-09-18, while
  `object_story_spec.video_data.video_id` was the same upload in all three. Keyed on that, DTC's 214 spending
  video ads are 93 videos (the per-ad id made them 186); matching the account library's upload title plus
  length on top merged nothing more, so re-uploads of one file are not a live problem. The token cannot read
  a video object itself (`#10`), but the account's `/advideos` edge lists title and length if that is ever needed.
- Windsor has no per-ad video id either (checked 2026-09-18; its `video_asset_video_id` is an asset
  breakdown, not the ad's video), so a video ad Windsor mapped gets its id from the site's published
  `creatives.json` (the last pull's map, `published_creatives`) while its creative id is unchanged, and from
  Meta's by-id read otherwise. The first site pull after the change reads every video ad once (~7 calls);
  after that only new or edited video ads are read.
- Format comes from the creative (`video_id` or `object_type == VIDEO` = video). A LOCAL build maps every ad in the
  "September 2026 Lead Magnet" and "September DTC" campaigns (~990 by 09:30 on 2026-09-17, superseded ads included),
  so a live re-rank in Claude can still tell formats apart; the Meta Ads connector has no creative fields. Every
  ad that has spent is then read by id, because the `/ads` listing can end early with no error (09:33 that day:
  312 came back and 136 spending ads, $1,693, dropped out of Best creative). The Pages build (`--site`) skips the
  listing and uses the by-id read alone: ~6 calls instead of ~20. Doubling the pulls to every 15 minutes on the
  listing put the token's app over Meta's ad-account call limit ("too many calls to this ad-account") the same
  morning.
- **Windsor.ai (added 2026-09-17, optional):** with `WINDSOR_API_KEY` set (Actions secret, or env locally),
  the pull reads format, image hash, creative id and post id for every spending ad from Windsor in one call,
  and Meta's by-id read only covers ads Windsor has not returned. A site pull then costs Meta 3 calls instead
  of ~9. Checked the same day: 260 of 260 spending ads identical to Meta's own creative read. Rows are kept
  only for JOM4 ads the Graph read shows delivering, because the Windsor key reaches every connected client
  account. A Windsor failure is a warning, never a failed pull.
  **Windsor supplies no numbers, on purpose.** The Basic plan serves a repeated query from cache: the same
  campaign read 3 minutes apart returned identical spend while Meta had moved $6-7 per campaign. Creative
  details never change once an ad exists, so a cached answer is fine for them and wrong for spend and leads.
  Windsor also timed out on `include_objects_without_insights`, so the local full listing stays on Meta.
- Previews: creative `thumbnail_url` at 320x400, inlined as data URIs for the top 13 creatives per block (10
  shown, 3 spare), one per creative from its highest-spending ad (Meta image URLs are signed and expire; the
  artifact CSP blocks remote images anyway). A creative that
  climbs into the top 10 live in Claude without a baked preview shows a placeholder until the next publish; the
  GitHub copy rebuilds every 30 minutes so it is always current. "View post" links use the post permalink from
  `effective_object_story_id`, never fb.me.
- The `/ads` listing must page at 50: at 100 Meta answers page two with "reduce the amount of data".

## Refresh

- **Live:** opened in Claude, the page calls the viewer's **Meta Ads** connector (`ads_get_ad_entities`,
  campaign level, `time_increment` 1) and refreshes every 5 minutes; the Refresh button forces a read.
  The connector returns `ad_entities` as a JSON string with currency strings like `$142.76 USD`.
- **Snapshot:** `python3 refresh.py` pulls the same rows through the Graph API with the `PBI 2/fb_token.txt`
  token and bakes them into `dashboard.html`. That is what shows before the live read lands, or without
  the connector. Republish `dashboard.html` to the URL above afterwards.

- **GitHub Pages:** the deploy repo (checked out at `.deploy/`, gitignored here) runs `refresh.py --site _site`
  in Actions, deploys it, then dispatches its own next run 30 minutes on (briefly 15 on 2026-09-17; Phil set it back to 30 the same morning) (GitHub's cron sheds runs on this
  account; see the `github-actions-cron-is-unreliable` memory). The cron `12,42 * * * *` is only a way back in.
  The chain stops handing on after `CHAIN_UNTIL` (2026-10-15 CT) in the workflow; restart or pull by hand with
  Actions -> refresh -> Run workflow. The token is the repo's `FB_TOKEN` secret (same read-only token as the
  webinar dashboard). Pages caches files 10 minutes, so the page fetches `version.json?cb=` on load, on tab
  focus and on Refresh, and reloads under `?v=` when a newer pull exists. An open tab also checks every 2 minutes
  (added 2026-09-17: a tab left on screen never fires a focus event, so it sat on an old pull). A reload
  never repeats for the same `?v=`, so a stale edge copy cannot loop; Refresh retries once with `&r=`.
- **Times stay in CT**, with "N min ago" beside the pull time (e.g. `9:28 AM CT (3 min ago)`). On 2026-09-17
  Phil, on Eastern, read a 20-minute-old "9:00 AM CT" pull as stale and reported the refresh as broken; it
  was not (the chain had run every ~28.5 min all morning). A local-clock label was tried and reverted within
  the hour: Phil said CT is fine. Before calling the chain broken, compare `gh run list` and `version.json`
  with the clock, not the header.
- The Claude artifact was not republished with the "min ago" change (the republish guard wanted a full
  re-read of the 1MB page). Its next republish of `dashboard.html` picks it up.
- **After editing** `dashboard.src.html` or `refresh.py` here: copy both into `.deploy/`, commit and push
  (a push redeploys), and republish `dashboard.html` to the artifact.

## Files

```
dashboard.src.html  page template ({{LOGO}}, {{SNAPSHOT}})
refresh.py          Graph + GHL (Hyros fallback) pull -> data/snapshot.json + data/daily.csv -> dashboard.html (+ --site DIR: index.html, version.json, url_days.json, creatives.json, hyros.json, robots.txt)
dashboard.html      built page (what gets published as the artifact)
brand/              PBI reversed logo, inlined at build
.deploy/            GitHub Pages deploy repo checkout (own git history)
```
