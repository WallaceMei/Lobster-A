# 🦞 龙虾雷达 - 优化待办池

> 上线运行 1 周后评估是否返工
> 创建: 2026-04-24
> 维护人: CC + Wallace

---

## 1. 决策原则

**当前阶段先按现有方案上线**, 1 周观察后再决定是否返工。

不返工的好处:
- 现有提示词 (T1-T5) 已经写完且经过 Opus 推理优化, 改动有引入 bug 风险
- AkShare 是万能兜底, 本身已能跑通, 只是不够"原生"
- 上线 1 周后能拿到真实命中率数据, 用数据驱动决策

---

## 2. 待优化项清单

### 2.0 [高优先级] 5 个提示词中的 DSA 返回结构引用要修正

**问题**: 提示词里引用了 `dashboard.data_perspective` / `dashboard.intelligence` / `dashboard.battle_plan`，
但 DSA 真实返回是:
```
report.meta             - query_id, stock_code, stock_name, current_price, change_pct
report.summary          - analysis_summary, operation_advice, trend_prediction, sentiment_score, sentiment_label
report.strategy         - 策略推荐
report.details          - 详细数据
```

**字段映射** (上线后用):
| 提示词中的引用 | DSA 实际字段 |
|---|---|
| `dashboard.core_conclusion` | `report.summary.analysis_summary` |
| `dashboard.data_perspective.trend` | `report.summary.trend_prediction` |
| `dashboard.intelligence` | `report.summary.sentiment_score` + `sentiment_label` |
| `dashboard.battle_plan.buy_price` | 在 `report.summary.operation_advice` 里 (text 描述, 需要 LLM 抽取) |
| (额外可用) | `report.strategy` (策略推荐), `report.details` (完整数据) |

**当前应对** (按 Wallace 指令不返工):
- M3 阶段先按现有提示词上线
- 提示词执行时 LLM 拿到 DSA 返回会发现字段不对, 自适应处理 (DeepSeek 推理力够)
- 上线 1 周后评估是否需要返工

**返工触发条件**: 上线后 T5/T4 推送内容明显空洞 / 字段全 N/A

---

### 2.1 [中优先级] T5 临时问答 → DSA Agent Chat 替代

**当前**: T5 自实现"DSA analyze + 小龙虾 SKILL 增强 + LLM 融合"三段式

**可替代为**: DSA 已内置 11 种策略 Agent, 通过 `POST /api/v1/agent/chat` 调用

```python
POST /api/v1/agent/chat
body: {"stock_code": "600519", "skills": ["bull_trend", "ma_golden_cross", "shrink_pullback"]}
```

**评估收益**:
- ✅ 减少自实现, 复用 DSA 已经做好的策略推理
- ✅ DSA 的 strategies 列表更全 (含缠论、波浪理论、情绪周期)
- ❌ 损失"小龙虾反向求证 + 红线扫描"的强制性 (可能要在 chat 提示词里手动嵌入)
- ❌ 输出格式可能不可控 (Agent 自由发挥)

**返工触发条件**: 上线 1 周后 T5 用户体验差 / 输出质量低于 DSA 内置 Agent

---

### 2.2 [中优先级] backtest_t4.py → DSA Backtest API 替代

**当前**: 自实现, 直接拉 AkShare 历史 K 比对 entry 价 vs next_day_high

**可替代为**: DSA 有完整回测模块

```python
POST /api/v1/backtest/run
GET  /api/v1/backtest/results
GET  /api/v1/backtest/performance/{code}
```

**评估收益**:
- ✅ DSA 回测引擎可能比简单 1% 命中规则更复杂 (含夏普比率/最大回撤等)
- ✅ 数据来源统一 (避免 AkShare 与 DSA 数据源不一致导致的差异)
- ❌ DSA 回测的"命中"定义可能与 Wallace "次日有 1% 利润即算命中" 不同
- ❌ 需要先研究 DSA backtest 的 API contract

**返工触发条件**: T4 命中率统计需求超出当前简单脚本能力 (如要看夏普 / 回撤)

---

### 2.3 [低优先级] T1/T2/T3 单股查询 → /stocks/{code}/quote 替代 AkShare

**当前**: T1 拉竞价用 `ak.stock_zh_a_spot_em()` (全 A 股), T2/T3 单股查询也用 AkShare

**可替代为**: DSA `GET /api/v1/stocks/{code}/quote` (单股快速报价)

**评估收益**:
- ✅ DSA 内部已处理代理 (Wallace 不用关 Clash)
- ✅ DSA 内部按优先级 (efinance > akshare > tushare > pytdx) 自动 fallback
- ❌ 单股查询 API 不适合"全市场扫描"场景 (T1 的高开异动 TOP 30, T4 的 A 档筛选)
- ❌ 需要循环调用 N 次, 慢且占用 DSA 资源

**结论**: **不返工**。AkShare 在 batch 场景更高效, DSA 单股 API 更适合 T5。

---

### 2.4 [低优先级] T4 涨停板/板块榜 → 保留 AkShare

**当前**: T4 用 `ak.stock_zt_pool_em` / `ak.stock_board_*`

**评估**: DSA 没有对应模块, 必须保留 AkShare。

**结论**: **不返工**。

---

### 2.5 [中优先级] DSA 原生不支持 MiniMax 搜索

**当前**: DSA .env 支持 Tavily/SerpAPI/Brave, 但不支持 MiniMax

**Wallace 提供的是 MiniMax key**

**应对方案** (3 选 1):
- 方案 1: Wallace 注册 Tavily / Brave (有免费额度), 把 MiniMax 留给小龙虾 SKILL 自己调用
- 方案 2: 在 DSA 加自定义 SearchProvider 接入 MiniMax (改 DSA 代码, 有维护负担)
- 方案 3: 完全不用 DSA 的搜索, 让 5 个提示词全部走小龙虾 SKILL 内的 MiniMax 调用

**当前选择 (M1 阶段)**: 方案 3 (最少改动)

**返工触发条件**: 上线后发现 DSA `/analysis/analyze` 因为没搜索而内容空洞

---

### 2.6 [已废弃 2026-04-24] 飞书推送方案

**最终架构: Qclaw 原生通道** (既不是 Webhook, 也不是 App 机器人)

理由:
- Wallace 测试发现 Qclaw 客户端"飞书消息"对话框已能与飞书双向通信 → Qclaw 平台已接入飞书
- 5 个提示词输出 Markdown, Qclaw 自动转发到飞书
- 零外部依赖, 不需要管理 Webhook URL / access_token

详见 `BLOCKERS.md` ✅ #7 已解决。

**未来可能升级**:
- Qclaw 通道有限制 (消息长度/频率/格式) → 启用 DSA 内置 lark-oapi 走 App 机器人
- 需要多群多渠道 → 加 PushPlus / Telegram

---

## 3. 不返工的项目（明确决策）

| 项 | 不返工的理由 |
|---|---|
| AkShare 涨停板池 | DSA 无对应接口, 别无选择 |
| AkShare 板块榜 | 同上 |
| AkShare 龙虎榜 | 同上 |
| 小龙虾 SKILL v4.0 完全自实现 | DSA 没有"反向求证 + 红线扫描"的强制契约, 必须自己写 |
| dedupe.sqlite 自实现 | DSA 没有去重数据库, 必须自己建 |

---

## 4. 评估时间表

| 时间 | 行动 |
|---|---|
| 上线后 D+1 ~ D+7 | 每天观察推送质量 + 命中率 |
| 上线后 D+7 (1 周复盘) | Wallace 决定哪些待办项要返工 |
| 返工前 | CC 写各项的 RFC, Wallace 决策 |

---

**最后更新**: 2026-04-24
**下次评估**: 上线后 1 周
