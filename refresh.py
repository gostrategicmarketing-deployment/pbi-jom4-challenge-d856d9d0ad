#!/usr/bin/env python3
"""Pull the JOM4 September challenge campaigns from Meta and rebuild the dashboard.

    python3 refresh.py               # rebuild dashboard.html (the Claude artifact); republish it after
    python3 refresh.py --site _site  # also write the GitHub Pages site: index.html + version.json + robots.txt
                                     # (and skip the full ads listing, which only a live re-rank in Claude uses)

The Claude artifact refreshes itself live through the viewer's Meta Ads connector; the baked
snapshot is only what shows before (or without) that read. The GitHub Pages copy has no
connector, so its GitHub Actions workflow runs this script every 30 minutes.

Spend and clicks come from the Graph API; leads are GHL's own opt-ins (GHL_API_KEY or the PBI key
file), with Hyros (DTC) and Meta scaled to GHL (Lead Magnet) as the fallback when GHL cannot be read. With WINDSOR_API_KEY set, the ads' creative details
(format, image hash, post id) come from Windsor.ai first, which saves Meta calls; without it,
or if Windsor fails, Meta supplies them as before.
"""
import argparse
import base64
import csv
import io
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
HYROS_KEY_FILE = Path.home() / "Documents/Claude/Projects/PBI 2/hyros_key.txt"
LOGOS = [HERE / "brand/pbi-logo-reversed.png",
         HERE.parent / "2026-08-12 - Webinar Dashboard/brand/pbi-logo-reversed.png"]

ACCOUNT = "act_1059453438345899"   # JOM4, America/Chicago
START = "2026-09-17"               # first delivery day of the challenge campaigns
TZ = ZoneInfo("America/Chicago")
NAME_FILTER = "September"          # the page classifies further, by name (see groupOf in the template)
# Campaigns included regardless of NAME_FILTER; maps campaign_id → (group, name).
# Add here when a challenge campaign's name lacks the normal marker (e.g. a CBO launched mid-challenge
# without "September" in its name).
EXTRA_CAMPAIGNS = {
    "120251163829380642": ("lm", "TOF | LM Untested Statics | CBO | start 9-21"),
}
_EXTRA_NAME_GROUP = {name: g for g, name in EXTRA_CAMPAIGNS.values()}


def _extra_campaign_filter():
    """Filtering that matches EXTRA_CAMPAIGNS by id, for a second pass after the NAME_FILTER pass."""
    return [{"field": "campaign.id", "operator": "IN", "value": list(EXTRA_CAMPAIGNS)}] if EXTRA_CAMPAIGNS else None
# (Meta count, GHL count) per group, mirrors CFG.leadCal; here it only decides which previews to bake
LEAD_CAL = {"lm": (352, 186), "dtc": (179, 147)}   # calibrated 2026-09-17
LEAD_FACTOR = {g: actual / meta for g, (meta, actual) in LEAD_CAL.items()}
RETIRED_HASHES = {"5aa5b3c86b8de4813d14c4cf7ef428c1", "d8214f6e4cbe8373bb0f3b9f3ed79610"}  # PBI/CLAUDE.md
TOP_N = 10                         # mirrors CFG.topN: the page shows the top 10 creatives per block (Phil, 2026-09-18)
PREVIEWS_PER_BLOCK = 13            # the page shows 10; spares cover a live re-rank inside Claude
MIN_SPEND = 20                     # mirrors CFG.minSpend: a creative needs $20 spent to rank as best creative
CREATIVE_FIELDS = ("creative{id,object_type,video_id,image_hash,effective_object_story_id,"
                   "object_story_spec{link_data{link,call_to_action},video_data{video_id,call_to_action}},"
                   "asset_feed_spec{link_urls}}")
WINDSOR_URL = "https://connectors.windsor.ai/facebook"
MAIN_HOST = "photographybusinessinstitute.com"  # this host shows as a bare path; any other keeps its name
URL_DAYS = 7                       # trailing days of ad-by-day rows pulled for the landing-page grid
SITE_URL = "https://gostrategicmarketing-deployment.github.io/pbi-jom4-challenge-d856d9d0ad"
HYROS_URL = "https://api.hyros.com/v1/api/v1.0/attribution"
HYROS_GROUP = "dtc"                # the group the page headlines on Hyros (Phil, 2026-09-17)
# GHL counts the opt-ins itself (Phil, 2026-09-17 evening: the PBI location's Private Integration Token,
# "to pull the stats for the challenge from GHL for opt ins each day"). Each opt-in is credited to the
# funnel it happened on, not to its form: every DTC page also embeds the FB Ads 1 form (a pop-up), and
# one of those was submitted on FB Ads 5 on day one.
GHL_KEY_FILE = Path.home() / "Documents/Claude/Projects/PBI 2/ghl_key.txt"
GHL_URL = "https://services.leadconnectorhq.com"
GHL_LOCATION = "GmBTEcbq9PN9YY99gncv"
GHL_SINCE = "2026-08-27"           # the funnels' creation day: earlier test opt-ins still mark a person as seen
GHL_GROUPS = {
    # One funnel per DTC angle page, (funnel id, the page its ads link to, its opt-in form); any opt-in
    # on the funnel counts. /newclientsN -> funnel checked 2026-09-17 by fetching each page.
    "dtc": {"step": None, "model": "first opt-in per person", "label": "GHL opt-ins", "funnels": [
        ("rzT7SyOSpywdlOic3do4", "/newclients1", "gsQ4RSn5ZMOL8CmwgPJK"),
        ("pTOIcfaaQCUKlEHMGZq9", "/newclients2", "eixtVRDXqVk8AS8wcpGP"),
        ("kd8Lcj1tvn1IlC1E6Kh4", "/newclients3", "jGWovQ6bJAkeULv89Krt"),
        ("4BuDZTwD8y8bWqgcZl9v", "/newclients4", "FFRagASSSe0UFQcupPvZ"),
        ("CIN9xdqqyVUZ26rde44q", "/newclients5", "64TDlIPe74xrhR9SbjdQ"),
        ("QfrPvC6u3cq7zRX2dxjP", "/newclients6", "FNIl1Wnb3rsEx1nla0mU"),
    ]},
    # "PCFU | Sept 2026 | Prelaunch | Paid", behind /fallsessionplans: a two-step opt-in, the PDF form on
    # the landing page and then a second form on the PDF thank-you page. Phil, 2026-09-17: the lead is
    # that second step, the one GHL names "Opt in 2" (a single page, no split test; the hand-read 186 of
    # that afternoon was this count). Only its own form has ever been submitted there.
    "lm": {"step": "438bd0ab-e87c-4797-b0b9-f497e912bfae", "model": "the Opt in 2 step, one per person",
           "label": "GHL Opt in 2 sign-ups", "funnels": [
        ("hTYEAkpzET9QE2oRFGce", "/fallsessionplans", "EDTzBgd6y72Tp5cKCvE3"),
    ]},
}

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


def graph(url, params, fatal=True, shrinkable=False):
    """GET with retries on throttles and transient Graph errors; a real fault fails at once.

    `shrinkable`: hand "reduce the amount of data" back to the caller (as None) instead of
    retrying the same request, which Meta answers the same way every time.
    """
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
        if shrinkable and "reduce the amount of data" in str(err.get("message", "")):
            return None
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


def creative_key(c):
    """What makes two ads the same creative: the image hash, or the uploaded video's id; else the ad stands alone.

    Mirrors creativeKey() in the template. The same image or video runs under several ads (V1-V3
    were rebuilt as V4-V6, and replaced ads keep their media), so Best creative adds them up.
    """
    if c.get("f") == "video":
        return "v:" + c["v"] if c.get("v") else None
    return "h:" + c["h"] if c.get("h") else None


def published_creatives():
    """The creative map from the last published pull, so a video id is looked up once per ad.

    Windsor has no per-ad video id, and Meta's by-id read of every video ad would add ~6 calls to
    each pull. A creative never changes once made, so a published entry is reused only while the
    ad still points at the same creative id; an edited ad gets a new one and is read again.
    """
    out = subprocess.run(["curl", "-sL", "--max-time", "20", f"{SITE_URL}/creatives.json?cb={int(time.time())}"],
                         capture_output=True, text=True).stdout
    try:
        prev = json.loads(out)
    except ValueError:
        prev = None
    if not isinstance(prev, dict):
        print("warning: no published creatives.json; every video ad's id is read from Meta this pull", file=sys.stderr)
        return {}
    return {k: v for k, v in prev.items() if isinstance(v, dict)}


def paged(url, params):
    """Every page of a listing. A page Meta finds too heavy is asked for again at half the size.

    The /ads listing with creative fields grew past what Meta will serve at 50 a page on
    2026-09-18 (~1,500 ads): it answered "reduce the amount of data" on a page part-way through,
    every time, and the plain retry spent 13 minutes on it before the pull gave up.
    """
    out = []
    while url:
        data = graph(url, params, shrinkable=True)
        if data is None:
            limit = int(params.get("limit") or (re.search(r"[?&]limit=(\d+)", url) or [0, 50])[1])
            if limit <= 5:
                sys.exit("Meta refuses even 5 rows a page (\"reduce the amount of data\"); try again later.")
            limit = max(5, limit // 2)
            if params:
                params = {**params, "limit": str(limit)}
            elif re.search(r"[?&]limit=\d+", url):
                url = re.sub(r"([?&]limit=)\d+", rf"\g<1>{limit}", url)
            else:
                url += ("&" if "?" in url else "?") + f"limit={limit}"
            print(f"Meta asked for less data; paging at {limit}", file=sys.stderr)
            continue
        out += data["data"]
        url = data.get("paging", {}).get("next")
        params = {}  # the next URL carries every parameter
    return out


def group_of(campaign):
    if campaign in _EXTRA_NAME_GROUP:
        return _EXTRA_NAME_GROUP[campaign]
    n = campaign.lower()
    if ("lead magnet" in n or "lm retargeting" in n) and "september 2026" in n:
        return "lm"
    if "september dtc" in n:
        return "dtc"
    return None


def pull_ads(today, full_listing, ghl=None):
    """Ad-level totals since START, every ad's format, and small previews of the likely winners."""
    base = f"https://graph.facebook.com/v21.0/{ACCOUNT}"
    def _ad_insights_params(filtering):
        return {"level": "ad", "fields": "ad_id,ad_name,campaign_name,spend,actions",
                "time_range": json.dumps({"since": START, "until": today}),
                "filtering": json.dumps(filtering), "limit": "500", "access_token": token()}
    def _parse_ad(r):
        acts = {a["action_type"]: float(a["value"]) for a in r.get("actions", [])}
        return {"id": r["ad_id"], "name": r["ad_name"], "campaign": r["campaign_name"],
                "spend": float(r["spend"]), "link_clicks": acts.get("link_click", 0.0),
                "leads": acts.get("lead", 0.0)}
    ads = [_parse_ad(r) for r in paged(f"{base}/insights",
           _ad_insights_params([{"field": "campaign.name", "operator": "CONTAIN", "value": NAME_FILTER}]))]
    if _extra_campaign_filter():
        ads += [_parse_ad(r) for r in paged(f"{base}/insights",
                _ad_insights_params(_extra_campaign_filter()))]
    ad_days = pull_ad_days(today)

    # Format for every ad in these campaigns, not just the ones that have spent, so a live
    # re-rank inside Claude can still tell an image from a video. Only a local build needs it:
    # it is ~20 calls a pull, and the Pages copy never re-ranks.
    creatives = {}
    listing = []
    # One listing per group name: the bare "September" filter would also page through every
    # September 2025 ad in the account.
    ad_statuses = ["ACTIVE", "PAUSED", "ADSET_PAUSED", "CAMPAIGN_PAUSED", "ARCHIVED", "PENDING_REVIEW",
                   "IN_PROCESS", "WITH_ISSUES", "DISAPPROVED", "PREAPPROVED"]
    for group_name in ("September 2026 Lead Magnet", "September DTC") if full_listing else ():
        listing += paged(f"{base}/ads", {
            "fields": "id," + CREATIVE_FIELDS,
            "filtering": json.dumps([{"field": "campaign.name", "operator": "CONTAIN", "value": group_name},
                                     {"field": "ad.effective_status", "operator": "IN", "value": ad_statuses}]),
            "limit": "50",  # 100 per page trips Meta's "reduce the amount of data" on page two
            "access_token": token(),
        })
    for cid in (EXTRA_CAMPAIGNS if full_listing else ()):
        listing += paged(f"{base}/ads", {
            "fields": "id," + CREATIVE_FIELDS,
            "filtering": json.dumps([{"field": "campaign.id", "operator": "IN", "value": [cid]},
                                     {"field": "ad.effective_status", "operator": "IN", "value": ad_statuses}]),
            "limit": "50",
            "access_token": token(),
        })
    def keep(ad):
        cr = ad.get("creative") or {}
        # The uploaded video is the one in the story spec. The creative's own video_id is a copy
        # Meta makes per ad (three ads of one upload, three ids on 2026-09-18), so it matches nothing.
        # Meta's read only: Windsor has neither.
        video = ((cr.get("object_story_spec") or {}).get("video_data") or {}).get("video_id") or cr.get("video_id")
        creatives[ad["id"]] = {
            "f": "video" if cr.get("video_id") or cr.get("object_type") == "VIDEO" else "image",
            "h": cr.get("image_hash"),
            "v": video,
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
    missing = set(spending - creatives.keys())
    # Best creative adds up every ad that ran the same video, so a video ad mapped by Windsor still
    # needs its video id: from the last published map while its creative is unchanged, else from Meta.
    no_vid = [i for i in spending & creatives.keys() if creatives[i]["f"] == "video" and not creatives[i].get("v")]
    prev, reused = (published_creatives() if no_vid else {}), 0
    for ad_id in no_vid:
        p = prev.get(ad_id) or {}
        if p.get("v") and p.get("c") and p.get("c") == creatives[ad_id]["c"]:
            creatives[ad_id]["v"] = p["v"]
            reused += 1
        else:
            missing.add(ad_id)
    missing = sorted(missing)
    if os.environ.get("WINDSOR_API_KEY"):
        print(f"Windsor mapped {len(from_windsor)} ads; {reused} video ids carried from the last pull; "
              f"Meta looks up {len(missing)}")
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

    # Same ranking as the page (bestFor): every ad that ran the same image or video is added up into
    # one creative, since START and paused ads included; then leads (GHL's own opt-ins per ad when
    # the GHL read worked, otherwise Meta scaled to GHL per group), cost per lead, spend. When fewer
    # than TOP_N creatives have leads the page fills in by link clicks, and so do the previews.
    # One preview per creative: its highest-spending ad's, which is the one the page shows.
    wanted = set()
    for g in ("lm", "dtc"):
        src = (ghl or {}).get(g)
        factor = LEAD_FACTOR.get(g, 1)
        for f in ("image", "video"):
            tally = {}
            for a in ads:
                c = creatives.get(a["id"])
                if group_of(a["campaign"]) != g or not c or c["f"] != f or c["h"] in RETIRED_HASHES:
                    continue
                t = tally.setdefault(creative_key(c) or "a:" + a["id"], {"leads": 0.0, "spend": 0.0, "clicks": 0.0, "top": a})
                t["leads"] += src["ads"].get(a["id"], 0) if src else a["leads"] * factor
                t["spend"] += a["spend"]
                t["clicks"] += a["link_clicks"]
                if a["spend"] > t["top"]["spend"]:
                    t["top"] = a
            block = [t for t in tally.values() if t["spend"] >= MIN_SPEND]
            picks = sorted((t for t in block if t["leads"] > 0),
                           key=lambda t: (-t["leads"], t["spend"] / t["leads"], -t["spend"]))
            if len(picks) < TOP_N:
                picks += sorted((t for t in block if not t["leads"] > 0), key=lambda t: (-t["clicks"], -t["spend"]))
            wanted |= {creatives[t["top"]["id"]]["c"] for t in picks[:PREVIEWS_PER_BLOCK]
                       if creatives[t["top"]["id"]]["c"]}

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


def hyros_key():
    key = os.environ.get("HYROS_API_KEY")
    if key:
        return key.strip()
    return HYROS_KEY_FILE.read_text().strip() if HYROS_KEY_FILE.exists() else None


def hyros_get(params, key):
    """One /attribution read, with retries. Returns its rows, or None (with a warning).

    Hyros holds a lock on each source id while a request for it is in flight and answers a second
    one with 400 "Already processing a request for id". Two reads over the same campaigns therefore
    cannot simply follow one another, so a collision waits and goes again.
    """
    args = ["curl", "-s", "-G", HYROS_URL, "--max-time", "60", "-H", f"API-Key: {key}", "-w", "\n%{http_code}"]
    for k, v in params.items():
        args += ["--data-urlencode", f"{k}={v}"]
    detail = "no response"
    for attempt in range(5):
        out = subprocess.run(args, capture_output=True, text=True).stdout
        body, _, status = out.rpartition("\n")
        try:
            data = json.loads(body)
        except ValueError:
            data = {}
        rows = data.get("result") if isinstance(data, dict) else None
        if isinstance(rows, list):
            return rows
        message = data.get("message") if isinstance(data, dict) else None
        detail = "; ".join(message) if isinstance(message, list) else str(message or f"HTTP {status}")
        if "Already processing" in detail or status.startswith("5") or status == "429":
            time.sleep(20 * (attempt + 1))  # the lock on a day-grouped read outlasts 105 seconds
            continue
        break
    print(f"warning: Hyros read failed ({detail}); the page falls back to Meta's Lead event", file=sys.stderr)
    return None


def pull_hyros(today, rows):
    """Hyros leads for the headlined group: by day, and by campaign.

    Phil, 2026-09-17: Hyros is the lead count the DTC half of the page leads on, with Meta's Lead
    event kept beside it. Two reads, both campaign level and last click, because that is the model
    the account's own screens use:

      * `timeGroupingOption=DAY` gives one bucket per day, in the account's timezone (CT, the page's
        clock). Its `cost` comes back 0, which is fine: spend has always come from Meta.
      * the default `SOURCE_LINK` grouping gives one row per campaign, for the campaign table.

    The day bucket de-duplicates a lead that touched two of the campaigns and the campaign rows do
    not, so the rows can sum a little above the day total (144 against 141 on 2026-09-17). The page
    says so rather than forcing them to agree.

    The ids are every campaign of the group that delivered in the window, not just the ones running
    now: /attribution takes an explicit id list, so a campaign that has since been paused would
    otherwise drop out of its own day with no error at all.
    """
    key = hyros_key()
    if not key:
        print("warning: no Hyros key (HYROS_API_KEY or the PBI key file); the page falls back to "
              "Meta's Lead event", file=sys.stderr)
        return None
    ids = sorted({r["id"] for r in rows if group_of(r["name"]) == HYROS_GROUP})
    if not ids:
        return None
    base = {
        "startDate": START,
        "endDate": today,
        "attributionModel": "last_click",   # lowercase, as this endpoint wants it
        "level": "facebook_campaign",
        "sourceConfiguration": "ALL_SOURCES",  # how the account's own report screens attribute
        "fields": "leads",
        "ids": ",".join(ids),
    }
    # Campaign rows first: they are the read that never collides. The day-grouped read holds a lock
    # on every id it touched for minutes afterwards, so it goes last and only once per pull.
    campaigns = hyros_get(base, key)
    days = hyros_get({**base, "timeGroupingOption": "DAY"}, key) if campaigns is not None else None
    if days is None or campaigns is None:
        return published_hyros(today)
    return {
        "group": HYROS_GROUP,
        "model": "last click",
        "pulled_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "days": {r["id"]: float(r.get("leads") or 0) for r in days if isinstance(r.get("id"), str)},
        "campaigns": {r["id"]: float(r.get("leads") or 0) for r in campaigns if isinstance(r.get("id"), str)},
    }


def published_hyros(today):
    """The last good Hyros read, from the published site, when this pull's read failed.

    Hyros is one number on a page otherwise built from Meta, and falling back to Meta's own count
    mid-campaign would step the series at the changeover. Carrying the last read forward keeps the
    series whole; it arrives with its own pulled_at, which the page prints, and `stale` so the page
    can say that spend has moved on since. A read from an earlier day is not carried: by then the
    gap is too wide to label away.
    """
    out = subprocess.run(["curl", "-sL", "--max-time", "20", f"{SITE_URL}/hyros.json?cb={int(time.time())}"],
                         capture_output=True, text=True).stdout
    try:
        prev = json.loads(out)
    except ValueError:
        prev = None
    if not isinstance(prev, dict) or prev.get("group") != HYROS_GROUP or not isinstance(prev.get("days"), dict):
        print("warning: no usable published hyros.json either; the page falls back to Meta's Lead event",
              file=sys.stderr)
        return None
    if not str(prev.get("pulled_at", "")).startswith(today):
        print(f"warning: the published Hyros read is from before {today}; the page falls back to "
              "Meta's Lead event", file=sys.stderr)
        return None
    print(f"warning: carrying the Hyros read from {prev['pulled_at']} forward", file=sys.stderr)
    prev["stale"] = True
    return prev


def ghl_key():
    key = os.environ.get("GHL_API_KEY")
    if key:
        return key.strip()
    return GHL_KEY_FILE.read_text().strip() if GHL_KEY_FILE.exists() else None


def ghl_get(path, params, key):
    """One GHL API read with retries on throttles. Returns the JSON, or None (with a warning).

    curl, not urllib: GHL's Cloudflare blocks python-urllib's user agent with a 1010 that looks
    like an auth failure (the lance-ghl-api memory).
    """
    args = ["curl", "-s", "-G", GHL_URL + path, "--max-time", "60", "-w", "\n%{http_code}",
            "-H", f"Authorization: Bearer {key}", "-H", "Version: 2021-07-28", "-H", "Accept: application/json"]
    for k, v in params.items():
        args += ["--data-urlencode", f"{k}={v}"]
    status = "no response"
    for attempt in range(5):
        out = subprocess.run(args, capture_output=True, text=True).stdout
        body, _, status = out.rpartition("\n")
        if status == "429" or status.startswith("5"):
            time.sleep(5 * (attempt + 1))
            continue
        try:
            return json.loads(body) if status == "200" else None
        except ValueError:
            break
    print(f"warning: GHL read failed on {path} (HTTP {status})", file=sys.stderr)
    return None


def pull_ghl(today):
    """Opt-ins straight from GHL's form submissions, per group: by day, by funnel and by ad.

    A lead is a PERSON, counted once per group, on the Central day and in the funnel of their first
    counted opt-in (for the Lead Magnet, their first "Opt in 2"). Nine people opted in twice to DTC
    on day one (195 submissions, 186 people), and a double opt-in is one registrant for the
    challenge. Days, funnels and ads therefore all add up to the group's total. Someone in both
    groups counts once in each; two people were on day one.

    The ad is the `h_ad_id` Meta fills into the funnel link, which GHL records with the submission
    (96% of day-one DTC opt-ins and 92% of Opt in 2s carried one). An opt-in with no ad id of its
    group counts in the day and the funnel but sits in no campaign or ad row, and the page says how
    many.

    Only aggregate counts leave this function: no names, emails or phones reach the snapshot or the
    public page. Returns {group: counts}, or None if any read failed: half a count is worse than
    the fallback.
    """
    key = ghl_key()
    if not key:
        print("warning: no GHL key (GHL_API_KEY or the PBI key file); leads fall back to Hyros and Meta", file=sys.stderr)
        return None
    where = {fid: (g, page) for g, cfg in GHL_GROUPS.items() for fid, page, _ in cfg["funnels"]}
    until = (datetime.strptime(today, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    subs = {g: {} for g in GHL_GROUPS}
    for form in sorted({f for cfg in GHL_GROUPS.values() for _, _, f in cfg["funnels"]}):
        page_no = 1
        while True:
            data = ghl_get("/forms/submissions", {"locationId": GHL_LOCATION, "formId": form, "limit": "100",
                                                  "page": str(page_no), "startAt": GHL_SINCE, "endAt": until}, key)
            if data is None or not isinstance(data.get("submissions"), list):
                return None
            for s in data["submissions"]:
                others = s.get("others") or {}
                event = others.get("funneEventData") or {}  # sic: GHL's spelling
                if event.get("funnel_id") not in where or not s.get("createdAt"):
                    continue
                g, page = where[event["funnel_id"]]
                if GHL_GROUPS[g]["step"] and event.get("funnel_step_id") != GHL_GROUPS[g]["step"]:
                    continue
                params = (others.get("eventData") or {}).get("url_params") or {}
                subs[g][s["id"]] = {"who": s.get("contactId") or s["id"], "at": s["createdAt"],
                                    "page": page, "ad": str(params.get("h_ad_id") or "")}
            if not (data.get("meta") or {}).get("nextPage"):
                break
            page_no += 1

    window = []
    d = datetime.strptime(START, "%Y-%m-%d")
    while d.strftime("%Y-%m-%d") <= today:
        window.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    out = {}
    for g, cfg in GHL_GROUPS.items():
        first, raw = {}, {}
        for s in sorted(subs[g].values(), key=lambda s: s["at"]):
            day = datetime.fromisoformat(s["at"].replace("Z", "+00:00")).astimezone(TZ).strftime("%Y-%m-%d")
            if START <= day <= today:
                raw[day] = raw.get(day, 0) + 1
            if s["who"] not in first:
                first[s["who"]] = {**s, "day": day}
        # Every day of the window is present, zeros included: the page reads a missing day as "no
        # GHL read" and would put Meta's scaled count in its place.
        days, funnels, ads = {day: 0 for day in window}, {}, {}
        for p in first.values():
            if not START <= p["day"] <= today:
                continue  # first seen before the campaigns ran: the team's own test opt-ins
            days[p["day"]] += 1
            by_day = funnels.setdefault(p["page"], {})
            by_day[p["day"]] = by_day.get(p["day"], 0) + 1
            ad = p["ad"] if p["ad"].isdigit() else ""  # Meta sometimes passes {{ad.id}} through unfilled
            ads[ad] = ads.get(ad, 0) + 1
        out[g] = {
            "source": "GHL",
            "group": g,
            "model": cfg["model"],
            "label": cfg["label"],
            "pulled_at": datetime.now(TZ).isoformat(timespec="seconds"),
            "days": days,
            "submissions": raw,
            "funnels": funnels,
            "pages": [page for _, page, _ in cfg["funnels"]],
            "ads": ads,  # "" = no ad id; settled against the Meta ad list in credit_campaigns()
        }
    return out


def credit_campaigns(ghl, ads, rows):
    """Put each GHL opt-in's ad into its campaign; anything else is counted as unattributed."""
    camp_of_ad = {a["id"]: a["campaign"] for a in ads}
    id_of_name = {r["name"]: r["id"] for r in rows}
    for g, src in ghl.items():
        # Every campaign of the group gets a row, zero included, for the same reason as the zero days.
        src["campaigns"] = {r["id"]: 0 for r in rows if group_of(r["name"]) == g}
        src["no_ad"], kept = 0, {}
        for ad, n in src.pop("ads").items():
            name = camp_of_ad.get(ad)
            if name and group_of(name) == g and name in id_of_name:
                cid = id_of_name[name]
                src["campaigns"][cid] = src["campaigns"].get(cid, 0) + n
                kept[ad] = n
            else:
                src["no_ad"] += n  # no ad id, or an ad from the other group's campaigns
        src["ads"] = kept
    return ghl


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
    if _extra_campaign_filter():
        for r in paged(f"https://graph.facebook.com/v21.0/{ACCOUNT}/insights", {
            "level": "ad",
            "fields": "ad_id,spend,inline_link_clicks",
            "time_range": json.dumps({"since": since, "until": today}),
            "time_increment": "1",
            "filtering": json.dumps(_extra_campaign_filter()),
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
        "fields": "campaign_id,campaign_name,spend,actions,action_values",
        "time_range": json.dumps({"since": START, "until": today}),
        "time_increment": "1",
        "filtering": json.dumps([{"field": "campaign.name", "operator": "CONTAIN", "value": NAME_FILTER}]),
        "limit": "500",
        "access_token": token(),
    }
    insights_url = f"https://graph.facebook.com/v21.0/{ACCOUNT}/insights"
    rows = []
    url = insights_url
    while url:
        data = graph(url, params)
        for r in data["data"]:
            acts = {a["action_type"]: float(a["value"]) for a in r.get("actions", [])}
            vals = {a["action_type"]: float(a["value"]) for a in r.get("action_values", [])}
            rows.append({
                "date": r["date_start"],
                "id": r["campaign_id"],
                "name": r["campaign_name"],
                "spend": float(r["spend"]),
                "link_clicks": acts.get("link_click", 0.0),
                "leads": acts.get("lead", 0.0),
                # The funnels' paid step ($17 a purchase on day one) as the pixel reports it: Meta's
                # number, labelled as such in daily.csv; GHL's orders need a payments scope the
                # token does not have (401 on 2026-09-17).
                "purchases": acts.get("offsite_conversion.fb_pixel_purchase", 0.0),
                "revenue": vals.get("offsite_conversion.fb_pixel_purchase", 0.0),
            })
        url = data.get("paging", {}).get("next")
        params = {}  # the next URL carries every parameter
    # Campaigns not matched by NAME_FILTER (see EXTRA_CAMPAIGNS)
    if EXTRA_CAMPAIGNS:
        for r in paged(insights_url, {
            "level": "campaign",
            "fields": "campaign_id,campaign_name,spend,actions,action_values",
            "time_range": json.dumps({"since": START, "until": today}),
            "time_increment": "1",
            "filtering": json.dumps([{"field": "campaign.id", "operator": "IN",
                                      "value": list(EXTRA_CAMPAIGNS)}]),
            "limit": "500",
            "access_token": token(),
        }):
            acts = {a["action_type"]: float(a["value"]) for a in r.get("actions", [])}
            vals = {a["action_type"]: float(a["value"]) for a in r.get("action_values", [])}
            rows.append({
                "date": r["date_start"],
                "id": r["campaign_id"],
                "name": r["campaign_name"],
                "spend": float(r["spend"]),
                "link_clicks": acts.get("link_click", 0.0),
                "leads": acts.get("lead", 0.0),
                "purchases": acts.get("offsite_conversion.fb_pixel_purchase", 0.0),
                "revenue": vals.get("offsite_conversion.fb_pixel_purchase", 0.0),
            })
    # Leads: GHL's own opt-ins for both groups. If the GHL read fails, DTC falls back to Hyros and the
    # Lead Magnet to Meta scaled to GHL, so the page never goes blank.
    ghl = pull_ghl(today)
    hyros = None if ghl else pull_hyros(today, rows)
    ads, creatives, thumbs, (since, ad_days) = pull_ads(today, full_listing, ghl)
    if ghl:
        credit_campaigns(ghl, ads, rows)
    url_days = sorted(published_url_days(since) + by_page(ad_days, creatives),
                      key=lambda t: (t["date"], t["page"]))
    return {"source": "snapshot", "pulled_at": datetime.now(TZ).isoformat(timespec="seconds"), "rows": rows,
            "ads": ads, "creatives": creatives, "thumbs": thumbs, "hyros": hyros,
            "leadsrc": ghl or ({HYROS_GROUP: hyros} if hyros else None),
            "url_days": url_days, "url_pulled_from": since,
            "extraGroups": {name: g for g, name in EXTRA_CAMPAIGNS.values()}}


DAILY_COLUMNS = [
    "Date", "Status", "Leads", "Spend ($)", "Link clicks", "Conv. rate (%)", "Cost per lead ($)",
    "Cost per link click ($)", "Purchases (Meta pixel)", "Revenue (Meta pixel, $)", "ROAS (Meta pixel)",
    "Lead Magnet leads", "DTC leads", "Lead Magnet spend ($)", "DTC spend ($)", "Meta Lead event", "Leads source",
]


def daily_csv(snap):
    """One row per Central day since START plus a Total row: both groups combined, split beside it.

    Phil, 2026-09-17: a spreadsheet with the combined leads, revenue, spend, link clicks and
    conversion rate each day. The Pages site publishes this file and a Google Sheet imports it
    (IMPORTDATA), so it keeps itself current. Leads follow the page exactly: GHL's own count per
    group when the pull read it, else the same fallbacks (Hyros for DTC, Meta scaled to GHL).
    Revenue is Meta's pixel Purchase value and says so in its column name. Plain numbers only, no
    currency or percent signs, so the Sheet reads every cell as a number.
    """
    src = snap.get("leadsrc") or {}
    today = snap["pulled_at"][:10]

    def leads(g, day, rows):
        s = src.get(g)
        if s and day in s.get("days", {}):
            return float(s["days"][day]), "GHL" if s.get("source") == "GHL" else "Hyros"
        return sum(r["leads"] for r in rows) * LEAD_FACTOR.get(g, 1), f"Meta x {round(LEAD_FACTOR.get(g, 1) * 100)}%"

    def line(label, status, rows, day_list):
        t = {"spend": 0.0, "clicks": 0.0, "purchases": 0.0, "revenue": 0.0, "meta": 0.0}
        by = {"lm": [0.0, 0.0], "dtc": [0.0, 0.0]}   # [leads, spend]
        how = set()
        for g in by:
            grp = [r for r in rows if group_of(r["name"]) == g]
            by[g][1] = sum(r["spend"] for r in grp)
            for day in day_list:
                n, h = leads(g, day, [r for r in grp if r["date"] == day])
                by[g][0] += n
                how.add(("Lead Magnet" if g == "lm" else "DTC") + ": " + h)
        for r in rows:
            if group_of(r["name"]):
                t["spend"] += r["spend"]; t["clicks"] += r["link_clicks"]; t["meta"] += r["leads"]
                t["purchases"] += r.get("purchases", 0.0); t["revenue"] += r.get("revenue", 0.0)
        lm, dtc = round(by["lm"][0]), round(by["dtc"][0])
        total = lm + dtc
        return [label, status, total, f"{t['spend']:.2f}", round(t["clicks"]),
                f"{100 * total / t['clicks']:.2f}" if t["clicks"] else "",
                f"{t['spend'] / total:.2f}" if total else "",
                f"{t['spend'] / t['clicks']:.2f}" if t["clicks"] else "",
                round(t["purchases"]), f"{t['revenue']:.2f}",
                f"{t['revenue'] / t['spend']:.2f}" if t["spend"] else "",
                lm, dtc, f"{by['lm'][1]:.2f}", f"{by['dtc'][1]:.2f}", round(t["meta"]),
                "; ".join(sorted(how))]

    days = sorted({r["date"] for r in snap["rows"] if START <= r["date"] <= today} | {today})
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(DAILY_COLUMNS)
    for day in days:
        w.writerow(line(day, "partial" if day == today else "", [r for r in snap["rows"] if r["date"] == day], [day]))
    w.writerow(line("Total", "through " + today, [r for r in snap["rows"] if START <= r["date"] <= today], days))
    return out.getvalue()


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
    daily = daily_csv(snap)
    (HERE / "data/daily.csv").write_text(daily)
    html = build(snap)
    (HERE / "dashboard.html").write_text(html)
    if args.site:
        site = Path(args.site)
        site.mkdir(parents=True, exist_ok=True)
        cut = html.index("</style>") + len("</style>")  # title, meta, fonts and CSS belong in <head>
        (site / "index.html").write_text(SKELETON.format(head=html[:cut], body=html[cut:].lstrip()))
        (site / "url_days.json").write_text(json.dumps(snap["url_days"], separators=(",", ":")))
        # the next pull's store of video ids (published_creatives); the page itself carries the same map
        (site / "creatives.json").write_text(json.dumps(snap["creatives"], separators=(",", ":")))
        if snap.get("hyros"):
            (site / "hyros.json").write_text(json.dumps(snap["hyros"], separators=(",", ":")))
        (site / "daily.csv").write_text(daily)   # the Google Sheet's feed (IMPORTDATA)
        (site / "version.json").write_text(json.dumps({"pulled_at": snap["pulled_at"]}))
        (site / "robots.txt").write_text(ROBOTS)

    spend = sum(r["spend"] for r in snap["rows"])
    leads = sum(r["leads"] for r in snap["rows"])
    print(f"{len(snap['rows'])} campaign-day rows, ${spend:,.2f} spent, {leads:.0f} Meta leads, pulled {snap['pulled_at']}")
    print(f"{len(snap['ads'])} ads with delivery, {len(snap['creatives'])} ads mapped to a format, {len(snap['thumbs'])} previews baked")
    spent = [snap["creatives"][a["id"]] for a in snap["ads"] if a["spend"] > 0 and a["id"] in snap["creatives"]]
    print(f"{len({creative_key(c) for c in spent if creative_key(c)})} distinct creatives behind {len(spent)} spending ads; "
          f"{sum(1 for c in spent if not creative_key(c))} with no image hash or video id rank on their own")
    for gh in (snap.get("leadsrc") or {}).values():
        if gh.get("source") != "GHL":
            continue
        print(f"GHL {gh['group'].upper()} ({gh['model']}): {sum(gh['days'].values())} people from "
              f"{sum(gh['submissions'].values())} opt-ins over {len(gh['days'])} days; "
              + ", ".join(f"{p} {sum(gh['funnels'].get(p, {}).values())}" for p in gh["pages"])
              + f"; {sum(gh['campaigns'].values())} credited to a campaign, {gh['no_ad']} with no ad of the group")
    hy = snap.get("hyros")
    if hy:
        print(f"Hyros ({hy['group'].upper()}, {hy['model']}): {sum(hy['days'].values()):.0f} leads over "
              f"{len(hy['days'])} days, {sum(hy['campaigns'].values()):.0f} over {len(hy['campaigns'])} campaigns")
    pages = sorted({r["page"] for r in snap["url_days"]})
    days = sorted({r["date"] for r in snap["url_days"]})
    unmapped = sum(r["clicks"] for r in snap["url_days"] if r["page"] == "?")
    print(f"{len(pages)} landing pages over {len(days)} days ({days[0] if days else '-'} to {days[-1] if days else '-'}, "
          f"pulled from {snap['url_pulled_from']}), {unmapped:.0f} link clicks on ads with no page")


if __name__ == "__main__":
    main()
