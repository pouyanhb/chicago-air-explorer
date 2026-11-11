#!/usr/bin/env python3
"""Incremental update of the archived-hourly-derived Chicago Air Explorer dataset.

Requires a prior one-time export from air.db. Fetches a bounded number of full UTC
calendar days, computes exactly the same 18-valid-hour/sensor/pollutant daily means
as the initial exporter, and preserves older days without downloading them again.
Data source is public City hourly Open Air Chicago data (di9s-96ws).
"""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import json
import math
import sys

from build_data import (
    DATA_DIR, HOURLY_URL, assemble_daily, build_recent, client,
    fetch_pages, load_daily_cache, write_json,
)

PAGE_FIELDS = "datasourceid,sensor_name,startofperiod,latitude,longitude,pm2_5concmass1hourmean_value,no2conc1hourmean_value"
MAX_DAYS = 7  # Limit the work in each scheduled run.
BACKTRACK_DAYS = 2
MIN_HOURS = 18  # Full UTC calendar day has 24 expected hours.


def raw_number(value):
    """Keep source precision until averaging, consistent with DuckDB exporter."""
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def day_data(rows, day):
    """Return {sensor_id: (pm25,no2,latestname,lat,lon)} from one UTC day."""
    byid = defaultdict(lambda: {"pm": [], "no": [], "name": None, "lat": None, "lon": None})
    seen = set()
    for r in rows:
        sid = str(r.get("datasourceid") or "").strip()
        hour = str(r.get("startofperiod") or "")[:19]
        if not sid or not hour or hour[:10] != day.isoformat():
            continue
        key = (sid, hour)
        if key in seen:
            raise RuntimeError(f"Provider duplicate hourly key {key}")
        seen.add(key)
        d = byid[sid]
        p = raw_number(r.get("pm2_5concmass1hourmean_value"))
        n = raw_number(r.get("no2conc1hourmean_value"))
        if p is not None:
            d["pm"].append(p)
        if n is not None:
            d["no"].append(n)
        name = r.get("sensor_name")
        if name:
            d["name"] = str(name).strip()
        for field in ("latitude", "longitude"):
            try:
                value = float(r.get(field))
                if value == value:
                    d["lat" if field == "latitude" else "lon"] = value
            except (TypeError, ValueError):
                pass
    out = {}
    for sid, d in byid.items():
        pm = round(sum(d["pm"])/len(d["pm"]),3) if len(d["pm"]) >= MIN_HOURS else None
        no = round(sum(d["no"])/len(d["no"]),3) if len(d["no"]) >= MIN_HOURS else None
        out[sid] = (pm, no, d["name"], d["lat"], d["lon"])
    return out


def save_if_changed(path, obj):
    """Avoid a fresh large Git blob if measurements and metadata have not changed."""
    if path.exists():
        try:
            old = json.loads(path.read_text())
            candidate = dict(obj)
            candidate["generated_at"] = old.get("generated_at")
            if candidate == old:
                print(f"No underlying changes in {path.name}; keeping previous file")
                return False
        except (ValueError, OSError):
            pass
    write_json(path, obj)
    return True


def refresh():
    daily_path = DATA_DIR / "daily.json"
    if not daily_path.exists():
        print("No historical seed yet. Run the read-only DuckDB exporter, then upload its JSON files to site/data/.")
        return
    records, metadata, latest = load_daily_cache(daily_path)
    if not latest:
        raise RuntimeError("Seed has no eligible days. Not refreshing.")
    now = datetime.now(timezone.utc)
    last_completed = now.date() - timedelta(days=1)
    old_manifest_path = DATA_DIR / "manifest.json"
    old_manifest = json.loads(old_manifest_path.read_text()) if old_manifest_path.exists() else {}
    scanned_value = old_manifest.get("scanned_through_utc_day")
    prior_scanned = date.fromisoformat(scanned_value) if scanned_value else None
    if prior_scanned and prior_scanned >= last_completed:
        # After catching up, systematically revisit a recent 14-day window.
        start = last_completed - timedelta(days=13)
    elif prior_scanned:
        # Move a bounded window forward, revisiting two days for late revisions.
        start = prior_scanned - timedelta(days=BACKTRACK_DAYS)
    else:
        start = date.fromisoformat(latest) - timedelta(days=BACKTRACK_DAYS)
    start = max(start, date(2025,9,1))
    end = min(last_completed, start + timedelta(days=MAX_DAYS-1))
    if end < start:
        print("No completed UTC days to refresh yet.")
        return

    print(f"Hourly incremental update: {start} through {end}; existing daily records: {len(records):,}",flush=True)
    session = client()
    attempted, success, failure = 0, 0, None
    scanned_through = prior_scanned
    day = start
    while day <= end:
        upper = day + timedelta(days=1)
        where = f"startofperiod >= '{day.isoformat()}T00:00:00' AND startofperiod < '{upper.isoformat()}T00:00:00'"
        try:
            fetched = list(fetch_pages(session, HOURLY_URL, where=where, select=PAGE_FIELDS,
                                       order="startofperiod ASC, datasourceid ASC"))
            per_sensor = day_data(fetched, day)
        except Exception as e:
            failure = f"City hourly API failed on {day.isoformat()}: {e}"
            print("::warning::" + failure, file=sys.stderr)
            break
        attempted += len(fetched)
        for sid, (pm, no, name, lat, lon) in per_sensor.items():
            key = (day.isoformat(), sid)
            if pm is None and no is None:
                records.pop(key, None)
            else:
                records[key] = (pm, no)
            old = metadata.get(sid, {"id":sid,"name":sid,"lat":None,"lon":None})
            if name:
                old["name"] = name
            if lat is not None and lon is not None and 41.4 < lat < 42.3 and -88.4 < lon < -87.2:
                if old.get("lat") is not None and (abs(lat-old["lat"])>.008 or abs(lon-old["lon"])>.012):
                    old["coord_warning"] = True
                old["lat"], old["lon"] = lat, lon
            metadata[sid] = old
        success += 1
        scanned_through = day
        print(f"  {day}: {len(fetched):,} hourly rows; {len(per_sensor)} reporting sensors", flush=True)
        day = upper

    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if success:
        daily = assemble_daily(records, metadata, generated)
        daily["source"] = "Open Air Chicago hourly observations; UTC-day means with >=18 valid hours"
        daily["aggregation"] = "UTC-day mean of >=18 valid hourly values per sensor/pollutant"
        daily["units"] = {"pm25":"µg/m³", "no2":"ppb"}
        daily["day_timezone"] = "UTC"
        save_if_changed(daily_path, daily)
    else:
        daily = json.loads(daily_path.read_text())

    recent_path = DATA_DIR / "recent.json"
    hourly_error = None
    try:
        recent = build_recent(session, set(metadata), generated)
        if recent["hours"]:
            save_if_changed(recent_path, recent)
        else:
            hourly_error = "No recent hourly rows returned; retained previous snapshot."
    except Exception as e:
        hourly_error = str(e)
        print("::warning::Recent-hour map retrieval failed: " + hourly_error, file=sys.stderr)

    prior_recent = {}
    if recent_path.exists():
        try:
            prior_recent = json.loads(recent_path.read_text())
        except (ValueError, OSError):
            pass
    hours = prior_recent.get("hours") or []
    notes = [
        "UTC-day means calculated from City hourly sensor observations, not City published daily aggregates.",
        "Each pollutant requires at least 18 valid sensor-hours out of 24; no missing values are imputed.",
        "Data publication can lag by days; this is not a live warning service.",
    ]
    manifest = {"version":1,"generated_at":generated,
                "daily_source":HOURLY_URL,"hourly_source":HOURLY_URL,
                "latest_utc_day":daily["dates"][-1],
                "latest_utc_hour":hours[-1] if hours else None,
                "sensor_count":len(daily["sensors"]),"day_count":len(daily["dates"]),
                "daily_records":len(daily["rows"]),
                "hourly_refresh_error":hourly_error,
                "daily_refresh_warning":failure,
                "scanned_through_utc_day":scanned_through.isoformat() if scanned_through else None,
                "audit":{"hourly_rows_fetched":attempted,"full_days_successful":success},
                "notes":notes}
    write_json(DATA_DIR/"manifest.json",manifest)
    print(f"Refreshed {success} UTC day(s); latest eligible day: {manifest['latest_utc_day']}; {len(daily['rows']):,} sensor-day records",flush=True)


if __name__ == "__main__":
    refresh()