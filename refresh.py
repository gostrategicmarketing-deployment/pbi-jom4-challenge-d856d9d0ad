#!/usr/bin/env python3
"""Pull the JOM4 September challenge campaigns from Meta and rebuild the dashboard.

    python3 refresh.py               # rebuild dashboard.html (the Claude artifact); republish it after
    python3 refresh.py --site _site  # also write the GitHub Pages site: index.html + version.json + robots.txt
                                     # (and skip the full ads listing, which only a live re-rank in Claude uses)

The Claude artifact refreshes itself live through the viewer's Meta Ads connector; the baked
snapshot is only what shows before (or without) that read. The GitHub Pages copy has no
connector, so its GitHub Actions workflow runs this script every 15 minutes.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
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
CREATIVE_FIELDS = "creative{id,object_type,video_id,image_hash,effective_object_story_id}"

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
        }
    for a in listing:
        keep(a)

    # Every ad that has spent is then looked up by id. The listing can end early with no error
    # (2026-09-17 09:33: 312 of ~990 ads came back and 136 spending ads fell out of Best creative),
    # and by id it is ~6 calls, so the Pages build uses this path alone.
    missing = sorted({a["id"] for a in ads if a["spend"] > 0 and a["id"] not in creatives})
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
    return ads, creatives, thumbs


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
    ads, creatives, thumbs = pull_ads(today, full_listing)
    return {"source": "snapshot", "pulled_at": datetime.now(TZ).isoformat(timespec="seconds"), "rows": rows,
            "ads": ads, "creatives": creatives, "thumbs": thumbs}


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
        (site / "version.json").write_text(json.dumps({"pulled_at": snap["pulled_at"]}))
        (site / "robots.txt").write_text(ROBOTS)

    spend = sum(r["spend"] for r in snap["rows"])
    leads = sum(r["leads"] for r in snap["rows"])
    print(f"{len(snap['rows'])} campaign-day rows, ${spend:,.2f} spent, {leads:.0f} Meta leads, pulled {snap['pulled_at']}")
    print(f"{len(snap['ads'])} ads with delivery, {len(snap['creatives'])} ads mapped to a format, {len(snap['thumbs'])} previews baked")


if __name__ == "__main__":
    main()
