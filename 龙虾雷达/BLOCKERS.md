# 🚧 龙虾雷达 - 阻塞与重大发现记录

> 每条阻塞: 当时上下文 + 已尝试方案 + 当前应对 + 是否需要 Wallace 决策

---

## ✅ [2026-04-24] 已解决 #1 - daily_stock_analysis 安装路径

**解决**: `C:/Users/m7856/daily_stock_analysis/`
- 入口: `webui.py` (端口 8000)
- API: FastAPI, prefix `/api/v1`
- Wallace 用 `py -3.10` 启动

---

## 🚨 [2026-04-24] 重大发现 #2 - DSA 没有 /api/v1/market/* 接口

**应对**: 5 个提示词全部用 AkShare 替代 (zt_pool / lhb_detail / board_industry / board_concept)。
保留 DSA 的 /analysis/analyze 和 /stocks/{code}/quote。

详见 docs/OPTIMIZATION_BACKLOG.md。

---

## ⚠️ [2026-04-24] 已知 #3 - 本地 Clash 代理拦截 eastmoney HTTPS

**应对**: 所有脚本顶部 `os.environ['NO_PROXY']='*'` + `Session(trust_env=False)`。
DSA 自己已处理 (main.py 顶部默认 NO_PROXY=*)。
测试时 Wallace 临时关 Clash 即可。

---

## ✅ [2026-04-24] 已收齐 #4 - Wallace 凭据已提供

5 keys + 飞书 App 凭据已配置到:
- `C:/quant_project/龙虾雷达/config/secrets.env` (源文件)
- `C:/quant_project/龙虾雷达/.env` (项目运行用)
- `C:/Users/m7856/daily_stock_analysis/.env` (DSA 用)

仍待提供:
- ⏳ 持仓 + 盯盘池真实截图 (当前用 沪深300 头部 10 只 + 题材龙头 8 只 占位, status=PLACEHOLDER)
- ⏳ 飞书 Webhook URL (Wallace 待创建; 推荐方案 B 见 BLOCKER #7)

---

## 🟡 [2026-04-24] 待 Wallace 决策 #6 - DSA Tushare 调用方式需要 patch

**问题**: Wallace 提供的 Tushare token 来自第三方 `http://tsy.xiaodefa.cn`, 不是官方 api.tushare.pro。
- 已验证: token + monkey-patch base URL → 成功拉到 600519 5 日日线 ✅
- 已验证: token 直接走官方 api.tushare.pro → 失败 "您的token不对" ❌

**DSA 现状** (`data_provider/tushare_fetcher.py`):
- 第 155 行硬编码 `TUSHARE_API_URL = "http://api.tushare.pro"`
- 已有 `_patch_api_endpoint` 方法 (绕过 SDK 默认的 waditu)
- DSA 拉 Tushare 时会失败, **会自动降级到 AkShare/efinance** (data_provider 多源策略)

**3 个选项 (Wallace 决策)**:

### Option A (推荐 - 最小侵入)
**改 DSA 一行**: `data_provider/tushare_fetcher.py` 第 155 行
```python
# 原: TUSHARE_API_URL = "http://api.tushare.pro"
# 改: TUSHARE_API_URL = os.getenv("TUSHARE_API_URL", "http://api.tushare.pro")
```
然后在 DSA 的 .env 加 `TUSHARE_API_URL=http://tsy.xiaodefa.cn`。
- ✅ 永久解决, DSA 也能用 Tushare 数据
- ⚠️ 改了 DSA 上游源码, DSA 升级时可能被覆盖 (可记到笔记里, 升级后重做)

### Option B (零侵入)
**不改 DSA, 让 DSA 的 Tushare 失败降级**, 仅 Wallace 项目内的脚本用 Tushare (已实现, `TUSHARE_PROVIDER=xiaodefa` 触发 monkey-patch)
- ✅ 完全不动 DSA
- ❌ DSA 内部分析时拿不到 Tushare 数据 (会用 AkShare/efinance, 数据质量略降但能跑)

### Option C (升级到官方)
让 Wallace 在 https://tushare.pro 注册官方账号
- ✅ 一切官方, 无 patch
- ❌ 官方 Tushare Pro 高级数据需要积分/付费

**当前默认走 Option B** (零侵入, 不阻塞 M1)。Wallace 一声令下即可改 Option A。

**Wallace 决策点**: 是 - 选 A/B/C

---

## ✅ [2026-04-24] 已解决 #7 - 飞书推送方案: 改 Qclaw 原生通道

**最终决策**: **方案 C (Qclaw 原生通道)** - 既不是 Webhook 也不是 App 机器人

**触发**: Wallace 测试发现 Qclaw 客户端"飞书消息"对话框已能与飞书双向通信
→ Qclaw 平台自身已接入飞书, 任务输出可自动转发

**改动**:
- ✅ 5 个提示词 (T1-T5) 全部重写"推送"章节
  - 删除 JSON interactive card 模板
  - 改为输出 Markdown 格式的最终报告
  - 删除所有 POST Webhook 步骤
- ✅ `scripts/verify_feishu.py` → `.deprecated` 归档
- ✅ `config/feishu_webhook.txt` → `.deprecated` 归档
- ✅ DSA `.env` 注释 `CUSTOM_WEBHOOK_URLS` 和 `FEISHU_WEBHOOK_URL`
- ✅ `docs/部署指南.md` B.2 章节重写为"Qclaw 远控通道配置"
- 🔇 飞书 App ID/Secret 仍保留在 DSA `.env` (应急回退备用)
- ⚠️ 微信通道按 Wallace 决策暂不配置

---

## 🟡 [2026-04-24] 待 Wallace 关注 #8 - DSA 不原生支持 MiniMax 搜索

**问题**: Wallace 提供的搜索 key 是 MiniMax, 但 DSA `.env` 只支持 Tavily/SerpAPI/Brave

**应对**: 不在 DSA 接入 MiniMax (改 DSA 代码成本高), 让小龙虾 SKILL 在 T1-T5 自己调 MiniMax
- ✅ 已在 `.env` 配置 `MINIMAX_API_KEYS`
- ✅ test_all_data_sources.py 单独测 MiniMax 连通性
- ⚠️ DSA `/analysis/analyze` 自带的"消息面"段会因为没搜索 key 而内容空洞 (但有 LLM 推理兜底)

**Wallace 决策点**: 否 (技术细节, CC 自行决定)。
**长期优化**: 考虑申请免费的 Tavily / Brave key, 让 DSA 也能搜索

---

## 🟡 [2026-04-24] 待 Wallace 操作 #9 - DSA 必须重启才能加载新 .env

**问题**: DSA 用 dotenv 在进程启动时一次性加载 .env, 不支持 hot-reload

**应对**: 我已更新 DSA 的 .env, 但 Wallace 当前的 webui.py 进程是更新前启动的, 用的还是旧配置 (空 LLM key)。

**Wallace 必须做**:
1. 在 DSA 运行的 PowerShell 窗口按 `Ctrl+C` 关闭
2. 重新运行: `py -3.10 webui.py`
3. 看到启动日志包含 "Tushare/Gemini/OpenAI 配置已加载" 类似提示

**未做这一步前**: DSA 的 /analysis/analyze 不可用 (会因为没有 LLM 而失败)

**Wallace 决策点**: 是 - 必须操作

---
