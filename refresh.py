#!/usr/bin/env python3
"""Pull the JOM4 September challenge campaigns from Meta and rebuild the dashboard.

    python3 refresh.py               # rebuild dashboard.html (the Claude artifact); republish it after
    python3 refresh.py --site _site  # also write the GitHub Pages site: index.html + version.json + robots.txt

The Claude artifact refreshes itself live through the viewer's Meta Ads connector; the baked
snapshot is only what shows before (or without) that read. The GitHub Pages copy has no
connector, so its GitHub Actions workflow runs this script every 30 minutes.
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


def graph(url, params):
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
        sys.exit(f"Meta error {status}: {err.get('message')}")
    sys.exit("Meta kept failing or throttling; try again in a few minutes.")


def token():
    return os.environ.get("FB_TOKEN") or TOKEN_FILE.read_text().strip()


def pull():
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
    return {"source": "snapshot", "pulled_at": datetime.now(TZ).isoformat(timespec="seconds"), "rows": rows}


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

    snap = pull()
    (HERE / "data").mkdir(exist_ok=True)
    (HERE / "data/snapshot.json").write_text(json.dumps(snap, indent=1))
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


if __name__ == "__main__":
    main()
