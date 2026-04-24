"""
龙虾雷达 - 全数据源连通性测试
========================================
逐个测试以下数据源, 任何一个失败都不会中断, 最后给汇总：
  - AkShare      （免 key, 实时行情）
  - Tushare      （需 token, 优质数据）
  - DSA API      （本地 daily_stock_analysis, 核心后端）
  - DeepSeek     （主推理 LLM）
  - Gemini       （T4 复杂分析 LLM）
  - MiniMax      （搜索引擎）
  - 飞书 Webhook  （推送通道）

用法：
  把所有 key 填到 .env 后运行：python scripts/test_all_data_sources.py
"""
import os
import sys
from pathlib import Path

# ===== 关键: Wallace 电脑装了本地代理 (Clash/Mihomo 类), 拦截国内站点 =====
# 必须在 import requests/akshare 之前彻底关掉代理 (DSA main.py 也是这么做的)
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""
os.environ["ALL_PROXY"] = ""

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 加载 .env (如果存在)
ENV_FILE = PROJECT_ROOT / ".env"
if ENV_FILE.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE)
        # .env 里如果有空 PROXY 配置, 不要让它覆盖上面的禁用
        if not os.environ.get("HTTP_PROXY"):
            os.environ["HTTP_PROXY"] = ""
        if not os.environ.get("HTTPS_PROXY"):
            os.environ["HTTPS_PROXY"] = ""
        print(f"[INFO] 已加载 {ENV_FILE}\n")
    except ImportError:
        print("[WARN] 缺少 python-dotenv, 跳过 .env 自动加载")
        print("       pip install python-dotenv 后会更顺畅\n")


def safe(label: str, fn):
    try:
        ok, detail = fn()
        prefix = "[OK]  " if ok else "[FAIL]"
        print(f"{prefix} {label}: {detail}")
        return ok
    except Exception as e:
        print(f"[FAIL] {label}: 异常 {type(e).__name__}: {e}")
        return False


def test_akshare():
    import akshare as ak
    df = ak.stock_zh_a_spot_em()
    return (len(df) > 1000, f"拉到 {len(df)} 只 A 股实时行情")


def test_tushare():
    token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not token:
        return (False, "未配置 TUSHARE_TOKEN (可降级用 AkShare)")
    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api()
    # 第三方平台 (xiaodefa) 必须 monkey-patch base URL, 否则官方拒识 token
    provider = os.getenv("TUSHARE_PROVIDER", "").strip().lower()
    if provider == "xiaodefa":
        pro._DataApi__http_url = "http://tsy.xiaodefa.cn"
    df = pro.daily(ts_code="600519.SH", start_date="20260101", end_date="20260424")
    return (len(df) > 0, f"拉到贵州茅台 {len(df)} 条日线 [{provider or 'official'}]")


def test_dsa_api():
    import requests
    s = requests.Session()
    s.trust_env = False
    base = os.getenv("DSA_BASE_URL", "http://127.0.0.1:8000")
    # DSA 真实路径: /api/health 是健康, /api/v1/* 是业务
    for path in ["/api/health", "/api/v1/agent/strategies", "/"]:
        try:
            r = s.get(f"{base}{path}", timeout=5)
            if r.status_code == 200:
                return (True, f"{base}{path} -> HTTP 200")
        except Exception:
            continue
    return (False, f"{base} 健康检查全失败 (服务可能没启动)")


def test_deepseek():
    import requests
    key = os.getenv("LLM_PRIMARY_API_KEY", "").strip() or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not key:
        return (False, "未配置 LLM_PRIMARY_API_KEY / DEEPSEEK_API_KEY")
    r = requests.post(
        "https://api.deepseek.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": "deepseek-chat",
              "messages": [{"role": "user", "content": "ping"}],
              "max_tokens": 5},
        timeout=15,
    )
    return (r.status_code == 200, f"HTTP {r.status_code}")


def test_gemini():
    key = os.getenv("LLM_SECONDARY_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return (False, "未配置 LLM_SECONDARY_API_KEY / GEMINI_API_KEY")
    try:
        import google.generativeai as genai
    except ImportError:
        return (False, "缺少 google-generativeai 库")
    # gemini-2.0-flash-exp 已不存在, 用稳定版 gemini-2.0-flash
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    genai.configure(api_key=key)
    model = genai.GenerativeModel(model_name)
    resp = model.generate_content("ping", generation_config={"max_output_tokens": 5})
    return (bool(resp.text), f"模型 {model_name}, 响应: {resp.text[:30]}")


def test_minimax():
    import requests, json
    key = os.getenv("MINIMAX_API_KEYS", "").strip() or os.getenv("MINIMAX_API_KEY", "").strip()
    if not key:
        return (False, "未配置 MINIMAX_API_KEYS / MINIMAX_API_KEY")
    # 用国内站 chatcompletion_v2 (key 是 sk-cp-* Coding Plan 国内版)
    s = requests.Session()
    s.trust_env = False
    r = s.post(
        "https://api.minimax.chat/v1/text/chatcompletion_v2",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": "MiniMax-M1", "messages": [{"role": "user", "content": "ping"}],
              "max_tokens": 5, "stream": False},
        timeout=15,
    )
    if r.status_code != 200:
        return (False, f"HTTP {r.status_code}: {r.text[:120]}")
    body = r.json()
    base = body.get("base_resp", {})
    if base.get("status_code", 0) != 0:
        return (False, f"业务错误 {base.get('status_code')}: {base.get('status_msg')}")
    return (True, f"连通 (model=MiniMax-M1, id={body.get('id', '')[:10]}...)")


def test_feishu():
    """[DEPRECATED 2026-04-24] 龙虾雷达改为 Qclaw 原生推送, 不再走 Webhook
    保留函数签名避免 KeyError, 始终返回 'SKIPPED'
    """
    return (True, "SKIPPED (架构改为 Qclaw 原生推送, 不走 Webhook)")


if __name__ == "__main__":
    print("=" * 60)
    print("龙虾雷达 - 数据源连通性测试")
    print("=" * 60)

    results = []
    results.append(("AkShare",   safe("AkShare",   test_akshare)))
    results.append(("Tushare",   safe("Tushare",   test_tushare)))
    results.append(("DSA API",   safe("DSA API",   test_dsa_api)))
    results.append(("DeepSeek",  safe("DeepSeek",  test_deepseek)))
    results.append(("Gemini",    safe("Gemini",    test_gemini)))
    results.append(("MiniMax",   safe("MiniMax",   test_minimax)))
    results.append(("Feishu",    safe("Feishu",    test_feishu)))

    print("\n" + "=" * 60)
    print("汇总")
    print("=" * 60)
    for name, ok in results:
        mark = "[OK]  " if ok else "[FAIL]"
        print(f"{mark} {name}")

    critical = {"AkShare", "DSA API", "DeepSeek", "Feishu"}
    failed_critical = [n for n, ok in results if (not ok) and (n in critical)]

    if not failed_critical:
        print("\n[OK] 关键数据源全通, 可以进入 M2")
        sys.exit(0)
    else:
        print(f"\n[WARN] 关键数据源有失败: {failed_critical}")
        print("       记录到 BLOCKERS.md 并继续推进, 不中断流程")
        sys.exit(1)
