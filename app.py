import hashlib
import html
import json
import random
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components


POOL_SHORT = (
    "I successfully completed all assigned tasks and met the primary project milestones. "
    "The team collaborated effectively to resolve minor issues and ensure smooth progress. "
    "All deliverables were submitted on time with high quality standards maintained throughout. "
    "I conducted thorough testing and identified several edge cases that were promptly addressed. "
    "The sprint retrospective highlighted key areas for improvement in the next development cycle. "
    "Cross-functional coordination helped reduce bottlenecks and improved overall delivery speed. "
    "I updated the project documentation to reflect the latest changes in system architecture."
)

POOL_MIDDLE = (
    "This week, I focused on completing several key tasks and ensuring the project remains on schedule. "
    "I successfully finalized the initial research phase and shared findings with the stakeholders. "
    "The development team resolved critical blockers and improved system performance significantly. "
    "Regular sync meetings helped align priorities and address any dependencies across teams. "
    "I reviewed the codebase and refactored several modules to improve maintainability and readability. "
    "Load testing was performed and the results showed the system can handle peak traffic effectively. "
    "The QA team completed regression testing and signed off on the latest release candidate. "
    "I coordinated with the DevOps team to streamline the CI/CD pipeline and reduce build times. "
    "Feature flags were implemented to allow gradual rollout of the new functionality to users."
)

POOL_LONG = (
    "This report summarizes the progress and key activities completed during the current period. "
    "The primary focus has been on advancing core project objectives while ensuring all tasks align "
    "with the established timeline and quality benchmarks set by the organization. "
    "Several technical challenges were identified and resolved through cross-functional collaboration. "
    "The infrastructure team completed the migration to the new cloud environment with minimal downtime. "
    "Performance monitoring revealed significant improvements in response time and system throughput. "
    "Security audits were conducted and all identified vulnerabilities were patched promptly. "
    "Documentation was updated to reflect the latest architectural changes and deployment procedures. "
    "The database optimization initiative resulted in a 40 percent reduction in query execution time. "
    "API rate limiting was implemented to protect backend services from unexpected traffic spikes. "
    "The onboarding process for new team members was streamlined with updated guides and tutorials. "
    "Automated monitoring alerts were configured to detect anomalies and trigger incident responses. "
    "The team successfully delivered three major features ahead of the planned release schedule. "
    "Stakeholder feedback was incorporated into the product roadmap for the upcoming quarter. "
    "A comprehensive post-mortem analysis was completed following the recent production incident."
)

POOL_SHORT_WORDS = POOL_SHORT.split()
POOL_MIDDLE_WORDS = POOL_MIDDLE.split()
POOL_LONG_WORDS = POOL_LONG.split()

APP_IDS_THRESHOLDS = [
    (40, "GATEWAY"),
    (65, "PAYMENT_APP"),
    (85, "ORDER_API"),
    (95, "AUTH_SVC"),
    (100, "INVENTORY"),
]

LOG_LEVEL_THRESHOLDS = [
    (60, "INFO"),
    (80, "DEBUG"),
    (90, "WARN"),
    (97, "ERROR"),
    (99, "FATAL"),
    (100, "TRACE"),
]

BUSINESS_KEY_THRESHOLDS = [
    (50, ""),
    (60, "ORDER_FLOW"),
    (70, "USER_MGMT"),
    (80, "PAYMENT_PROCESS"),
    (90, "INVENTORY_CHECK"),
    (100, "SHIPMENT"),
]

LOG_LEVEL_MAP = {"TRACE": 1, "DEBUG": 2, "INFO": 3, "WARN": 4, "ERROR": 5, "FATAL": 6}
KEYWORDS = ["validation", "security", "request", "timeout", "retry", "auth", "payment", "connect"]
DOMAINS = ["com", "net", "io"]
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13) Chrome/120.0 Mobile",
    "curl/7.68.0",
    "curl/8.1.2",
    "PostmanRuntime/7.29.2",
    "PostmanRuntime/7.36.0",
    "python-requests/2.31.0",
    "axios/1.6.0",
    "okhttp/4.11.0",
    "Java/17.0.9",
    "Go-http-client/1.1",
]

DATABASES = ["ClickHouse", "TimescaleDB", "InfluxDB"]


@dataclass
class Config:
    ch_host: str
    ch_port: int
    ch_user: str
    ch_password: str
    pg_host: str
    pg_port: int
    pg_user: str
    pg_password: str
    pg_db: str
    influx_url: str
    influx_token: str
    influx_org: str
    influx_bucket: str
    influx_container: str
    total_rows: int
    batch_size: int
    influx_chunk: int
    verify_every_batches: int
    write_to_file: bool
    output_file: str
    cleanup_before_insert: bool


class UiLogger:
    def __init__(self, placeholder, output_file, write_to_file):
        self.placeholder = placeholder
        self.lines = []
        self.file_handle = None
        if write_to_file:
            path = Path(output_file).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.file_handle = path.open("w", encoding="utf-8")
            self.write(f"=== generate_3db output === {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
            self.write(f"Output file: {path}")

    def write(self, message=""):
        self.lines.append(str(message))
        log_text = html.escape("\n".join(self.lines[-500:]))
        log_html = f"""
        <div id="log-box" style="
            height: 360px;
            overflow-y: auto;
            background: #0f172a;
            color: #e5e7eb;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 12px;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 13px;
            line-height: 1.45;
            white-space: pre-wrap;
        ">{log_text}</div>
        <script>
            const box = document.getElementById("log-box");
            if (box) {{
                box.scrollTop = box.scrollHeight;
            }}
        </script>
        """
        self.placeholder.empty()
        with self.placeholder.container():
            components.html(log_html, height=386)
        if self.file_handle and not self.file_handle.closed:
            self.file_handle.write(str(message) + "\n")
            self.file_handle.flush()

    def close(self):
        if self.file_handle:
            self.file_handle.close()


def md5hex(value):
    return hashlib.md5(str(value).encode()).hexdigest()


def city_hash(value):
    return int(hashlib.md5(str(value).encode()).hexdigest(), 16)


def hex_str(value, length):
    return hashlib.md5(str(value).encode()).hexdigest()[:length]


def hex_words(base, count, offset=0):
    return " ".join(hex_str(base + x + offset, (city_hash(x + offset) % 4) + 4) for x in range(count))


def pick_by_threshold(value, thresholds):
    for threshold, label in thresholds:
        if value < threshold:
            return label
    return thresholds[-1][1]


def format_duration(seconds):
    seconds = int(max(0, seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def update_progress(progress_slot, done, total_rows, started_at):
    pct = done / total_rows if total_rows else 0
    elapsed_total = time.time() - started_at
    progress_slot.progress(
        pct,
        text=f"{done:,} / {total_rows:,} rows / {format_duration(elapsed_total)} (hh:mm:ss)",
    )


def generate_raw_data(number, h_line, h_group, h5):
    ip = f"10.0.{h_line % 255}.{h5 % 255}"
    phone = f"09{10000000 + (h_group % 90000000)}"
    email = f"user_{hex_str(h_group, 8)}@domain.{DOMAINS[h_group % 3]}"
    user_agent = USER_AGENTS[h_line % len(USER_AGENTS)]

    sn_word_count = (h_line % 8) + 8
    sn_start = (h_line ^ h5) % max(1, len(POOL_SHORT_WORDS) - sn_word_count)
    short_note = (
        f"{hex_words(number, 10, 0)} "
        f"{' '.join(POOL_SHORT_WORDS[sn_start: sn_start + sn_word_count])} "
        f"{hex_words(number, 10, 100)}"
    )

    md_word_count = (h5 % 10) + 10
    md_start = (h_group ^ h_line) % max(1, len(POOL_MIDDLE_WORDS) - md_word_count)
    middle_desc = (
        f"{hex_words(number, 40, 200)} "
        f"{' '.join(POOL_MIDDLE_WORDS[md_start: md_start + md_word_count])} "
        f"{hex_words(number, 40, 300)}"
    )
    md_words = middle_desc.split()
    if len(md_words) < 100:
        middle_desc = middle_desc + " " + hex_words(number, 100 - len(md_words), 350)
    middle_desc = " ".join(middle_desc.split()[:150])

    lc_word_count = (h_line % 15) + 15
    lc_start = (h_group ^ h5) % max(1, len(POOL_LONG_WORDS) - lc_word_count)
    long_context = (
        f"{hex_words(number, 130, 400)} "
        f"{' '.join(POOL_LONG_WORDS[lc_start: lc_start + lc_word_count])} "
        f"{hex_words(number, 130, 500)}"
    )
    lc_words = long_context.split()
    if len(lc_words) < 300:
        long_context = long_context + " " + hex_words(number, 300 - len(lc_words), 700)
    long_context = " ".join(long_context.split()[:500])

    return json.dumps(
        {
            "ip": ip,
            "phone": phone,
            "email": email,
            "user_agent": user_agent,
            "short_note": short_note,
            "middle_desc": middle_desc,
            "long_context": long_context,
            "payload": {"code": h_group % 1000, "latency_ms": h5 % 500},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def generate_batch(batch_idx, batch_size, start_time):
    rows = []
    base_number = batch_idx * batch_size

    for i in range(batch_size):
        number = base_number + i
        h_line = city_hash(number)
        h5 = city_hash(number + 5_000_000)
        chunk_seed = city_hash(number // 1000)
        group_size = chunk_seed % 13 + 5
        trace_group = number // group_size
        h_group = city_hash(trace_group)

        log_time = start_time + timedelta(
            milliseconds=trace_group * group_size * 100 + (number % group_size) * 100 + h_line % 1000
        )

        rows.append(
            {
                "id": str(uuid.uuid4()),
                "trace_id": "tr-" + md5hex(trace_group),
                "app_id": pick_by_threshold(h_line % 100, APP_IDS_THRESHOLDS),
                "log_level": pick_by_threshold((h_line >> 8) % 100, LOG_LEVEL_THRESHOLDS),
                "biz_key": pick_by_threshold(h_group % 100, BUSINESS_KEY_THRESHOLDS),
                "log_time": log_time,
                "message": f"{md5hex(number)[:5]} {KEYWORDS[h5 % 8]} {md5hex(number + 1)[:6]}",
                "raw_data": generate_raw_data(number, h_line, h_group, h5),
            }
        )
    return rows


def connect_clients(cfg):
    import clickhouse_connect
    import psycopg2
    from influxdb_client import InfluxDBClient
    from influxdb_client.client.write_api import SYNCHRONOUS

    ch_client = clickhouse_connect.get_client(
        host=cfg.ch_host,
        port=cfg.ch_port,
        username=cfg.ch_user,
        password=cfg.ch_password,
    )
    pg_conn = psycopg2.connect(
        host=cfg.pg_host,
        port=cfg.pg_port,
        user=cfg.pg_user,
        password=cfg.pg_password,
        dbname=cfg.pg_db,
    )
    pg_conn.autocommit = False
    influx_client = InfluxDBClient(
        url=cfg.influx_url,
        token=cfg.influx_token,
        org=cfg.influx_org,
        timeout=60_000,
    )
    write_api = influx_client.write_api(write_options=SYNCHRONOUS)
    return ch_client, pg_conn, influx_client, write_api


def timed_insert_clickhouse(ch_client, rows):
    t0 = time.time()
    ch_rows = [
        [
            r["id"],
            r["trace_id"],
            r["app_id"],
            r["log_level"],
            r["biz_key"],
            r["log_time"],
            r["message"],
            r["raw_data"],
        ]
        for r in rows
    ]
    ch_client.insert(
        "DistributedLogging",
        ch_rows,
        column_names=["id", "traceId", "appId", "logLevel", "businessKey", "logTime", "message", "rawData"],
    )
    return (time.time() - t0) * 1000


def timed_insert_timescale(pg_conn, rows):
    import psycopg2.extras

    t0 = time.time()
    cursor = pg_conn.cursor()
    ts_rows = [
        (
            r["id"],
            r["trace_id"],
            r["app_id"],
            LOG_LEVEL_MAP[r["log_level"]],
            r["biz_key"] or None,
            r["log_time"],
            r["message"],
            r["raw_data"],
        )
        for r in rows
    ]
    psycopg2.extras.execute_batch(
        cursor,
        """
        INSERT INTO distributed_logging
            (id, trace_id, app_id, log_level, business_key, log_time, message, raw_data)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING
        """,
        ts_rows,
        page_size=500,
    )
    pg_conn.commit()
    cursor.close()
    return (time.time() - t0) * 1000


def timed_insert_influx(write_api, rows, cfg, logger):
    t0 = time.time()
    for i in range(0, len(rows), cfg.influx_chunk):
        chunk = rows[i : i + cfg.influx_chunk]
        records = [
            {
                "measurement": "distributed_logging",
                "tags": {
                    "appId": r["app_id"],
                    "logLevel": r["log_level"],
                    "businessKey": r["biz_key"] or "",
                },
                "fields": {
                    "traceId": r["trace_id"],
                    "message": r["message"],
                    "rawData": r["raw_data"],
                },
                "time": r["log_time"],
            }
            for r in chunk
        ]
        for attempt in range(1, 6):
            try:
                write_api.write(bucket=cfg.influx_bucket, record=records)
                break
            except Exception as exc:
                if attempt == 5:
                    logger.write(f"InfluxDB bỏ qua chunk: {exc}")
                else:
                    wait = attempt * 2
                    logger.write(f"InfluxDB timeout, thử lại lần {attempt}/5 sau {wait}s...")
                    time.sleep(wait)
    return (time.time() - t0) * 1000


def reset_influx_bucket(influx_client, cfg, logger):
    from influxdb_client.domain.bucket_retention_rules import BucketRetentionRules

    buckets_api = influx_client.buckets_api()
    orgs_api = influx_client.organizations_api()
    org = orgs_api.find_organizations(org=cfg.influx_org)[0]
    bucket = buckets_api.find_bucket_by_name(cfg.influx_bucket)
    if bucket:
        buckets_api.delete_bucket(bucket)
        logger.write(f"InfluxDB bucket '{cfg.influx_bucket}' đã xóa")
    buckets_api.create_bucket(
        bucket_name=cfg.influx_bucket,
        retention_rules=BucketRetentionRules(type="expire", every_seconds=90 * 24 * 3600),
        org_id=org.id,
    )
    logger.write(f"InfluxDB bucket '{cfg.influx_bucket}' đã tạo lại")


def cleanup_databases(ch_client, pg_conn, influx_client, cfg, logger):
    logger.write("Đang dọn dẹp data cũ...")
    ch_client.command("TRUNCATE TABLE DistributedLogging")
    logger.write("ClickHouse done")
    cur = pg_conn.cursor()
    cur.execute("TRUNCATE TABLE distributed_logging")
    pg_conn.commit()
    cur.close()
    logger.write("TimescaleDB done")
    reset_influx_bucket(influx_client, cfg, logger)
    time.sleep(3)
    logger.write("Đã dọn dẹp xong cả 3 DB")


def get_storage_sizes(ch_client, pg_conn, cfg):
    sizes = {}
    try:
        df = ch_client.query_df(
            """
            SELECT formatReadableSize(sum(bytes_on_disk)) AS size
            FROM system.parts
            WHERE table = 'DistributedLogging' AND active = 1
            """
        )
        sizes["ClickHouse"] = df.iloc[0]["size"] if not df.empty else "N/A"
    except Exception as exc:
        sizes["ClickHouse"] = f"ERROR: {exc}"

    try:
        cur = pg_conn.cursor()
        cur.execute(
            """
            SELECT pg_size_pretty(sum(total_bytes)) AS total_size
            FROM hypertable_detailed_size('distributed_logging')
            """
        )
        row = cur.fetchone()
        cur.close()
        sizes["TimescaleDB"] = row[0] if row else "N/A"
    except Exception as exc:
        sizes["TimescaleDB"] = f"ERROR: {exc}"

    try:
        result = subprocess.run(
            ["docker", "exec", cfg.influx_container, "du", "-sh", "/var/lib/influxdb2"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        sizes["InfluxDB"] = result.stdout.split("\t")[0].strip() if result.returncode == 0 else f"ERROR: {result.stderr.strip()}"
    except Exception as exc:
        sizes["InfluxDB"] = f"ERROR: {exc}"

    return sizes


def get_group_stats(ch_client, pg_conn, influx_client, cfg, stat_name, batch_idx, inserted_rows):
    if stat_name == "BusinessKey":
        ch_sql = "SELECT businessKey AS label, count() AS cnt FROM DistributedLogging GROUP BY businessKey ORDER BY cnt DESC"
        pg_sql = "SELECT COALESCE(business_key,'') AS label, count(*) AS cnt FROM distributed_logging GROUP BY label ORDER BY cnt DESC"
        influx_tag = "businessKey"
    elif stat_name == "AppId":
        ch_sql = "SELECT appId AS label, count() AS cnt FROM DistributedLogging GROUP BY appId ORDER BY cnt DESC"
        pg_sql = "SELECT app_id AS label, count(*) AS cnt FROM distributed_logging GROUP BY app_id ORDER BY cnt DESC"
        influx_tag = "appId"
    else:
        ch_sql = "SELECT toString(logLevel) AS label, count() AS cnt FROM DistributedLogging GROUP BY logLevel ORDER BY cnt DESC"
        pg_sql = """
            SELECT CASE log_level
                WHEN 1 THEN 'TRACE' WHEN 2 THEN 'DEBUG' WHEN 3 THEN 'INFO'
                WHEN 4 THEN 'WARN' WHEN 5 THEN 'ERROR' WHEN 6 THEN 'FATAL'
            END AS label, count(*) AS cnt
            FROM distributed_logging
            GROUP BY log_level
            ORDER BY cnt DESC
        """
        influx_tag = "logLevel"

    rows = []
    timing_rows = []
    try:
        t0 = time.time()
        df = ch_client.query_df(ch_sql)
        timing_rows.append(
            {
                "batch": batch_idx + 1,
                "rows_done": inserted_rows,
                "metric": stat_name,
                "database": "ClickHouse",
                "ms": round((time.time() - t0) * 1000, 2),
                "status": "OK",
            }
        )
        rows.extend({"database": "ClickHouse", "metric": stat_name, "label": r["label"] or "(trống)", "count": int(r["cnt"])} for _, r in df.iterrows())
    except Exception as exc:
        timing_rows.append(
            {
                "batch": batch_idx + 1,
                "rows_done": inserted_rows,
                "metric": stat_name,
                "database": "ClickHouse",
                "ms": None,
                "status": f"ERROR: {exc}",
            }
        )

    try:
        t0 = time.time()
        cur = pg_conn.cursor()
        cur.execute(pg_sql)
        fetched_rows = cur.fetchall()
        timing_rows.append(
            {
                "batch": batch_idx + 1,
                "rows_done": inserted_rows,
                "metric": stat_name,
                "database": "TimescaleDB",
                "ms": round((time.time() - t0) * 1000, 2),
                "status": "OK",
            }
        )
        rows.extend({"database": "TimescaleDB", "metric": stat_name, "label": r[0] or "(trống)", "count": int(r[1])} for r in fetched_rows)
        cur.close()
    except Exception as exc:
        timing_rows.append(
            {
                "batch": batch_idx + 1,
                "rows_done": inserted_rows,
                "metric": stat_name,
                "database": "TimescaleDB",
                "ms": None,
                "status": f"ERROR: {exc}",
            }
        )

    try:
        flux = f'''
            from(bucket: "{cfg.influx_bucket}")
              |> range(start: -61d)
              |> filter(fn: (r) => r["_measurement"] == "distributed_logging")
              |> filter(fn: (r) => r["_field"] == "message")
              |> group(columns: ["{influx_tag}"])
              |> count()
              |> group()
              |> sort(columns: ["_value"], desc: true)
        '''
        t0 = time.time()
        tables = influx_client.query_api().query(flux, org=cfg.influx_org)
        timing_rows.append(
            {
                "batch": batch_idx + 1,
                "rows_done": inserted_rows,
                "metric": stat_name,
                "database": "InfluxDB",
                "ms": round((time.time() - t0) * 1000, 2),
                "status": "OK",
            }
        )
        rows.extend(
            {
                "database": "InfluxDB",
                "metric": stat_name,
                "label": r.values.get(influx_tag, "") or "(trống)",
                "count": int(r.get_value()),
            }
            for table in tables
            for r in table.records
        )
    except Exception as exc:
        timing_rows.append(
            {
                "batch": batch_idx + 1,
                "rows_done": inserted_rows,
                "metric": stat_name,
                "database": "InfluxDB",
                "ms": None,
                "status": f"ERROR: {exc}",
            }
        )

    totals_by_database = {}
    for row in rows:
        totals_by_database[row["database"]] = totals_by_database.get(row["database"], 0) + row["count"]
    for row in rows:
        total = totals_by_database.get(row["database"], 0)
        row["percent"] = round(row["count"] * 100 / total, 2) if total else 0.0

    return rows, timing_rows


def verify_batch(ch_client, pg_conn, influx_client, cfg, rows, batch_idx, inserted_rows):
    metrics = {"point_lookup": [], "trace_lookup": [], "free_text": []}
    stats_rows = []
    stats_query_rows = []
    sample = random.choice(rows)
    row_id = sample["id"]
    log_time = sample["log_time"]
    message = sample["message"]
    search_trace_id = random.choice(rows)["trace_id"]
    raw = json.loads(sample["raw_data"])
    lc_words = raw["long_context"].split()
    lc_mid_start = random.randint(130, min(150, len(lc_words) - 6))
    lc_text = " ".join(lc_words[lc_mid_start : lc_mid_start + 5])

    t0 = time.time()
    df = ch_client.query_df(f"SELECT toString(id) AS id, message FROM DistributedLogging WHERE id = '{row_id}' LIMIT 1")
    metrics["point_lookup"].append({"batch": batch_idx + 1, "rows_done": inserted_rows, "database": "ClickHouse", "ms": (time.time() - t0) * 1000, "result": int(not df.empty)})

    t0 = time.time()
    cur = pg_conn.cursor()
    cur.execute("SELECT message FROM distributed_logging WHERE id = %s AND log_time = %s LIMIT 1", (row_id, log_time))
    pg_found = cur.fetchone()
    cur.close()
    metrics["point_lookup"].append({"batch": batch_idx + 1, "rows_done": inserted_rows, "database": "TimescaleDB", "ms": (time.time() - t0) * 1000, "result": int(bool(pg_found))})

    t0 = time.time()
    flux = f'''
        from(bucket: "{cfg.influx_bucket}")
          |> range(start: -61d)
          |> filter(fn: (r) => r["_measurement"] == "distributed_logging")
          |> filter(fn: (r) => r["_field"] == "message")
          |> filter(fn: (r) => r["_value"] == "{message}")
          |> limit(n: 1)
    '''
    tables = influx_client.query_api().query(flux, org=cfg.influx_org)
    found = any(record for table in tables for record in table.records)
    metrics["point_lookup"].append({"batch": batch_idx + 1, "rows_done": inserted_rows, "database": "InfluxDB", "ms": (time.time() - t0) * 1000, "result": int(found)})

    t0 = time.time()
    df = ch_client.query_df(f"SELECT toString(id) AS id FROM DistributedLogging WHERE traceId = '{search_trace_id}'")
    metrics["trace_lookup"].append({"batch": batch_idx + 1, "rows_done": inserted_rows, "database": "ClickHouse", "ms": (time.time() - t0) * 1000, "result": len(df)})

    t0 = time.time()
    cur = pg_conn.cursor()
    cur.execute("SELECT count(*) FROM distributed_logging WHERE trace_id = %s", (search_trace_id,))
    count = cur.fetchone()[0]
    cur.close()
    metrics["trace_lookup"].append({"batch": batch_idx + 1, "rows_done": inserted_rows, "database": "TimescaleDB", "ms": (time.time() - t0) * 1000, "result": int(count)})

    t0 = time.time()
    flux = f'''
        from(bucket: "{cfg.influx_bucket}")
          |> range(start: -61d)
          |> filter(fn: (r) => r["_measurement"] == "distributed_logging")
          |> filter(fn: (r) => r["_field"] == "traceId")
          |> filter(fn: (r) => r["_value"] == "{search_trace_id}")
    '''
    tables = influx_client.query_api().query(flux, org=cfg.influx_org)
    count = sum(len(table.records) for table in tables)
    metrics["trace_lookup"].append({"batch": batch_idx + 1, "rows_done": inserted_rows, "database": "InfluxDB", "ms": (time.time() - t0) * 1000, "result": int(count)})

    t0 = time.time()
    df = ch_client.query_df(f"SELECT toString(id) AS id FROM DistributedLogging WHERE rawData LIKE '%{lc_text}%' LIMIT 10")
    metrics["free_text"].append({"batch": batch_idx + 1, "rows_done": inserted_rows, "database": "ClickHouse", "ms": (time.time() - t0) * 1000, "result": len(df)})

    t0 = time.time()
    cur = pg_conn.cursor()
    cur.execute("SELECT id FROM distributed_logging WHERE raw_data::text ILIKE %s LIMIT 10", (f"%{lc_text}%",))
    rows_pg = cur.fetchall()
    cur.close()
    metrics["free_text"].append({"batch": batch_idx + 1, "rows_done": inserted_rows, "database": "TimescaleDB", "ms": (time.time() - t0) * 1000, "result": len(rows_pg)})

    t0 = time.time()
    lc_safe = lc_text.replace('"', '\\"')
    flux = f'''
        import "strings"
        from(bucket: "{cfg.influx_bucket}")
          |> range(start: -61d)
          |> filter(fn: (r) => r["_measurement"] == "distributed_logging")
          |> filter(fn: (r) => r["_field"] == "rawData")
          |> filter(fn: (r) => strings.containsStr(v: r["_value"], substr: "{lc_safe}"))
          |> limit(n: 10)
    '''
    tables = influx_client.query_api().query(flux, org=cfg.influx_org)
    count = sum(len(table.records) for table in tables)
    metrics["free_text"].append({"batch": batch_idx + 1, "rows_done": inserted_rows, "database": "InfluxDB", "ms": (time.time() - t0) * 1000, "result": int(count)})

    for stat_name in ["AppId", "LogLevel", "BusinessKey"]:
        metric_stats, metric_timing = get_group_stats(ch_client, pg_conn, influx_client, cfg, stat_name, batch_idx, inserted_rows)
        stats_rows.extend(metric_stats)
        stats_query_rows.extend(metric_timing)

    samples = {
        "point_lookup_id": row_id,
        "trace_lookup_trace_id": search_trace_id,
        "free_text": lc_text,
    }
    return metrics, stats_rows, stats_query_rows, samples


def find_metric_ms(rows, database):
    for row in rows:
        if row.get("database") == database:
            value = row.get("ms")
            return round(value, 2) if value is not None else None
    return None


def build_summary_row(batch_idx, insert_ms, sizes, metrics, stats_query_rows):
    row = {"patch": batch_idx + 1}

    for database in DATABASES:
        row[f"insert_{database}_ms"] = round(insert_ms.get(database, 0), 2)

    for database in DATABASES:
        row[f"storage_{database}"] = sizes.get(database)

    metric_groups = {
        "point_lookup": metrics.get("point_lookup", []),
        "trace_lookup": metrics.get("trace_lookup", []),
        "free_text": metrics.get("free_text", []),
    }
    for metric_name, metric_rows in metric_groups.items():
        for database in DATABASES:
            row[f"{metric_name}_{database}_ms"] = find_metric_ms(metric_rows, database)

    for metric_name in ["AppId", "LogLevel", "BusinessKey"]:
        metric_rows = [r for r in stats_query_rows if r.get("metric") == metric_name]
        for database in DATABASES:
            row[f"{metric_name}_distribution_{database}_ms"] = find_metric_ms(metric_rows, database)

    return row


def render_results(insert_rows, storage_rows, lookup_rows, stats_rows, stats_query_rows, summary_rows):
    if insert_rows:
        df_insert = pd.DataFrame(insert_rows)
        batch_rows_values = df_insert["batch_rows"].dropna().unique().tolist()
        if len(batch_rows_values) == 1:
            insert_title = f"Insert {int(batch_rows_values[0]):,} rows time"
        else:
            insert_title = "Insert batch rows time"
        st.subheader(insert_title)
        st.dataframe(df_insert, use_container_width=True, hide_index=True)
        chart_df = df_insert.melt(
            id_vars=["batch", "batch_rows", "rows_done"],
            value_vars=["ClickHouse_ms", "TimescaleDB_ms", "InfluxDB_ms"],
            var_name="database",
            value_name="ms",
        )
        chart_df["database"] = chart_df["database"].str.replace("_ms", "", regex=False)
        st.plotly_chart(
            px.line(chart_df, x="rows_done", y="ms", color="database", markers=True, title=insert_title),
            use_container_width=True,
        )

    if storage_rows:
        df_storage = pd.DataFrame(storage_rows)
        st.subheader("Storage size")
        st.dataframe(df_storage, use_container_width=True, hide_index=True)

    if lookup_rows:
        df_lookup = pd.DataFrame(lookup_rows)
        metric_titles = {
            "point_lookup": "Point lookup",
            "trace_lookup": "Trace lookup",
            "free_text": "Free-text search",
        }
        for metric_type, title in metric_titles.items():
            metric_df = df_lookup[df_lookup["type"] == metric_type].copy()
            if metric_df.empty:
                continue
            st.subheader(title)
            st.dataframe(metric_df.drop(columns=["type"]), use_container_width=True, hide_index=True)
            st.plotly_chart(
                px.line(
                    metric_df,
                    x="rows_done",
                    y="ms",
                    color="database",
                    markers=True,
                    title=f"{title} time",
                ),
                use_container_width=True,
            )

    if stats_rows:
        df_stats = pd.DataFrame(stats_rows)
        df_stats_query = pd.DataFrame(stats_query_rows) if stats_query_rows else pd.DataFrame()
        metric_titles = {
            "AppId": "AppId distribution",
            "LogLevel": "LogLevel distribution",
            "BusinessKey": "BusinessKey distribution",
        }
        for metric, title in metric_titles.items():
            metric_df = df_stats[df_stats["metric"] == metric].copy()
            if not metric_df.empty:
                st.subheader(title)
                metric_df = metric_df[["database", "label", "count", "percent"]]
                st.dataframe(metric_df, use_container_width=True, hide_index=True)
                st.plotly_chart(
                    px.bar(
                        metric_df,
                        x="label",
                        y="percent",
                        color="database",
                        barmode="group",
                        title=title,
                        labels={"percent": "percent (%)", "label": metric},
                        hover_data={"count": True, "percent": ":.2f"},
                    ),
                    use_container_width=True,
                )

                if not df_stats_query.empty:
                    timing_df = df_stats_query[df_stats_query["metric"] == metric].copy()
                    if not timing_df.empty:
                        st.markdown(f"**{title} query time**")
                        timing_df = timing_df[["batch", "rows_done", "database", "ms", "status"]]
                        st.dataframe(timing_df, use_container_width=True, hide_index=True)
                        chart_df = timing_df.dropna(subset=["ms"])
                        if not chart_df.empty:
                            st.plotly_chart(
                                px.line(
                                    chart_df,
                                    x="rows_done",
                                    y="ms",
                                    color="database",
                                    markers=True,
                                    title=f"{title} query time",
                                    labels={"ms": "query time (ms)"},
                                ),
                                use_container_width=True,
                            )

    elif stats_query_rows:
        df_stats_query = pd.DataFrame(stats_query_rows)
        for metric, title in {
            "AppId": "AppId distribution query time",
            "LogLevel": "LogLevel distribution query time",
            "BusinessKey": "BusinessKey distribution query time",
        }.items():
            timing_df = df_stats_query[df_stats_query["metric"] == metric].copy()
            if not timing_df.empty:
                st.subheader(title)
                timing_df = timing_df[["batch", "rows_done", "database", "ms", "status"]]
                st.dataframe(timing_df, use_container_width=True, hide_index=True)
                chart_df = timing_df.dropna(subset=["ms"])
                if not chart_df.empty:
                    st.plotly_chart(
                        px.line(
                            chart_df,
                            x="rows_done",
                            y="ms",
                            color="database",
                            markers=True,
                            title=title,
                            labels={"ms": "query time (ms)"},
                        ),
                        use_container_width=True,
                    )

    if summary_rows:
        st.subheader("Verify summary")
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)


def run_benchmark(cfg, logger, progress_slot, results_slot):
    ch_client = pg_conn = influx_client = None
    insert_rows = []
    storage_rows = []
    lookup_rows = []
    stats_rows = []
    stats_query_rows = []
    summary_rows = []
    total_verify_s = 0.0
    start_time_data = datetime.now(timezone.utc) - timedelta(days=60)

    try:
        logger.write("Đang kết nối 3 database...")
        ch_client, pg_conn, influx_client, write_api = connect_clients(cfg)
        logger.write("Kết nối thành công")

        if cfg.cleanup_before_insert:
            cleanup_databases(ch_client, pg_conn, influx_client, cfg, logger)
        else:
            logger.write("Bỏ qua xóa data cũ, append vào data hiện tại")

        sizes = get_storage_sizes(ch_client, pg_conn, cfg)
        storage_rows.extend({"batch": 0, "rows_done": 0, "database": db, "size": size} for db, size in sizes.items())

        total_batches = cfg.total_rows // cfg.batch_size
        if cfg.total_rows % cfg.batch_size:
            total_batches += 1
        started_at = time.time()
        logger.write(f"Bắt đầu generate + insert {cfg.total_rows:,} dòng")

        for batch_idx in range(total_batches):
            remaining = cfg.total_rows - batch_idx * cfg.batch_size
            current_batch_size = min(cfg.batch_size, remaining)
            rows = generate_batch(batch_idx, current_batch_size, start_time_data)

            with ThreadPoolExecutor(max_workers=3) as executor:
                f1 = executor.submit(timed_insert_clickhouse, ch_client, rows)
                f2 = executor.submit(timed_insert_timescale, pg_conn, rows)
                f3 = executor.submit(timed_insert_influx, write_api, rows, cfg, logger)
                while not (f1.done() and f2.done() and f3.done()):
                    update_progress(
                        progress_slot,
                        batch_idx * cfg.batch_size,
                        cfg.total_rows,
                        started_at,
                    )
                    time.sleep(1)
                ch_ms = f1.result()
                ts_ms = f2.result()
                influx_ms = f3.result()

            done = min((batch_idx + 1) * cfg.batch_size, cfg.total_rows)
            elapsed_insert = max(0.001, time.time() - started_at - total_verify_s)
            speed = done / elapsed_insert
            pct = done / cfg.total_rows
            insert_rows.append(
                {
                    "batch": batch_idx + 1,
                    "batch_rows": current_batch_size,
                    "rows_done": done,
                    "ClickHouse_ms": round(ch_ms, 2),
                    "TimescaleDB_ms": round(ts_ms, 2),
                    "InfluxDB_ms": round(influx_ms, 2),
                }
            )
            logger.write(
                f"Batch {batch_idx + 1:>5} | {done:>10,} / {cfg.total_rows:,} | "
                f"{pct * 100:.1f}% | {speed:,.0f} rows/s"
            )
            update_progress(progress_slot, done, cfg.total_rows, started_at)

            should_verify = (batch_idx + 1) % cfg.verify_every_batches == 0 or batch_idx + 1 == total_batches
            if should_verify:
                logger.write(f"Verify batch {batch_idx + 1}")
                verify_start = time.time()
                sizes = get_storage_sizes(ch_client, pg_conn, cfg)
                storage_rows.extend({"batch": batch_idx + 1, "rows_done": done, "database": db, "size": size} for db, size in sizes.items())
                metrics, batch_stats, batch_stats_query, samples = verify_batch(ch_client, pg_conn, influx_client, cfg, rows, batch_idx, done)
                for metric_type, metric_rows in metrics.items():
                    for row in metric_rows:
                        row["type"] = metric_type
                        lookup_rows.append(row)
                stats_rows = batch_stats
                stats_query_rows.extend(batch_stats_query)
                summary_rows.append(
                    build_summary_row(
                        batch_idx,
                        {
                            "ClickHouse": ch_ms,
                            "TimescaleDB": ts_ms,
                            "InfluxDB": influx_ms,
                        },
                        sizes,
                        metrics,
                        batch_stats_query,
                    )
                )
                total_verify_s += time.time() - verify_start
                logger.write(f"Point lookup id: {samples['point_lookup_id']}")
                logger.write(f"Trace lookup trace_id: {samples['trace_lookup_trace_id']}")
                logger.write(f"Free-text sample: {samples['free_text']}")
                logger.write()
                with results_slot.container():
                    render_results(insert_rows, storage_rows, lookup_rows, stats_rows, stats_query_rows, summary_rows)

        logger.write(f"Hoàn thành. Đã insert {cfg.total_rows:,} dòng vào cả 3 DB")
    finally:
        try:
            if pg_conn:
                pg_conn.close()
            if influx_client:
                influx_client.close()
        finally:
            logger.close()


def build_config():
    st.sidebar.header("ClickHouse")
    ch_host = st.sidebar.text_input("CH_HOST", "localhost")
    ch_port = st.sidebar.number_input("CH_PORT", min_value=1, max_value=65535, value=8123)
    ch_user = st.sidebar.text_input("CH_USER", "admin")
    ch_password = st.sidebar.text_input("CH_PASSWORD", "P@ssw0rd", type="password")

    st.sidebar.header("TimescaleDB")
    pg_host = st.sidebar.text_input("PG_HOST", "localhost")
    pg_port = st.sidebar.number_input("PG_PORT", min_value=1, max_value=65535, value=5432)
    pg_user = st.sidebar.text_input("PG_USER", "postgres")
    pg_password = st.sidebar.text_input("PG_PASSWORD", "P@ssw0rd", type="password")
    pg_db = st.sidebar.text_input("PG_DB", "postgres")

    st.sidebar.header("InfluxDB")
    influx_url = st.sidebar.text_input("INFLUX_URL", "http://localhost:8086")
    influx_token = st.sidebar.text_area(
        "INFLUX_TOKEN",
        "lUDz6ChzF0UdOi-11lc6w_rQs2Z29WT-j8CD9rVRbZCqdZcV1pIruvuEnZWDU1k8Pp_FNBZYzGkmse9hkO72kw==",
        height=90,
    )
    influx_org = st.sidebar.text_input("INFLUX_ORG", "UIT")
    influx_bucket = st.sidebar.text_input("INFLUX_BUCKET", "DistributedLogging")
    influx_container = st.sidebar.text_input("Influx Docker container", "csdlnc-influxdb-1")

    st.sidebar.header("Run config")
    total_rows = st.sidebar.number_input("TOTAL_ROWS", min_value=1_000, value=1_000_000, step=1_000)
    batch_size = st.sidebar.number_input("BATCH_SIZE", min_value=100, value=1_000, step=100)
    influx_chunk = st.sidebar.number_input("INFLUX_CHUNK", min_value=10, value=100, step=10)
    verify_every_batches = st.sidebar.number_input("Verify every N batches", min_value=1, value=20, step=1)
    cleanup_before_insert = st.sidebar.checkbox("Xóa data cũ trước khi insert", value=False)
    write_to_file = st.sidebar.checkbox("Ghi log ra file", value=True)
    output_file = st.sidebar.text_input(
        "OUTPUT_FILE",
        str(Path.cwd() / "generate_3db_output.txt"),
    )

    return Config(
        ch_host=ch_host,
        ch_port=int(ch_port),
        ch_user=ch_user,
        ch_password=ch_password,
        pg_host=pg_host,
        pg_port=int(pg_port),
        pg_user=pg_user,
        pg_password=pg_password,
        pg_db=pg_db,
        influx_url=influx_url,
        influx_token=influx_token.strip(),
        influx_org=influx_org,
        influx_bucket=influx_bucket,
        influx_container=influx_container,
        total_rows=int(total_rows),
        batch_size=int(batch_size),
        influx_chunk=int(influx_chunk),
        verify_every_batches=int(verify_every_batches),
        write_to_file=write_to_file,
        output_file=output_file,
        cleanup_before_insert=cleanup_before_insert,
    )


def main():
    st.set_page_config(page_title="3DB Distributed Logging Benchmark", layout="wide")
    st.title("3DB Distributed Logging Benchmark")

    cfg = build_config()
    run_clicked = st.sidebar.button("Run benchmark", type="primary", use_container_width=True)

    st.caption("Click Run benchmark để generate dữ liệu, insert vào ClickHouse, TimescaleDB, InfluxDB, rồi hiển thị log, bảng thống kê và biểu đồ.")
    progress_slot = st.empty()
    log_slot = st.empty()
    results_slot = st.empty()

    if run_clicked:
        logger = UiLogger(log_slot, cfg.output_file, cfg.write_to_file)
        try:
            run_benchmark(cfg, logger, progress_slot, results_slot)
        except Exception as exc:
            logger.write(f"ERROR: {exc}")
            st.exception(exc)


if __name__ == "__main__":
    main()
