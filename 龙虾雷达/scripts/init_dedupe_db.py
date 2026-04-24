"""
龙虾雷达 - 去重数据库初始化
========================================
建表：
  - pushed_news       已推送消息哈希表（防重复推送）
  - daily_push_count  每日各任务推送计数（控制上限）
  - t4_candidates     T4 候选历史表（用于次日命中率回测）

用法：python scripts/init_dedupe_db.py
"""
import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dedupe.sqlite"


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS pushed_news (
            hash       TEXT PRIMARY KEY,
            title      TEXT,
            source     TEXT,
            pushed_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
            task_name  TEXT
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_pushed_news_pushed_at ON pushed_news(pushed_at)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_push_count (
            date       TEXT,
            task_name  TEXT,
            count      INTEGER DEFAULT 0,
            PRIMARY KEY (date, task_name)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS t4_candidates (
            date           TEXT,
            tier           TEXT,
            stock_code     TEXT,
            stock_name     TEXT,
            score          REAL,
            sector         TEXT,
            catalyst       TEXT,
            entry_price    REAL,
            stop_loss      REAL,
            next_day_open  REAL,
            next_day_high  REAL,
            hit_target     INTEGER,
            PRIMARY KEY (date, stock_code)
        )
    """)

    conn.commit()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]
    conn.close()

    print(f"[OK] 数据库初始化完成: {DB_PATH}")
    print(f"[OK] 已创建表: {tables}")


if __name__ == "__main__":
    try:
        init_db()
    except Exception as e:
        print(f"[FAIL] 初始化失败: {e}", file=sys.stderr)
        sys.exit(1)
