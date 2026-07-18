#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 overnight research 的 raw/*.json 整合进 SQLite 可搜索数据库。"""

import json
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).parent
RAW_DIR = BASE_DIR / "raw"
DB_DIR = BASE_DIR / "db"
DB_PATH = DB_DIR / "overnight_research.db"

# 类别与文件名映射（也决定数据库表名）
CATEGORY_FILES = {
    "china_mechanisms": "china_mechanisms.json",
    "investor_speeches": "investor_speeches.json",
    "academic_research": "academic_research.json",
    "industry_deep_dive": "industry_deep_dive.json",
    "event_cases": "event_cases.json",
}

# 公共字段（所有表都有）
COMMON_COLUMNS = [
    ("id", "TEXT PRIMARY KEY"),
    ("title", "TEXT NOT NULL"),
    ("source", "TEXT"),
    ("url", "TEXT"),
    ("date", "TEXT"),
    ("accessed_at", "TEXT"),
    ("category", "TEXT NOT NULL"),
    ("tags", "TEXT"),          # JSON array 字符串
    ("summary", "TEXT"),
    ("key_points", "TEXT"),    # JSON array 字符串
    ("related_sectors", "TEXT"),   # JSON array 字符串
    ("related_tickers", "TEXT"),   # JSON array 字符串
    ("impact", "TEXT"),
    ("original_language", "TEXT"),
    ("translated", "INTEGER"),     # 0/1
]

# 各类别特有的额外字段
EXTRA_COLUMNS = {
    "china_mechanisms": [],
    "investor_speeches": [("speaker", "TEXT")],
    "academic_research": [
        ("authors", "TEXT"),              # JSON array
        ("original_title", "TEXT"),
        ("applicability_to_a_share", "TEXT"),
        ("limitations", "TEXT"),
    ],
    "industry_deep_dive": [("sector", "TEXT")],
    "event_cases": [("event_date", "TEXT")],
}


def _to_json_text(value):
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _to_bool_int(value):
    if isinstance(value, bool):
        return 1 if value else 0
    return value


def has_fts5(conn: sqlite3.Connection) -> bool:
    try:
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='records_fts'")
        # 尝试创建临时 FTS5 表来探测支持
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts5_test USING fts5(x)")
        conn.execute("DROP TABLE IF EXISTS _fts5_test")
        return True
    except sqlite3.OperationalError:
        return False


def create_table(conn: sqlite3.Connection, table: str, extra: list):
    columns = [f"{name} {dtype}" for name, dtype in COMMON_COLUMNS + extra]
    sql = f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(columns)})"
    conn.execute(sql)


def create_fts(conn: sqlite3.Connection, table: str):
    # 为每个表建立独立的 FTS5 虚拟表，便于按类别搜索
    fts_table = f"{table}_fts"
    conn.execute(f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS {fts_table} USING fts5(
            title,
            summary,
            content='{table}',
            content_rowid='rowid'
        )
    """)
    # 同步触发器
    conn.execute(f"""
        CREATE TRIGGER IF NOT EXISTS {table}_fts_insert AFTER INSERT ON {table}
        BEGIN
            INSERT INTO {fts_table}(rowid, title, summary)
            VALUES (new.rowid, new.title, new.summary);
        END
    """)
    conn.execute(f"""
        CREATE TRIGGER IF NOT EXISTS {table}_fts_delete AFTER DELETE ON {table}
        BEGIN
            INSERT INTO {fts_table}({fts_table}, rowid, title, summary)
            VALUES ('delete', old.rowid, old.title, old.summary);
        END
    """)
    conn.execute(f"""
        CREATE TRIGGER IF NOT EXISTS {table}_fts_update AFTER UPDATE ON {table}
        BEGIN
            INSERT INTO {fts_table}({fts_table}, rowid, title, summary)
            VALUES ('delete', old.rowid, old.title, old.summary);
            INSERT INTO {fts_table}(rowid, title, summary)
            VALUES (new.rowid, new.title, new.summary);
        END
    """)


def load_json(path: Path) -> list:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("records", [])
    return data


def insert_records(conn: sqlite3.Connection, table: str, records: list, extra_cols: list):
    common_names = [c[0] for c in COMMON_COLUMNS]
    extra_names = [c[0] for c in extra_cols]
    all_names = common_names + extra_names
    placeholders = ", ".join(["?"] * len(all_names))
    sql = f"INSERT OR REPLACE INTO {table} ({', '.join(all_names)}) VALUES ({placeholders})"

    extra_set = set(extra_names)
    rows = []
    for rec in records:
        row = []
        for col in common_names:
            val = rec.get(col)
            if col in ("tags", "key_points", "related_sectors", "related_tickers"):
                val = _to_json_text(val)
            elif col == "translated":
                val = _to_bool_int(val)
            row.append(val)
        for col in extra_names:
            val = rec.get(col)
            if col == "authors":
                val = _to_json_text(val)
            row.append(val)
        rows.append(row)
    conn.executemany(sql, rows)


def build():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")

    fts_supported = has_fts5(conn)
    total = 0
    stats = {}

    for table, filename in CATEGORY_FILES.items():
        path = RAW_DIR / filename
        if not path.exists():
            print(f"[skip] {path} not found")
            continue
        records = load_json(path)
        extra = EXTRA_COLUMNS.get(table, [])
        create_table(conn, table, extra)
        if fts_supported:
            create_fts(conn, table)
        insert_records(conn, table, records, extra)
        stats[table] = len(records)
        total += len(records)

    # 汇总表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            table_name TEXT PRIMARY KEY,
            count INTEGER,
            built_at TEXT
        )
    """)
    from datetime import datetime, timezone
    built_at = datetime.now(timezone.utc).isoformat()
    for table, count in stats.items():
        conn.execute(
            "INSERT OR REPLACE INTO stats (table_name, count, built_at) VALUES (?, ?, ?)",
            (table, count, built_at),
        )

    conn.commit()
    conn.close()

    print(f"[done] total={total} records written to {DB_PATH}")
    for table, count in stats.items():
        fts = "FTS5" if fts_supported else "no FTS5"
        print(f"  - {table}: {count} ({fts})")


if __name__ == "__main__":
    build()
