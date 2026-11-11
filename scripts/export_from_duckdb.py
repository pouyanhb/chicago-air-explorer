#!/usr/bin/env python3
"""One-time, read-only export of Chicago air-quality summaries from air.db.

Creates three compact JSON files for Chicago Air Explorer. Does not modify air.db.
Source timestamps are assumed to represent UTC, as in the existing Colab notebook.
Full UTC days require >=18 distinct valid hourly readings per pollutant.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path


def val(value):
    try:
        v = float(value)
        return round(v, 3) if math.isfinite(v) and v >= 0 else None
    except (TypeError, ValueError):
        return None


def export(db_path, out_dir):
    import duckdb
    db_path = Path(db_path)
    out_dir = Path(out_dir)
    if not db_path.is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        names = {x[1] for x in con.execute("PRAGMA table_info('raw_hourly')").fetchall()}
        required = {"datasourceid", "startofperiod", "sensor_name", "latitude", "longitude",
                    "pm2_5concmass1hourmean_value", "no2conc1hourmean_value"}
        if not required.issubset(names):
            raise ValueError(f"raw_hourly is missing columns: {sorted(required-names)}")
        print("Checking sensor-hour uniqueness (database is opened read-only)...", flush=True)
        duplicates = con.execute("""
            SELECT COUNT(*) FROM (
                SELECT datasourceid, TRY_CAST(startofperiod AS TIMESTAMP) AS ts
                FROM raw_hourly
                WHERE datasourceid IS NOT NULL AND TRY_CAST(startofperiod AS TIMESTAMP) IS NOT NULL
                GROUP BY 1,2 HAVING COUNT(*) > 1
            )
        """).fetchone()[0]
        if duplicates:
            raise ValueError(f"Found {duplicates:,} duplicated sensor-hour keys. Resolve them before exporting.")
        invalid_ids = con.execute("""
            SELECT COUNT(*) FROM raw_hourly
            WHERE datasourceid IS NULL OR TRIM(CAST(datasourceid AS VARCHAR)) = ''
               OR TRY_CAST(startofperiod AS TIMESTAMP) IS NULL
        """).fetchone()[0]
        if invalid_ids:
            print(f"Note: {invalid_ids:,} records with missing IDs/timestamps excluded")

        meta_rows = con.execute("""
            SELECT CAST(datasourceid AS VARCHAR) AS id,
                   ARG_MAX(sensor_name, TRY_CAST(startofperiod AS TIMESTAMP)) AS name,
                   ARG_MAX(TRY_CAST(latitude AS DOUBLE), TRY_CAST(startofperiod AS TIMESTAMP)) AS lat,
                   ARG_MAX(TRY_CAST(longitude AS DOUBLE), TRY_CAST(startofperiod AS TIMESTAMP)) AS lon,
                   MIN(TRY_CAST(latitude AS DOUBLE)) AS min_lat,
                   MAX(TRY_CAST(latitude AS DOUBLE)) AS max_lat,
                   MIN(TRY_CAST(longitude AS DOUBLE)) AS min_lon,
                   MAX(TRY_CAST(longitude AS DOUBLE)) AS max_lon
            FROM raw_hourly
            WHERE datasourceid IS NOT NULL
            GROUP BY 1
        """).fetchall()
        sensors = []
        for sid, name, lat, lon, minlat, maxlat, minlon, maxlon in meta_rows:
            lat = float(lat) if lat is not None and math.isfinite(float(lat)) and 41.4 < float(lat) < 42.3 else None
            lon = float(lon) if lon is not None and math.isfinite(float(lon)) and -88.4 < float(lon) < -87.2 else None
            coord_warning = bool(minlat is not None and maxlat is not None and abs(maxlat-minlat) > .008 or
                                 minlon is not None and maxlon is not None and abs(maxlon-minlon) > .012)
            sensors.append({"id": sid, "name": str(name or sid), "lat": lat, "lon": lon,
                            "coord_warning": coord_warning, "days_pm": 0, "days_no2": 0})
        sensors.sort(key=lambda x: (x["name"].casefold(), x["id"]))
        id_to_index = {s["id"]: i for i, s in enumerate(sensors)}
        print(f"Found {len(sensors)} sensor IDs. Calculating full UTC-day averages...", flush=True)
        cutoff = datetime.now(timezone.utc).date().isoformat()
        # UTC-day average for each pollutant only when at least 18 valid hourly readings.
        # No interpolation, and no filling of missing NO2 with zero.
        sql = """
        WITH hourly AS (
          SELECT CAST(datasourceid AS VARCHAR) AS sid,
                 CAST(TRY_CAST(startofperiod AS TIMESTAMP) AS DATE) AS day,
                 CASE WHEN ISFINITE(TRY_CAST(pm2_5concmass1hourmean_value AS DOUBLE))
                         AND TRY_CAST(pm2_5concmass1hourmean_value AS DOUBLE) >= 0
                      THEN TRY_CAST(pm2_5concmass1hourmean_value AS DOUBLE) ELSE NULL END AS pm,
                 CASE WHEN ISFINITE(TRY_CAST(no2conc1hourmean_value AS DOUBLE))
                         AND TRY_CAST(no2conc1hourmean_value AS DOUBLE) >= 0
                      THEN TRY_CAST(no2conc1hourmean_value AS DOUBLE) ELSE NULL END AS no
          FROM raw_hourly
          WHERE datasourceid IS NOT NULL
            AND TRY_CAST(startofperiod AS TIMESTAMP) IS NOT NULL
            AND CAST(TRY_CAST(startofperiod AS TIMESTAMP) AS DATE) < CAST(? AS DATE)
        )
        SELECT day, sid,
               CASE WHEN COUNT(pm) >= 18 THEN AVG(pm) ELSE NULL END AS pm,
               CASE WHEN COUNT(no) >= 18 THEN AVG(no) ELSE NULL END AS no,
               COUNT(pm) AS pm_hours, COUNT(no) AS no_hours
        FROM hourly
        GROUP BY 1, 2
        HAVING COUNT(pm) >= 18 OR COUNT(no) >= 18
        ORDER BY 1, 2
        """
        items = con.execute(sql, [cutoff]).fetchall()
        days = sorted({str(r[0]) for r in items})
        di = {d: i for i, d in enumerate(days)}
        rows, accum = [], defaultdict(lambda: [0.0, 0.0, 0, 0])
        for date, sid, pm, no, pmh, noh in items:
            day = str(date)
            if sid not in id_to_index:
                continue
            pm, no = val(pm), val(no)
            rows.append([di[day], id_to_index[sid], pm, no])
            a = accum[day]
            if pm is not None:
                a[0] += pm; a[2] += 1; sensors[id_to_index[sid]]["days_pm"] += 1
            if no is not None:
                a[1] += no; a[3] += 1; sensors[id_to_index[sid]]["days_no2"] += 1
        network = [[di[d], round(accum[d][0]/accum[d][2],3) if accum[d][2] else None,
                    round(accum[d][1]/accum[d][3],3) if accum[d][3] else None,
                    accum[d][2], accum[d][3]] for d in days]
        if not rows:
            raise ValueError("No eligible sensor-days. Inspect hourly data validity and thresholds.")
        generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
        daily = {"version": 1, "generated_at": generated, "source": "Open Air Chicago hourly archive in air.db",
                 "aggregation": "UTC-day mean of >=18 valid hourly records per sensor and pollutant",
                 "day_timezone": "UTC", "units": {"pm25":"µg/m³", "no2":"ppb"},
                 "dates": days, "sensors": sensors, "rows": rows, "network": network}

        max_hour = con.execute("""
            SELECT MAX(TRY_CAST(startofperiod AS TIMESTAMP)) FROM raw_hourly
        """).fetchone()[0]
        earliest = max_hour - timedelta(hours=72)
        recent_raw = con.execute("""
            SELECT TRY_CAST(startofperiod AS TIMESTAMP) AS hour,
                   CAST(datasourceid AS VARCHAR) AS sid,
                   TRY_CAST(pm2_5concmass1hourmean_value AS DOUBLE) AS pm,
                   TRY_CAST(no2conc1hourmean_value AS DOUBLE) AS no
            FROM raw_hourly
            WHERE datasourceid IS NOT NULL
              AND TRY_CAST(startofperiod AS TIMESTAMP) > ?
              AND TRY_CAST(startofperiod AS TIMESTAMP) <= ?
            ORDER BY 1,2
        """, [earliest, max_hour]).fetchall()
        byhour = defaultdict(dict)
        for hour, sid, pm, no in recent_raw:
            if sid in id_to_index:
                byhour[hour.isoformat(timespec="seconds")][sid] = (val(pm), val(no))
        hours = sorted(byhour)
        hnet = []
        for i, hour in enumerate(hours):
            v = list(byhour[hour].values())
            p = [x[0] for x in v if x[0] is not None]
            n = [x[1] for x in v if x[1] is not None]
            hnet.append([i, round(sum(p)/len(p),3) if p else None,
                         round(sum(n)/len(n),3) if n else None, len(p),len(n)])
        min_cohort = max(15,round(len(sensors)*.15))
        map_hour = next((h for h in reversed(hours)
                         if sum(x[0] is not None for x in byhour[h].values()) >= min_cohort),None)
        recent = {"version":1, "generated_at":generated,
                  "source":"Open Air Chicago hourly archive in air.db", "hours":hours,
                  "network":hnet, "map_hour":map_hour,
                  "map_rows":[[sid, *v] for sid, v in sorted(byhour[map_hour].items())] if map_hour else [],
                  "min_sensor_cohort":min_cohort}
        manifest = {"version":1,"generated_at":generated,
                    "daily_source":"Local archive: Open Air Chicago hourly API (di9s-96ws)",
                    "hourly_source":"Local archive: Open Air Chicago hourly API (di9s-96ws)",
                    "latest_utc_day":days[-1], "latest_utc_hour":hours[-1] if hours else None,
                    "sensor_count":len(sensors),"day_count":len(days),"daily_records":len(rows),
                    "hourly_refresh_error":None,
                    "audit":{"source_invalid_keys":int(invalid_ids), "duplicate_sensor_hours":0},
                    "notes":["UTC-day means derived from hourly archive; each pollutant needs >=18 distinct valid sensor-hours per full UTC day.",
                             "No missing values imputed; database remains unchanged.",
                             "Publication delays and archive update date may mean recent days are absent."]}
        for filename, obj in [("daily.json",daily),("recent.json",recent),("manifest.json",manifest)]:
            target = out_dir/filename
            target.write_text(json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
            print(f"Saved {filename}: {target.stat().st_size/1024/1024:.2f} MB")
        print(f"Exported {len(rows):,} eligible sensor-days; {len(days)} UTC dates; latest stored hour {max_hour}")
        print("Review measurement units and timestamps before publishing as final scientific results.")
    finally:
        con.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to existing air.db")
    ap.add_argument("--out", default="site_data_export", help="Output directory for public JSON files")
    args = ap.parse_args()
    export(args.db,args.out)