#!/usr/bin/env python3
"""Pull the JOM4 September challenge campaigns from Meta and rebuild the dashboard.

    python3 refresh.py               # rebuild dashboard.html (the Claude artifact); republish it after
    python3 refresh.py --site _site  # also write the GitHub Pages site: index.html + version.json + robots.txt
                                     # (and skip the full ads listing, which only a live re-rank in Claude uses)

The Claude artifact refreshes itself live through the viewer's Meta Ads connector; the baked
snapshot is only what shows before (or without) that read. The GitHub Pages copy has no
connector, so its GitHub Actions workflow runs this script every 30 minutes.

Every number comes from the Graph API. With WINDSOR_API_KEY set, the ads' creative details
(format, image hash, post id) come from Windsor.ai first, which saves Meta calls; without it,
or if Windsor fails, Meta supplies them as before.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
TOKEN_FILE = Path.home() / "Documents/Claude/Projects/PBI 2/fb_token.txt"
LOGOS = [HERE / "brand/pbi-logo-reversed.png",
         HERE.parent / "2026-08-12 - Webinar Dashboard/brand/pbi-logo-reversed.png"]

ACCOUNT = "act_1059453438345899"   # JOM4, America/Chicago
START = "2026-09-17"               # first delivery day of the challenge campaigns
TZ = ZoneInfo("America/Chicago")
NAME_FILTER = "September"          # the page classifies further, by name (see groupOf in the template)
LM_LEAD_FACTOR = 0.75              # mirrors CFG.lmLeadFactor; here it only decides which previews to bake
RETIRED_HASHES = {"5aa5b3c86b8de4813d14c4cf7ef428c1", "d8214f6e4cbe8373bb0f3b9f3ed79610"}  # PBI/CLAUDE.md
PREVIEWS_PER_BLOCK = 8             # the page shows 5; spares cover a live re-rank inside Claude
MIN_SPEND = 20                     # mirrors CFG.minSpend: an ad needs $20 spent to rank as best creative
CREATIVE_FIELDS = ("creative{id,object_type,video_id,image_hash,effective_object_story_id,"
                   "object_story_spec{link_data{link,call_to_action},video_data{call_to_action}},"
                   "asset_feed_spec{link_urls}}")
WINDSOR_URL = "https://connectors.windsor.ai/facebook"
MAIN_HOST = "photographybusinessinstitute.com"  # this host shows as a bare path; any other keeps its name
URL_DAYS = 7                       # trailing days of ad-by-day rows pulled for the landing-page grid
SITE_URL = "https://gostrategicmarketing-deployment.github.io/pbi-jom4-challenge-d856d9d0ad"

SKELETON = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
{head}
</head>
<body>
{body}
</body>
</html>
"""
ROBOTS = "User-agent: *\nDisallow: /\n"


def graph(url, params, fatal=True):
    """GET with retries on throttles and transient Graph errors; a real fault fails at once."""
    for attempt in range(6):
        args = ["curl", "-s", "-G", url, "-w", "\n%{http_code}"]
        for k, v in params.items():
            args += ["--data-urlencode", f"{k}={v}"]
        out = subprocess.run(args, capture_output=True, text=True).stdout
        body, _, status = out.rpartition("\n")
        try:
            data = json.loads(body)
        except ValueError:
            data = {"error": {"code": 2, "message": f"unreadable response (HTTP {status})"}}
        err = data.get("error")
        if not err:
            return data
        if err.get("code") in (1, 2, 4, 17, 32, 341, 613) or status.startswith("5"):
            time.sleep(min(300, 5 * 3 ** attempt))
            continue
        if not fatal and err.get("code") == 100:  # an id Meta cannot read; a throttle still stops the pull
            return None
        sys.exit(f"Meta error {status}: {err.get('message')}")
    sys.exit("Meta kept failing or throttling; try again in a few minutes.")


def token():
    return os.environ.get("FB_TOKEN") or TOKEN_FILE.read_text().strip()


def windsor_get(params):
    """One Windsor.ai connector read. Returns its rows, or None (with a warning) on any failure."""
    args = ["curl", "-s", "-G", WINDSOR_URL, "--max-time", "90", "-w", "\n%{http_code}"]
    for k, v in {**params, "api_key": os.environ["WINDSOR_API_KEY"]}.items():
        args += ["--data-urlencode", f"{k}={v}"]
    out = subprocess.run(args, capture_output=True, text=True).stdout
    body, _, status = out.rpartition("\n")
    try:
        data = json.loads(body)
    except ValueError:
        data = {}
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        err = data.get("error") if isinstance(data, dict) else None
        msg = err.get("message") if isinstance(err, dict) else err or f"unreadable response (HTTP {status})"
        msg = str(msg).replace(os.environ["WINDSOR_API_KEY"], "***")  # a bad-key error echoes the key back
        print(f"warning: Windsor read failed ({msg}); Meta looks the creatives up instead", file=sys.stderr)
        return None
    return data["data"]


def windsor_creatives(today, ad_ids):
    """Format, image hash and post id for the spending ads, from Windsor instead of Meta.

    Only this static metadata comes from Windsor. Its Basic plan serves a repeated query from
    cache (measured 2026-09-17: the same read 3 minutes later returned the same spend while
    Meta had moved $6-7 a campaign), so every number on the page stays on the Graph read.
    An ad's creative never changes, so a cached answer is still right; ads newer than the
    cache are simply absent and fall through to Meta's by-id read.
    """
    if not os.environ.get("WINDSOR_API_KEY"):
        return {}
    rows = windsor_get({
        "date_from": START,
        "date_to": today,
        "fields": "account_id,ad_id,creative_id,object_type,image_hash,effective_object_story_id,link,spend",
        "select_accounts": ACCOUNT.removeprefix("act_"),
        "filter": json.dumps([["campaign", "contains", NAME_FILTER], "and", ["spend", "gt", 0]]),
    })
    out = {}
    for r in rows or ():
        # Windsor's key reaches every connected client account: keep JOM4's ads only, and only
        # the ones the Graph read says are delivering, so nothing else lands on the public page.
        # No creative id or no destination link and the ad falls through to Meta's own read,
        # which is what the landing-page split needs; a half-mapped ad would read as unknown.
        if str(r.get("account_id")) != ACCOUNT.removeprefix("act_") or r.get("ad_id") not in ad_ids \
                or not r.get("creative_id") or not r.get("link"):
            continue
        out[r["ad_id"]] = {"id": r["creative_id"], "object_type": r.get("object_type"),
                           "image_hash": r.get("image_hash"), "link": r.get("link"),
                           "effective_object_story_id": r.get("effective_object_story_id")}
    return out


def link_of(creative):
    """The page an ad sends people to, from whichever shape of creative carries it."""
    cr = creative or {}
    if cr.get("link"):  # Windsor hands the destination over as one field
        return cr["link"]
    spec = cr.get("object_story_spec") or {}
    for part in ("link_data", "video_data"):
        d = spec.get(part) or {}
        cta = (d.get("call_to_action") or {}).get("value") or {}
        if d.get("link") or cta.get("link"):
            return d.get("link") or cta.get("link")
    for u in (cr.get("asset_feed_spec") or {}).get("link_urls") or ():
        if u.get("website_url"):
            return u["website_url"]
    return None


def page_key(url):
    """A landing page as the report names it: `/newclients5`, or `host/path` off the main domain.

    Query strings hold the UTM tags, which differ ad by ad and name no different page.
    """
    if not url:
        return None
    u = re.sub(r"^https?://", "", url.split("#")[0].split("?")[0].strip(), flags=re.I)
    u = re.sub(r"^www\.", "", u, flags=re.I).rstrip("/").lower()
    host, _, path = u.partition("/")
    return "/" + path if host == MAIN_HOST else (u or None)


def paged(url, params):
    out = []
    while url:
        data = graph(url, params)
        out += data["data"]
        url = data.get("paging", {}).get("next")
        params = {}  # the next URL carries every parameter
    return out


def group_of(campaign):
    if "lead magnet" in campaign.lower() and "september 2026" in campaign.lower():
        return "lm"
    if "september dtc" in campaign.lower():
        return "dtc"
    return None


def pull_ads(today, full_listing):
    """Ad-level totals since START, every ad's format, and small previews of the likely winners."""
    base = f"https://graph.facebook.com/v21.0/{ACCOUNT}"
    name_filter = {"field": "campaign.name", "operator": "CONTAIN", "value": NAME_FILTER}
    ads = []
    for r in paged(f"{base}/insights", {
        "level": "ad",
        "fields": "ad_id,ad_name,campaign_name,spend,actions",
        "time_range": json.dumps({"since": START, "until": today}),
        "filtering": json.dumps([name_filter]),
        "limit": "500",
        "access_token": token(),
    }):
        acts = {a["action_type"]: float(a["value"]) for a in r.get("actions", [])}
        ads.append({"id": r["ad_id"], "name": r["ad_name"], "campaign": r["campaign_name"], "spend": float(r["spend"]),
                    "link_clicks": acts.get("link_click", 0.0), "leads": acts.get("lead", 0.0)})
    ad_days = pull_ad_days(today)

    # Format for every ad in these campaigns, not just the ones that have spent, so a live
    # re-rank inside Claude can still tell an image from a video. Only a local build needs it:
    # it is ~20 calls a pull, and the Pages copy never re-ranks.
    creatives = {}
    listing = []
    # One listing per group name: the bare "September" filter would also page through every
    # September 2025 ad in the account.
    for group_name in ("September 2026 Lead Magnet", "September DTC") if full_listing else ():
        listing += paged(f"{base}/ads", {
            "fields": "id," + CREATIVE_FIELDS,
            "filtering": json.dumps([{"field": "campaign.name", "operator": "CONTAIN", "value": group_name},
                                     {"field": "ad.effective_status", "operator": "IN", "value":
                                      ["ACTIVE", "PAUSED", "ADSET_PAUSED", "CAMPAIGN_PAUSED", "ARCHIVED", "PENDING_REVIEW",
                                       "IN_PROCESS", "WITH_ISSUES", "DISAPPROVED", "PREAPPROVED"]}]),
            "limit": "50",  # 100 per page trips Meta's "reduce the amount of data" on page two
            "access_token": token(),
        })
    def keep(ad):
        cr = ad.get("creative") or {}
        creatives[ad["id"]] = {
            "f": "video" if cr.get("video_id") or cr.get("object_type") == "VIDEO" else "image",
            "h": cr.get("image_hash"),
            "c": cr.get("id"),
            "p": cr.get("effective_object_story_id"),
            "u": page_key(link_of(cr)),
        }
    for a in listing:
        keep(a)

    # Windsor next (one call, none against Meta's ad-account limit), when WINDSOR_API_KEY is set.
    spending = {a["id"] for a in ads if a["spend"] > 0}
    from_windsor = windsor_creatives(today, spending - creatives.keys())
    for ad_id, cr in from_windsor.items():
        keep({"id": ad_id, "creative": cr})

    # Every ad that has spent and is still unmapped is then looked up by id. The listing can end
    # early with no error (2026-09-17 09:33: 312 of ~990 ads came back and 136 spending ads fell
    # out of Best creative), and by id it is ~6 calls without Windsor, so the Pages build skips the
    # listing and relies on Windsor plus this read.
    missing = sorted(spending - creatives.keys())
    if os.environ.get("WINDSOR_API_KEY"):
        print(f"Windsor mapped {len(from_windsor)} ads; Meta looks up {len(missing)}")
    for i in range(0, len(missing), 50):
        chunk = missing[i:i + 50]
        data = graph("https://graph.facebook.com/v21.0/", {"ids": ",".join(chunk), "fields": CREATIVE_FIELDS,
                                                            "access_token": token()}, fatal=False)
        if data is None:  # one unreadable id fails the whole batch; read that chunk one by one
            data = {}
            for ad_id in chunk:
                one = graph(f"https://graph.facebook.com/v21.0/{ad_id}", {"fields": CREATIVE_FIELDS,
                                                                           "access_token": token()}, fatal=False)
                if one:
                    data[ad_id] = one
        for ad_id, v in data.items():
            keep({"id": ad_id, "creative": v.get("creative")})
    unmapped = [a for a in ads if a["spend"] > 0 and a["id"] not in creatives]
    if unmapped:
        print(f"warning: {len(unmapped)} spending ads have no creative (${sum(a['spend'] for a in unmapped):,.2f}); "
              "they cannot rank as best creative", file=sys.stderr)

    # Same ranking as the page: leads (Lead Magnet at 75%), then cost per lead, then spend;
    # plus the top by link clicks, which the page backfills with when few ads have leads.
    wanted = set()
    for g in ("lm", "dtc"):
        for f in ("image", "video"):
            block = [a for a in ads if group_of(a["campaign"]) == g and a["spend"] >= MIN_SPEND
                     and a["id"] in creatives and creatives[a["id"]]["f"] == f
                     and creatives[a["id"]]["h"] not in RETIRED_HASHES]
            factor = LM_LEAD_FACTOR if g == "lm" else 1

            def rank(a):
                adj = a["leads"] * factor
                return (-adj, a["spend"] / adj if adj else float("inf"), -a["spend"])
            picks = sorted(block, key=rank)[:PREVIEWS_PER_BLOCK]
            picks += sorted(block, key=lambda a: (-a["link_clicks"], -a["spend"]))[:5]
            wanted |= {creatives[a["id"]]["c"] for a in picks if creatives[a["id"]]["c"]}

    thumbs = {}
    wanted = sorted(wanted)
    for i in range(0, len(wanted), 50):
        data = graph("https://graph.facebook.com/v21.0/", {
            "ids": ",".join(wanted[i:i + 50]),
            "fields": "thumbnail_url",
            "thumbnail_width": "320",
            "thumbnail_height": "400",
            "access_token": token(),
        })
        for cid, v in data.items():
            if not v.get("thumbnail_url"):
                continue
            img = subprocess.run(["curl", "-sL", "--max-time", "20", v["thumbnail_url"]], capture_output=True).stdout
            if img[:3] == b"\xff\xd8\xff" or img[:4] == b"\x89PNG":
                kind = "png" if img[:4] == b"\x89PNG" else "jpeg"
                thumbs[cid] = f"data:image/{kind};base64," + base64.b64encode(img).decode()
    return ads, creatives, thumbs, ad_days


def pull_ad_days(today):
    """Every ad's link clicks and spend day by day, over a trailing window.

    Only ad-by-day rows can split a day by landing page, because one ad set can send its ads to
    several pages (the DTC builds from V4 on do). There is one row per ad per day, so the pull is
    windowed at URL_DAYS: at a few hundred ads delivering, a fortnight of them would be a dozen
    calls every half hour, and Meta counts this token's app against the ad account by CPU.
    Older days are carried forward from the published site instead (published_url_days).

    It runs straight after the ad totals so the two reads see the same minute: split by page they
    are the same clicks twice, and the page shows both.
    """
    since = max(START, (datetime.now(TZ).date() - timedelta(days=URL_DAYS - 1)).isoformat())
    rows = []
    for r in paged(f"https://graph.facebook.com/v21.0/{ACCOUNT}/insights", {
        "level": "ad",
        # inline_link_clicks matched the link_click action ad for ad on 2026-09-17 and is far
        # cheaper to read than the whole actions array.
        "fields": "ad_id,spend,inline_link_clicks",
        "time_range": json.dumps({"since": since, "until": today}),
        "time_increment": "1",
        "filtering": json.dumps([{"field": "campaign.name", "operator": "CONTAIN", "value": NAME_FILTER}]),
        "limit": "500",
        "access_token": token(),
    }):
        rows.append((r["ad_id"], r["date_start"], float(r.get("inline_link_clicks") or 0), float(r["spend"])))
    return since, rows


def by_page(ad_days, creatives):
    """Ad-by-day rows folded into one row per landing page per day."""
    agg = {}
    for ad_id, date, clicks, spend in ad_days:
        page = (creatives.get(ad_id) or {}).get("u") or "?"
        t = agg.setdefault((date, page), {"date": date, "page": page, "clicks": 0.0, "spend": 0.0})
        t["clicks"] += clicks
        t["spend"] += spend
    return sorted(agg.values(), key=lambda t: (t["date"], t["page"]))


def published_url_days(before):
    """The page-by-day rows from before this pull's window, read back off the published site.

    Nothing survives between GitHub Actions runs, so the site's own url_days.json is the store:
    each run rewrites the days it pulled and keeps what the last run knew about the days before
    them. A day is finished long before it leaves the window, so a carried-forward row is final.
    A missing or unreadable file costs history only, never a number on the page.
    """
    out = subprocess.run(["curl", "-sL", "--max-time", "20",
                          f"{SITE_URL}/url_days.json?cb={int(time.time())}"],
                         capture_output=True, text=True).stdout
    try:
        rows = json.loads(out)
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        print("warning: no published url_days.json; the page grid starts at the pulled window",
              file=sys.stderr)
        return []
    return [{"date": r["date"], "page": r["page"], "clicks": float(r["clicks"]), "spend": float(r.get("spend") or 0)}
            for r in rows if isinstance(r, dict) and isinstance(r.get("date"), str) and r["date"] < before
            and isinstance(r.get("page"), str) and isinstance(r.get("clicks"), (int, float))]


def pull(full_listing=True):
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    params = {
        "level": "campaign",
        "fields": "campaign_id,campaign_name,spend,actions",
        "time_range": json.dumps({"since": START, "until": today}),
        "time_increment": "1",
        "filtering": json.dumps([{"field": "campaign.name", "operator": "CONTAIN", "value": NAME_FILTER}]),
        "limit": "500",
        "access_token": token(),
    }
    url = f"https://graph.facebook.com/v21.0/{ACCOUNT}/insights"
    rows = []
    while url:
        data = graph(url, params)
        for r in data["data"]:
            acts = {a["action_type"]: float(a["value"]) for a in r.get("actions", [])}
            rows.append({
                "date": r["date_start"],
                "id": r["campaign_id"],
                "name": r["campaign_name"],
                "spend": float(r["spend"]),
                "link_clicks": acts.get("link_click", 0.0),
                "leads": acts.get("lead", 0.0),
            })
        url = data.get("paging", {}).get("next")
        params = {}  # the next URL carries every parameter
    ads, creatives, thumbs, (since, ad_days) = pull_ads(today, full_listing)
    url_days = sorted(published_url_days(since) + by_page(ad_days, creatives),
                      key=lambda t: (t["date"], t["page"]))
    return {"source": "snapshot", "pulled_at": datetime.now(TZ).isoformat(timespec="seconds"), "rows": rows,
            "ads": ads, "creatives": creatives, "thumbs": thumbs,
            "url_days": url_days, "url_pulled_from": since}


def build(snapshot):
    template = (HERE / "dashboard.src.html").read_text()
    logo = next((p for p in LOGOS if p.exists()), None)
    logo_uri = "data:image/png;base64," + base64.b64encode(logo.read_bytes()).decode() if logo else ""
    snap_json = json.dumps(snapshot, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace("{{LOGO}}", logo_uri).replace("{{SNAPSHOT}}", snap_json)
    if re.search(r"\{\{[A-Z]+\}\}", html):
        sys.exit("dashboard.src.html has an unfilled placeholder")
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", help="also write the GitHub Pages site into this directory")
    args = ap.parse_args()

    snap = pull(full_listing=not args.site)
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data/snapshot.json").write_text(json.dumps({k: v for k, v in snap.items() if k != "thumbs"}, indent=1))
    html = build(snap)
    (HERE / "dashboard.html").write_text(html)
    if args.site:
        site = Path(args.site)
        site.mkdir(parents=True, exist_ok=True)
        cut = html.index("</style>") + len("</style>")  # title, meta, fonts and CSS belong in <head>
        (site / "index.html").write_text(SKELETON.format(head=html[:cut], body=html[cut:].lstrip()))
        (site / "url_days.json").write_text(json.dumps(snap["url_days"], separators=(",", ":")))
        (site / "version.json").write_text(json.dumps({"pulled_at": snap["pulled_at"]}))
        (site / "robots.txt").write_text(ROBOTS)

    spend = sum(r["spend"] for r in snap["rows"])
    leads = sum(r["leads"] for r in snap["rows"])
    print(f"{len(snap['rows'])} campaign-day rows, ${spend:,.2f} spent, {leads:.0f} Meta leads, pulled {snap['pulled_at']}")
    print(f"{len(snap['ads'])} ads with delivery, {len(snap['creatives'])} ads mapped to a format, {len(snap['thumbs'])} previews baked")
    pages = sorted({r["page"] for r in snap["url_days"]})
    days = sorted({r["date"] for r in snap["url_days"]})
    unmapped = sum(r["clicks"] for r in snap["url_days"] if r["page"] == "?")
    print(f"{len(pages)} landing pages over {len(days)} days ({days[0] if days else '-'} to {days[-1] if days else '-'}, "
          f"pulled from {snap['url_pulled_from']}), {unmapped:.0f} link clicks on ads with no page")


if __name__ == "__main__":
    main()
