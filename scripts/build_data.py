#!/usr/bin/env python3
"""Create static, source-attributed Chicago air-quality data for GitHub Pages.

The City of Chicago's Open Air Chicago *daily* source is UTC-day aggregated.
The hourly source is used only for the latest-published-hour layer and short trends.
No DuckDB file, credentials, or user account is needed. Raw records are never committed.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "site" / "data"
DAILY_URL = "https://data.cityofchicago.org/resource/rtmx-vkjr.json"
HOURLY_URL = "https://data.cityofchicago.org/resource/di9s-96ws.json"
START_DATE = "2025-09-01"
PAGE_SIZE = 2500
DAILY_SELECT = "datasourceid,sensor_name,startofperiod,latitude,longitude,pm2_5concmass24hourmean_value,no2conc24hourmean_value"
HOURLY_SELECT = "datasourceid,startofperiod,pm2_5concmass1hourmean_value,no2conc1hourmean_value"


def client():
    retry = Retry(total=5, backoff_factor=1.5, status_forcelist=[429,500,502,503,504], allowed_methods=["GET"], respect_retry_after_header=True)
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4))
    session.headers.update({"User-Agent": "ChicagoAirExplorer/1.0 public-data-dashboard (GitHub Actions)", "Accept": "application/json"})
    token = os.getenv("SOCRATA_APP_TOKEN", "").strip()
    if token:
        session.headers["X-App-Token"] = token
    return session


def fetch_pages(session, url: str, *, where: str, select: str, order: str):
    """Page a stable ordered query. Fail the build rather than publish a partial response."""
    offset = 0
    while True:
        params = {"$where": where, "$select": select, "$order": order, "$limit": PAGE_SIZE, "$offset": offset}
        try:
            r = session.get(url, params=params, timeout=(15, 100))
            r.raise_for_status()
            page = r.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"Chicago API unavailable at offset {offset} for {url}: {exc}") from exc
        if not isinstance(page, list):
            raise RuntimeError(f"Unexpected API response for {url}: {repr(page)[:200]}")
        if not page:
            break
        yield from page
        offset += len(page)
        print(f"  received {offset:,} rows from {url.rsplit('/',1)[-1]}", flush=True)
        if len(page) < PAGE_SIZE:
            break


def number(value):
    if value is None or value == "":
        return None
    try:
        x = float(value)
        if not math.isfinite(x) or x < 0:
            return None
        return round(x, 3)
    except (ValueError, TypeError):
        return None


def coordinate(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (ValueError, TypeError):
        return None


def load_daily_cache(path: Path):
    if not path.exists():
        return {}, {}, None
    obj = json.loads(path.read_text())
    if obj.get("version") != 1:
        raise ValueError("Unsupported daily cache schema")
    days, sensors = obj["dates"], obj["sensors"]
    records = {}
    for i, si, pm, no in obj["rows"]:
        records[(days[i], sensors[si]["id"])] = (pm, no)
    return records, {s["id"]: {k:v for k,v in s.items() if k in ("id", "name", "lat", "lon", "coord_warning")} for s in sensors}, (max(days) if days else None)


def parse_day(row):
    day = str(row.get("startofperiod") or "")[:10]
    if len(day) != 10 or day[4] != "-" or day[7] != "-":
        return None
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return None
    return day


def process_daily(rows, records, metadata):
    seen = set()
    invalid = defaultdict(int)
    for r in rows:
        day = parse_day(r)
        sid = str(r.get("datasourceid") or "").strip()
        if not sid or not day:
            invalid["missing_sensor_or_day"] += 1
            continue
        key = (day, sid)
        if key in seen:
            raise RuntimeError(f"Duplicate sensor/UTC-day returned: {key}")
        seen.add(key)
        pm = number(r.get("pm2_5concmass24hourmean_value"))
        no = number(r.get("no2conc24hourmean_value"))
        records[key] = (pm, no)   # Corrected provider values replace matching saved values.
        old = metadata.get(sid, {"id": sid, "name": sid, "lat": None, "lon": None})
        name = str(r.get("sensor_name") or old.get("name") or sid).strip()
        lat, lon = coordinate(r.get("latitude")), coordinate(r.get("longitude"))
        if lat is not None and lon is not None and 41.4 < lat < 42.3 and -88.4 < lon < -87.2:
            if old.get("lat") is not None and (abs(lat-old["lat"]) > 0.008 or abs(lon-old["lon"]) > 0.012):
                old["coord_warning"] = True
            # Latest valid reported coordinates, not averaged coordinates.
            old["lat"], old["lon"] = lat, lon
        old["name"] = name
        metadata[sid] = old
        if pm is None:
            invalid["missing_or_invalid_pm25"] += 1
        if no is None:
            invalid["missing_or_invalid_no2"] += 1
    return dict(invalid)


def assemble_daily(records, metadata, generated):
    days = sorted(set(day for day, _ in records))
    sensors = sorted(metadata.values(), key=lambda s: (s.get("name") or "").casefold())
    dindex = {day:i for i,day in enumerate(days)}
    sindex = {s["id"]:i for i,s in enumerate(sensors)}
    output_rows = []
    sums = defaultdict(lambda: [0.,0.,0,0])
    counts = defaultdict(lambda: [0,0])
    for (day, sid), (pm, no) in sorted(records.items()):
        if sid not in sindex:
            continue
        output_rows.append([dindex[day], sindex[sid], pm, no])
        sums[day][0] += pm or 0
        sums[day][1] += no or 0
        if pm is not None:
            sums[day][2] += 1
            counts[sid][0] += 1
        if no is not None:
            sums[day][3] += 1
            counts[sid][1] += 1
    for sensor in sensors:
        sensor["days_pm"], sensor["days_no2"] = counts[sensor["id"]]
    network = []
    for day in days:
        p, n, pc, nc = sums[day]
        network.append([dindex[day], round(p/pc,3) if pc else None, round(n/nc,3) if nc else None, pc, nc])
    return {"version":1,"generated_at":generated,"source":DAILY_URL,
        "day_timezone":"UTC","units":{"pm25":"µg/m³","no2":"ppb"},
        "dates":days,"sensors":sensors,"rows":output_rows,"network":network}


def build_recent(session, sensor_ids, generated):
    # Fast metadata lookup for the newest *published* hour, not wall-clock time.
    params = {"$select":"startofperiod", "$order":"startofperiod DESC", "$limit":1}
    r = session.get(HOURLY_URL,params=params,timeout=(15,80))
    r.raise_for_status()
    data = r.json()
    if not data:
        return {"version":1,"generated_at":generated,"source":HOURLY_URL,"hours":[],"network":[],"map_hour":None,"map_rows":[]}
    newest = str(data[0]["startofperiod"])[:19]
    latest_dt = datetime.fromisoformat(newest.replace("Z",""))
    lower = (latest_dt - timedelta(hours=72)).strftime("%Y-%m-%dT%H:%M:%S")
    raw = list(fetch_pages(session, HOURLY_URL,where=f"startofperiod >= '{lower}'",select=HOURLY_SELECT,order="startofperiod ASC, datasourceid ASC"))
    seen = set()
    byhour = defaultdict(dict)
    for row in raw:
        sid = str(row.get("datasourceid") or "").strip()
        hour = str(row.get("startofperiod") or "")[:19]
        if not sid or not hour or sid not in sensor_ids:
            continue
        key = (hour,sid)
        if key in seen:
            raise RuntimeError(f"Duplicate hourly key: {key}")
        seen.add(key)
        byhour[hour][sid] = (number(row.get("pm2_5concmass1hourmean_value")),number(row.get("no2conc1hourmean_value")))
    hours = sorted(byhour)
    network = []
    for i,h in enumerate(hours):
        vals = list(byhour[h].values())
        p = [v[0] for v in vals if v[0] is not None]
        n = [v[1] for v in vals if v[1] is not None]
        network.append([i,round(sum(p)/len(p),3) if p else None,round(sum(n)/len(n),3) if n else None,len(p),len(n)])
    min_sensors = max(15, round(len(sensor_ids) * .15))
    # Never mix different hours on the latest-hour map. The newest hour with adequate
    # participation is chosen; an insufficient recent cohort is labeled honestly.
    map_hour = next((h for h in reversed(hours) if sum(1 for v in byhour[h].values() if v[0] is not None) >= min_sensors),None)
    map_rows = [[sid,*v] for sid,v in sorted(byhour[map_hour].items())] if map_hour else []
    return {"version":1,"generated_at":generated,"source":HOURLY_URL,
            "hours":hours,"network":network,"map_hour":map_hour,"map_rows":map_rows,"min_sensor_cohort":min_sensors}


def write_json(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":"),allow_nan=False),encoding="utf-8")
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily-only",action="store_true",help="Skip optional hourly fetch")
    ap.add_argument("--rebuild",action="store_true",help="Fetch all historical daily observations")
    args = ap.parse_args()
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    daily_path = DATA_DIR/"daily.json"
    records, metadata, last_day = load_daily_cache(daily_path)
    if args.rebuild:
        records, metadata, last_day = {}, {}, None
    start_day = max(START_DATE, (datetime.strptime(last_day,"%Y-%m-%d")-timedelta(days=21)).strftime("%Y-%m-%d")) if last_day else START_DATE
    session = client()
    print(f"Loading daily API from {start_day}; cached sensor-day records: {len(records):,}",flush=True)
    raw = list(fetch_pages(session,DAILY_URL,where=f"startofperiod >= '{start_day}T00:00:00'",select=DAILY_SELECT,order="startofperiod ASC, datasourceid ASC"))
    if not raw:
        raise RuntimeError("Daily API returned zero observations; keeping existing data unchanged")
    audit = process_daily(raw,records,metadata)
    daily = assemble_daily(records,metadata,generated)
    if not daily["rows"]:
        raise RuntimeError("No valid daily data; nothing to publish")
    # Daily result is safe to persist even if the recent hourly feed is unavailable.
    write_json(daily_path,daily)
    recent_path = DATA_DIR/"recent.json"
    hourly_error = None
    if not args.daily_only:
        try:
            recent = build_recent(session,set(metadata),generated)
            if recent["hours"]:
                write_json(recent_path,recent)
            else:
                hourly_error = "No recent hourly observations returned; kept previous hourly feed."
        except Exception as exc:
            hourly_error = str(exc)
            print(f"Hourly dataset not available: {hourly_error}; keeping last successful hourly artifact",file=sys.stderr)
    prior_recent = {}
    if recent_path.exists():
        try:
            prior_recent = json.loads(recent_path.read_text())
        except Exception:
            pass
    latest_hour = prior_recent.get("hours",[])[-1] if prior_recent.get("hours") else None
    manifest = {"version":1,"generated_at":generated,"daily_source":DAILY_URL,"hourly_source":HOURLY_URL,
                "latest_utc_day":daily["dates"][-1],"latest_utc_hour":latest_hour,
                "sensor_count":len(daily["sensors"]),"day_count":len(daily["dates"]),
                "daily_records":len(daily["rows"]),"hourly_refresh_error":hourly_error,
                "audit":audit,"notes":["Daily series are source-published UTC-day aggregates, not reconstructed Chicago-local days.","The last available hour may be delayed by the provider.","Coverage eligibility is not determined from daily aggregates alone."]}
    write_json(DATA_DIR/"manifest.json",manifest)
    print(f"Built {len(daily['rows']):,} sensor-days, {len(daily['sensors'])} sensors, latest UTC day {manifest['latest_utc_day']}, latest hour {latest_hour}")


if __name__=="__main__":
    main()
