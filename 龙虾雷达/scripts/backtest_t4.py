"""
龙虾雷达 - T4 候选回测命中率脚本
========================================
用法:
  python scripts/backtest_t4.py            # 默认回填昨日
  python scripts/backtest_t4.py 20260423   # 指定日期
  python scripts/backtest_t4.py --stats    # 仅打印近 30 天统计

逻辑:
  1. 读 t4_candidates 表昨日（或指定日期）的所有候选
  2. 拉次日（即"今日"）实际开盘价 + 最高价
  3. 命中判定: 次日最高价 - 昨日收盘价 >= 1% (Wallace 打板偏好"次日有利润"即算命中)
  4. 回填 next_day_open, next_day_high, hit_target 三个字段
  5. 输出每档命中率 + 30 天累计统计

建议:
  Qclaw 配置每日 16:00 自动跑 (回填昨日)
"""
import os
# 关键: 关代理, 否则 Clash 拦截 AkShare
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""

import sys
import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "dedupe.sqlite"


def get_next_trading_day(target_date: date) -> date:
    """返回 target_date 之后的下一个交易日。
    简化版: 周末跳过, 不处理节假日 (生产可用 ak.tool_trade_date_hist_sina)
    """
    nxt = target_date + timedelta(days=1)
    while nxt.weekday() >= 5:  # 周六/日
        nxt += timedelta(days=1)
    return nxt


def fetch_quote_for_date(stock_code: str, target_date: date) -> dict:
    """拉取指定股票指定日期的开盘价和最高价。
    返回: {'open': float, 'high': float} 或 None (拉取失败)
    """
    try:
        import akshare as ak
        # AkShare 个股日 K (前复权)
        df = ak.stock_zh_a_hist(
            symbol=stock_code,
            period="daily",
            start_date=target_date.strftime("%Y%m%d"),
            end_date=target_date.strftime("%Y%m%d"),
            adjust="qfq",
        )
        if len(df) == 0:
            return None
        row = df.iloc[0]
        return {"open": float(row["开盘"]), "high": float(row["最高"])}
    except Exception as e:
        print(f"  [WARN] 拉取 {stock_code} @ {target_date} 失败: {e}")
        return None


def backfill_for_date(target_date: date) -> dict:
    """
    回填指定日期 t4_candidates 的次日数据
    返回: {'total': N, 'filled': M, 'hit': K, 'tier_stats': {...}}
    """
    next_day = get_next_trading_day(target_date)
    target_str = target_date.strftime("%Y-%m-%d")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT date, tier, stock_code, stock_name, score, entry_price
        FROM t4_candidates
        WHERE date = ?
    """, (target_str,))
    candidates = cur.fetchall()

    if not candidates:
        print(f"[INFO] {target_str} 无 T4 候选记录")
        conn.close()
        return {"total": 0, "filled": 0, "hit": 0}

    print(f"[INFO] {target_str} 有 {len(candidates)} 只候选, 拉次日 {next_day.strftime('%Y-%m-%d')} 数据回填...")

    filled = 0
    hit = 0
    tier_stats = {"A": {"n": 0, "hit": 0}, "B": {"n": 0, "hit": 0}, "C": {"n": 0, "hit": 0}}

    for c in candidates:
        quote = fetch_quote_for_date(c["stock_code"], next_day)
        if quote is None:
            continue

        # 命中判定
        # entry_price 是 T4 推荐的"明日开盘以下挂单"的参考价
        # 简化: 用昨日 entry_price 作为成本基准, 次日最高 / entry - 1 >= 1% 算命中
        entry = c["entry_price"] or quote["open"]  # 没记 entry 就用次日开盘当成本
        is_hit = (quote["high"] - entry) / entry >= 0.01

        cur.execute("""
            UPDATE t4_candidates
            SET next_day_open = ?, next_day_high = ?, hit_target = ?
            WHERE date = ? AND stock_code = ?
        """, (quote["open"], quote["high"], 1 if is_hit else 0, target_str, c["stock_code"]))

        filled += 1
        if is_hit:
            hit += 1
        tier = c["tier"]
        tier_stats[tier]["n"] += 1
        if is_hit:
            tier_stats[tier]["hit"] += 1

    conn.commit()
    conn.close()

    print(f"[OK] 回填 {filled}/{len(candidates)} 条")
    print(f"[OK] 命中 {hit}/{filled} ({hit / max(filled, 1) * 100:.1f}%)")
    for tier in ("A", "B", "C"):
        s = tier_stats[tier]
        if s["n"] > 0:
            print(f"  {tier} 档: {s['hit']}/{s['n']} ({s['hit'] / s['n'] * 100:.1f}%)")

    return {"total": len(candidates), "filled": filled, "hit": hit, "tier_stats": tier_stats}


def print_30day_stats():
    """打印近 30 天的命中率统计"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    thirty_days_ago = (date.today() - timedelta(days=30)).strftime("%Y-%m-%d")

    cur.execute("""
        SELECT tier, COUNT(*) AS total,
               SUM(CASE WHEN hit_target=1 THEN 1 ELSE 0 END) AS hit,
               AVG(score) AS avg_score
        FROM t4_candidates
        WHERE date >= ? AND hit_target IS NOT NULL
        GROUP BY tier
        ORDER BY tier
    """, (thirty_days_ago,))
    rows = cur.fetchall()

    print(f"\n========== 近 30 天 T4 命中率统计 ==========")
    print(f"统计起始: {thirty_days_ago}")
    print()
    if not rows:
        print("[INFO] 近 30 天暂无回填数据")
    else:
        print(f"{'档位':<6} {'总数':<8} {'命中':<8} {'命中率':<10} {'平均分':<8}")
        print("-" * 45)
        total_n, total_hit = 0, 0
        for r in rows:
            rate = r["hit"] / r["total"] * 100 if r["total"] else 0
            print(f"{r['tier']:<6} {r['total']:<8} {r['hit']:<8} {rate:>7.1f}%   {r['avg_score']:>6.1f}")
            total_n += r["total"]
            total_hit += r["hit"]
        print("-" * 45)
        if total_n:
            print(f"{'合计':<6} {total_n:<8} {total_hit:<8} {total_hit / total_n * 100:>7.1f}%")

    # 最近 3 天的具体表现
    cur.execute("""
        SELECT date, tier, COUNT(*) AS n,
               SUM(CASE WHEN hit_target=1 THEN 1 ELSE 0 END) AS hit
        FROM t4_candidates
        WHERE date >= date('now', '-3 days') AND hit_target IS NOT NULL
        GROUP BY date, tier
        ORDER BY date DESC, tier
    """)
    print(f"\n========== 最近 3 天 ==========")
    for r in cur.fetchall():
        print(f"  {r['date']}  {r['tier']} 档  {r['hit']}/{r['n']}")

    conn.close()


def main():
    args = sys.argv[1:]

    if "--stats" in args:
        print_30day_stats()
        return 0

    # 目标日期: 命令行第 1 个参数, 或默认昨日
    if args and len(args[0]) == 8 and args[0].isdigit():
        try:
            target = datetime.strptime(args[0], "%Y%m%d").date()
        except ValueError:
            print("[FAIL] 日期格式错误, 应为 YYYYMMDD")
            return 1
    else:
        target = date.today() - timedelta(days=1)
        # 如果"昨日"是周末, 回退到上周五
        while target.weekday() >= 5:
            target -= timedelta(days=1)

    print(f"========== T4 回测 - 目标日期 {target} ==========")
    result = backfill_for_date(target)
    print()
    print_30day_stats()
    return 0


if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"[FAIL] 数据库不存在: {DB_PATH}")
        print("[INFO] 请先跑: python scripts/init_dedupe_db.py")
        sys.exit(1)
    sys.exit(main())
