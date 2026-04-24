# 🦞 MILESTONE 3 - 5 个 Qclaw 任务提示词完成报告

> 状态: **完成** ✅
> 5 个提示词文件全部写完, 总计约 1700 行可执行细则
> 完成时间: 2026-04-24

---

## 1. 核心交付

| 文件 | 用途 | 行数 | 触发频率 |
|---|---|---|---|
| `prompts/T1_竞价情报.md` | 9:24 集合竞价情报扫描 | 220+ | 1 次/交易日 |
| `prompts/T2_早盘密集.md` | 9:30-10:30 黄金时段 5 分钟轮询 | 280+ | 13 轮/交易日 |
| `prompts/T3_盘中常规.md` | 10:30-15:00 守护型 10 分钟轮询 | 280+ | 27 轮/交易日 |
| `prompts/T4_收盘潜力.md` | 15:05 三档候选筛选（核心任务） | 380+ | 1 次/交易日 |
| `prompts/T5_临时问答.md` | "分析 XXX" 手动触发单股分析 | 260+ | 按需 |

---

## 2. 与文档原版的关键差异（重要）

### 2.1 全部用 AkShare 替代不存在的 DSA `/market/*`

按 BLOCKERS #2 的方案，5 个提示词中所有市场扫描类调用全部改为：

| 原文档 (DSA endpoint) | T1-T5 实际用 (AkShare) |
|---|---|
| `/api/v1/market/limit_up_today` | `ak.stock_zt_pool_em(date)` |
| `/api/v1/market/sectors` | `ak.stock_board_industry_summary_ths()` + `ak.stock_board_concept_em()` |
| `/api/v1/market/dragon_tiger_today` | `ak.stock_lhb_detail_em(start_date, end_date)` |
| `/api/v1/market/lianban_ranking` | `ak.stock_zt_pool_em()` 返回里的"连板数"字段排序 |
| `/api/v1/market/pre_market_quotes` | `ak.stock_zh_a_spot_em()` 9:25 后含竞价 |

**保留** DSA 的:
- `POST /api/v1/analysis/analyze` (T5 单股深度分析的核心)
- `GET /api/v1/stocks/{code}/quote` (T5 兜底快速报价)

### 2.2 每个提示词都强制前置代理处理

所有提示词的 Step 0 都包含：
```python
import os
os.environ['NO_PROXY'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
import requests
session = requests.Session()
session.trust_env = False
```

避免 Wallace 电脑的 Clash 拦截 AkShare HTTPS 请求。

### 2.3 每个提示词都有可执行的错误处理

不是文档原版的"如果失败 → 降级"四个字，而是表格化的具体降级路径：

```
| 失败场景 | 应对 |
|---|---|
| AkShare 涨停板池失败 | 用 spot_df 涨幅 > 9.8% 近似（精度下降，输出标"⚠️ 涨停数据降级"） |
| 龙虎榜失败 | 跳过游资判定，输出标"⚠️ 龙虎榜未取" |
| ...
```

---

## 3. 7 个必备元素全覆盖（按 MASTER_PROMPT 节 6.1）

| 元素 | T1 | T2 | T3 | T4 | T5 |
|---|---|---|---|---|---|
| 任务元数据 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 执行步骤（编号） | ✅ Step 0-7 | ✅ Step 0-7 | ✅ Step 0-8 | ✅ Step 0-8 | ✅ Step 1-4 |
| 数据源调用（具体 URL/库） | ✅ | ✅ | ✅ | ✅ | ✅ |
| 去重逻辑（dedupe.sqlite） | ✅ count | ✅ hash + count | ✅ hash + count | N/A（每日推 1 次） | N/A（手动） |
| 价值判定规则 | ✅ 全推 | ✅ C 宽松 | ✅ B 中等 | ✅ A/B/C 三档 | ✅ 全分析 |
| 输出格式模板 | ✅ JSON | ✅ A/B/C 三模板 | ✅ 标准+午后+尾盘 | ✅ 大富文本卡 | ✅ Markdown |
| 错误处理（具体降级） | ✅ 表格 | ✅ 表格 | ✅ 表格+13:00重试 | ✅ 表格+致命定义 | ✅ 表格 |

---

## 4. T4 的特别说明（最复杂）

T4 的"三档独立筛选"是 Wallace 业务核心，做了以下增强：

### 4.1 三档定义清晰化
- **A 档**: 纯量价（5-10 只，仓位 ≤ 5%）
- **B 档**: A + 当日催化（3-7 只，仓位 5-15%）
- **C 档**: B + 龙头属性（1-5 只，仓位 10-25%）
- 嵌套关系明确：C ⊂ B ⊂ A

### 4.2 龙头属性可执行判定
- "老龙头" = 该股近 30 天涨停 ≥ 2 次 + 是该板块涨停 Top 3
- "新龙头候选" = 当日连板 ≥ 2 + 封单/成交额 > 0.3

### 4.3 T4 专用评分（与 SKILL 节 3 不同）
- T4: 量价 40% / 消息 30% / 龙头 20% / 板块热度 10%（选股专用）
- SKILL 节 3: 政策 / 资金 / 研报 / 情绪 各 25 分（单股深度分析）
- 已在 T4 文档中显式说明两者差异，避免引用混淆

### 4.4 反向求证强制
- 对 A/B/C 各档前 3 名（最多 9 只）执行 SKILL 节 4 反向求证
- critical 级利空 → 直接踢出所有档（不只是降分）

### 4.5 时间预算
- 总耗时 40 分钟（15:05 启动，15:45 推完）
- 每阶段都有具体预算，超时硬截断保证一定推得出去

---

## 5. 自检（按 MASTER_PROMPT 6.7 验收清单）

- [x] 5 个提示词文件创建完成
- [x] 每个提示词都包含 7 个必备元素（见上节 3 表）
- [ ] CC 用一只测试股票（推荐 600519）模拟运行 T5 验证输出 - **延后到 M4 联调阶段**
- [ ] CC 模拟运行 T4 输出三档候选示例 - **延后到 M4 联调阶段**

延后说明: T5/T4 的"模拟运行"需要：
- DSA Web UI 已启动（M1.Step1.1 等 Wallace）
- AkShare 能稳定连接（M1.Step1.4 需要关 Clash）
- DeepSeek key 已配置（M1.Step1.2 等 Wallace）
- 飞书 Webhook 已配置（M1.Step1.3 等 Wallace）

这些都需要 Wallace 凑齐资料才能跑。M4 阶段会做这件事。

---

## 6. 下一步

**M4** - 联调测试与上线，包含：
- Step 4.1: Qclaw 任务导入指南（CC 写文档）
- Step 4.2: 单任务联调（需要 Wallace 配合在 Qclaw 导入 + 跑测试）
- Step 4.3: 1 周观察期（需要 Wallace 用飞书 + 反馈）
- Step 4.4: 回测命中率脚本（CC 写）

我能独立完成的（M4 中的）:
- 部署指南.md（Qclaw 任务导入分步图文）
- 调试手册.md
- backtest_t4.py 回测脚本
- 测试报告.md（待联调时填）

---

**报告人**: Claude Opus 4.7
**完成时间**: 2026-04-24
**下一步**: M4 - 写部署指南 + 回测脚本，等 Wallace 资料齐了联调
