---
name: lobster-skill
description: LobsterRadar A股全域情报系统 - 消息情报+数据融合+反向求证，专为打板策略设计
version: "4.0.0"
author: Wallace
trigger_keywords:
  - 龙虾雷达
  - 股票分析
  - 分析
  - 板块
  - 涨停
  - 情报
  - 打板
  - A股
category: finance
tags:
  - a-stock
  - trading
  - sentiment-analysis
---


# 🦞 小龙虾 SKILL v4.0

> **使命**: Wallace 的 A 股盘中/盘后情报方法论。把"判断"翻译成"算法"，把"双重确认"翻译成"if-then 检查"。
>
> **绝对原则**: 本 SKILL 只产出**信息和评分**，**不产出"买/卖"指令**。决策权 100% 在 Wallace。

---

## 0. v3.0 → v4.0 升级清单（已逐项落实）

| 问题 | v3.0 现状 | v4.0 解决方案 |
|---|---|---|
| 数据源描述模糊 | "金十数据""韭研公社"几个字带过 | 显式列 URL/API/搜索词/返回字段，每条数据源单独成节 |
| 验证规则空话 | 写"双重确认" | 拆成"时间窗 + 关键词匹配 + 容差"三段判定 |
| 评分公式拍脑袋 | 4 维 0.4/0.3/0.2/0.1 加权 | 4 维各 25 分锚点制（每个分档有客观判据） |
| 红线扫描跑不动 | "1 分钟跌 5%" 这种实时规则盘后没意义 | 改为"公告事件型"红线（立案/ST/停牌等） |
| 输出格式过载 | 一个大模板，啥场景都用 | 拆 3 套：早盘速读 / 突发简报 / 盘后深度 |
| 缺反向求证 | 只搜利好，不搜利空 | 强制反向搜索 5 类利空关键词 |
| **新增**：DSA 接口假设错误 | 文档假设 `/api/v1/market/*` 存在 | 实际不存在，市场全景类全部用 AkShare |
| **新增**：本地代理干扰 | 没考虑 | Wallace 电脑装 Clash，所有 requests 调用要 `trust_env=False` |
| **新增**：缺失败降级 | 一处失败整体崩 | 每条数据源都有"降级"和"跳过"路径 |
| **新增**：SKILL 调用契约 | 模糊"被任务调用" | 显式 input schema + output schema |

---

## 1. 数据源协议（显式可执行）

### 1.1 数据源表（按信任度排序）

| ID | 名称 | 用途 | 信任度 | 访问方式 | 失败降级 |
|---|---|---|---|---|---|
| DS1 | 上交所/深交所公告 | 立案/ST/停牌等官方披露 | ★★★★★ | web_fetch | 跳过该项，标 [无公告数据] |
| DS2 | DSA `/analysis/analyze` | 单股深度分析（量价/筹码/资金流） | ★★★★★ | POST 本地 API | 改用 AkShare 拼凑基础字段 |
| DS3 | DSA `/stocks/{code}/quote` | 单股实时报价 | ★★★★ | GET 本地 API | AkShare `stock_zh_a_spot_em` 过滤 |
| DS4 | AkShare `stock_zt_pool_em` | 涨停板池（含连板数） | ★★★★ | 直接库调用 | 改用东财抓取或跳过 |
| DS5 | AkShare `stock_lhb_detail_em` | 龙虎榜明细 | ★★★★ | 直接库调用 | 跳过，标 [龙虎榜未取] |
| DS6 | AkShare `stock_board_*` | 行业/概念板块涨幅 | ★★★★ | 直接库调用 | 跳过，标 [板块数据缺失] |
| DS7 | 金十数据 | 政策/事件实时快讯 | ★★★★ | web_search "site:jin10.com" | 改用 MiniMax 搜索 |
| DS8 | MiniMax 搜索 | 综合搜索 + 结构化结果 | ★★★ | DSA 内置 SearchService | 改用通用 web_search |
| DS9 | 雪球热议 | 散户情绪验证（**仅交叉验证用，不单独决策**） | ★★ | web_search "site:xueqiu.com" | 跳过 |

### 1.2 每条数据源的细则

#### DS1 - 上交所/深交所公告
```yaml
名称: 交易所公告
用途: 立案/ST/退市/停牌等官方披露 — 红线扫描的唯一可信来源
访问:
  上交所:
    日股票公告: web_fetch "http://www.sse.com.cn/disclosure/listedinfo/announcement/"
    指定证券: web_fetch "http://www.sse.com.cn/disclosure/listedinfo/announcement/?stockCode={code}"
  深交所:
    日股票公告: web_fetch "http://www.szse.cn/disclosure/listed/notice/"
    巨潮资讯网（更全）: web_fetch "http://www.cninfo.com.cn/new/disclosure/stock?stockCode={code}"
抓取窗口: 当日 + 前 1 个交易日
关键词优先级（高→低）:
  P0_红线: ["立案调查", "ST 风险警示", "*ST", "退市风险", "重大资产重组停牌"]
  P1_重大: ["业绩预告", "重大合同", "中标", "增持", "回购", "股权激励"]
  P2_一般: ["公告日期", "投资者关系", "诉讼仲裁"]
返回数据归一化字段: [发布时间, 公告标题, 公告类型, 涉及股票代码]
```

#### DS2 - DSA `/api/v1/analysis/analyze`
```yaml
名称: daily_stock_analysis 单股深度分析
用途: T5 临时问答 + T4 候选股深度盘后复盘的核心数据来源
访问:
  POST http://127.0.0.1:8000/api/v1/analysis/analyze
  Content-Type: application/json
  Body示例: {"stock_code": "600519", "async_mode": false}
  超时: 60 秒（首次冷启动可能更慢）
返回结构（dashboard 字段）:
  - core_conclusion: 核心结论一句话
  - data_perspective:
      trend: 趋势描述
      price_position: 价格位置
      volume: 量能
      chips: 筹码
  - intelligence: 消息面汇总（DSA 自带的 LLM 已做了一遍）
  - battle_plan:
      buy_price: 建议买入价
      stop_loss: 止损价
      target_price: 目标价
失败处理:
  - HTTP 5xx: 重试 1 次，仍失败则降级到 DS3 + DS4 拼凑基础字段
  - HTTP 4xx: 直接报"标的代码不存在或无数据"
  - 超时: 降级到只用 DS3 实时报价
```

#### DS3 - DSA `/api/v1/stocks/{code}/quote`
```yaml
名称: DSA 单股报价
用途: 快速获取单股实时价格/涨跌幅，<1 秒响应
访问:
  GET http://127.0.0.1:8000/api/v1/stocks/{code}/quote
  示例: GET .../stocks/600519/quote
返回: 价格、涨跌幅、成交量、最近一笔时间
```

#### DS4 - AkShare 涨停板池
```yaml
名称: 涨停板池（含连板梯队）
用途: T1 竞价后涨停回顾 / T4 选股全市场扫描
调用:
  import akshare as ak
  df = ak.stock_zt_pool_em(date='20260424')   # YYYYMMDD
返回字段（关键）:
  - 序号, 代码, 名称, 涨跌幅, 最新价, 成交额
  - 流通市值, 总市值
  - 换手率
  - 封板资金, 首次封板时间, 最后封板时间
  - 炸板次数
  - 涨停统计 (例: "3/5" = 5 天 3 次涨停)
  - 连板数
  - 所属行业
连板梯队提取（替代不存在的 /market/lianban_ranking）:
  按 "连板数" 降序，分组：
  - 4 板及以上: 高度梯队（一日游风险高）
  - 3 板: 中坚梯队
  - 2 板: 接力梯队
  - 1 板（首板）: 启动梯队（Wallace 主战场）
失败处理:
  - 非交易日: AkShare 会返回空 DataFrame，标 [非交易日，跳过]
  - 网络失败: 重试 1 次，仍失败则用 DS3 spot 替代（精度下降）
代理: 调用前必须 `os.environ['NO_PROXY']='*'` + 用 trust_env=False Session
```

#### DS5 - AkShare 龙虎榜
```yaml
名称: 龙虎榜明细
用途: T4 候选股的"游资买入"信号验证
调用:
  df = ak.stock_lhb_detail_em(start_date='20260424', end_date='20260424')
返回字段（关键）:
  - 代码, 名称, 上榜日, 收盘价, 涨跌幅
  - 上榜原因
  - 买入金额, 卖出金额, 净额, 成交额
  - 买方营业部 list / 卖方营业部 list（用于识别游资席位）
游资席位识别（白名单）:
  - "中国国际金融上海分公司"（拉萨天团 - 顶级游资聚集）
  - "国信证券股份有限公司深圳泰然九路营业部"（八大金刚 - 章盟主席位）
  - "华泰证券股份有限公司南京浦口大道营业部"（炒股养家系）
  - "东方财富证券股份有限公司拉萨团结路第二营业部"（拉萨天团）
  - "财通证券股份有限公司杭州大路营业部"（赵老哥附近席位）
  - "光大证券绍兴营业部"（绍兴帮）
判定:
  - 命中 ≥1 个白名单席位 → "游资关注"标签 +5 分
  - 命中 ≥2 个白名单席位 → "游资接力"标签 +10 分
失败处理: 跳过此项，标 [龙虎榜未取]
```

#### DS6 - AkShare 板块涨幅榜
```yaml
名称: 行业 + 概念板块涨幅
用途: T1/T2/T3 识别热点板块；T4 用于评分维度 4
调用:
  行业板块: df_industry = ak.stock_board_industry_summary_ths()
  概念板块: df_concept = ak.stock_board_concept_em()
返回字段（关键）:
  - 板块名称, 涨跌幅, 总成交额
  - 上涨家数, 下跌家数
  - 领涨股, 领涨股涨跌幅
真热点判定（双时点验证）:
  9:30 时点记录 Top 20 板块名单 → 写到 logs/sectors_0930.json
  10:00 时点再记录一次 → 写到 logs/sectors_1000.json
  两份名单都进 Top 10 的板块 → 标记 "真热点"，避免一日游
失败处理: 跳过，标 [板块数据缺失]，后续步骤如依赖板块则用"个股涨停统计"近似替代
```

#### DS7 - 金十数据
```yaml
名称: 金十数据快讯
用途: 政策/事件类实时快讯
访问:
  方式 A（推荐）: web_search "金十 [关键词] site:jin10.com" 时间过滤近 4 小时
  方式 B（备用）: web_fetch "https://www.jin10.com/" → 解析最新快讯流
抓取范围: 最近 4 小时
必抓字段: [发布时间, 标题, 内容摘要, 来源标签 ★/★★/★★★]
排除关键词（不是 A 股相关，直接丢弃）:
  ["美股", "纳斯达克", "外汇", "美元指数", "原油", "比特币", "加密"]
注意: 金十的红色标签 ★★★ 是其编辑认为的"高重要性"，可作为优先排序参考但不能完全信任
```

#### DS8 - MiniMax 搜索
```yaml
名称: MiniMax Web Search
用途: 当 web_search 返回质量差时的兜底，或需要结构化结果时
访问: 通过 DSA 已配置的 SearchService 调用（DSA 内部已封装）
适用: 综合搜索 + 跨源汇总
```

#### DS9 - 雪球
```yaml
名称: 雪球热议
用途: 散户情绪信号 — 仅用作"评分维度 4 - 情绪/技术"的输入之一
访问: web_search "[股票名] 雪球 site:xueqiu.com"
关键限制:
  - 雪球水军极多，**不信任内容文字**
  - **只看热度信号**: 评论数、转发数、热度趋势
  - 任何雪球内容**不能单独作为推送依据**，必须有 DS1/DS7/DS6 的支撑
```

---

## 2. 交叉验证规则（每条都是 if-then 算法）

### 2.1 规则 R1 - 政策利好双重确认

```python
def verify_policy_news(news_item) -> ConfidenceLevel:
    """
    输入: 单条政策类新闻 (来源、时间、内容)
    输出: 'CONFIRMED' / 'SINGLE_SOURCE' / 'RUMOR'
    """
    # Step 1: 在金十找原文
    jin10_match = web_search(f"金十 {news_item.keywords} site:jin10.com")
    has_jin10 = len(jin10_match) > 0
    
    # Step 2: 在交易所/官方找文件
    official_match = web_search(f"{news_item.keywords} site:sse.com.cn OR site:szse.cn OR site:csrc.gov.cn")
    has_official = len(official_match) > 0
    
    # Step 3: 时间间隔检查
    time_diff_ok = (
        abs(jin10_match[0].time - official_match[0].time).hours < 6
        if (has_jin10 and has_official) else False
    )
    
    # Step 4: 内容一致性检查（金额/范围/对象，容差 ±10%）
    content_consistent = check_consistency(
        jin10_match[0].content,
        official_match[0].content,
        tolerance=0.10
    ) if (has_jin10 and has_official) else False
    
    # 判定
    score = sum([has_jin10, has_official, time_diff_ok, content_consistent])
    if score == 4:
        return 'CONFIRMED'      # 高可信，可推送
    elif score == 3:
        return 'SINGLE_SOURCE'  # 标"待验证"再推
    else:
        return 'RUMOR'          # 不推送
```

### 2.2 规则 R2 - 题材炒作判定

```python
def verify_theme_hype(sector_name: str) -> ThemeStatus:
    """
    输入: 板块名（如"AI算力"）
    输出: 'CONFIRMED' / 'BREWING' / 'ONE_DAY_TRIP'
    """
    # 触发条件: 该板块在涨幅榜 Top 10 + 涨停 ≥ 3 只
    sector_rank = get_sector_rank(sector_name)
    limit_up_count = count_limit_up_in_sector(sector_name)
    if not (sector_rank <= 10 and limit_up_count >= 3):
        return 'NOT_TRIGGERED'
    
    # 三个验证维度
    has_policy = bool(search_policy_for_sector(sector_name))    # 政策催化
    has_event = bool(search_event_for_sector(sector_name))      # 事件催化
    has_money = check_capital_flow(sector_name) > THRESHOLD     # 资金流入

    score = sum([has_policy, has_event, has_money])
    if score == 3:
        return 'CONFIRMED'      # 题材确立，可重点关注
    elif score == 2:
        return 'BREWING'        # 题材发酵中，谨慎跟进
    else:
        return 'ONE_DAY_TRIP'   # 一日游风险高，警惕
```

### 2.3 规则 R3 - 业绩预告交叉验证

```python
def verify_earnings_forecast(stock_code, forecast) -> EarningsImpact:
    """
    输入: 业绩预告原文
    输出: 'MAJOR_BEAT' / 'MAJOR_MISS' / 'NORMAL'
    """
    yoy_change = parse_yoy_change(forecast)        # 同比变化
    qoq_change = parse_qoq_change(forecast)        # 环比变化
    consensus = get_analyst_consensus(stock_code)  # 机构一致预期（可空）
    
    # 同比超预期
    if yoy_change > 0.5 and (consensus is None or yoy_change > consensus * 1.2):
        return 'MAJOR_BEAT'
    if yoy_change < -0.5:
        return 'MAJOR_MISS'
    if abs(yoy_change) < 0.2:
        return 'NORMAL'
    return 'NORMAL'
```

---

## 3. 风险评分（4 维 25 分锚点制 = 0-100）

### 3.1 维度 1: 政策维度（0-25 分）

| 分数 | 锚点判据（必须命中其一） |
|---|---|
| 25 | 国务院/证监会/部委正式文件，明确利好该题材，发文 24 小时内 |
| 20 | 地方政府正式文件 / 部委吹风稿（媒体引用部委官员表态） |
| 15 | 行业协会文件 / 央媒（新华社、人民日报）专题报道 |
| 10 | 一般媒体报道 / 自媒体引述未官宣 |
| 5 | 网传、小道消息，无明确来源 |
| 0 | 无政策维度信息 |

### 3.2 维度 2: 资金维度（0-25 分）

数据来源: DSA `/analysis/analyze` 返回的 `data_perspective.volume` + AkShare 龙虎榜

| 分数 | 判据 |
|---|---|
| 25 | 主力净流入 > 5 亿 + 北向资金同向流入 + 龙虎榜白名单游资 ≥ 2 个 |
| 20 | 主力净流入 1-5 亿 + 龙虎榜有白名单游资 |
| 15 | 主力净流入 0.5-1 亿 |
| 10 | 主力净流入 < 0.5 亿 OR 主力/北向方向矛盾 |
| 5 | 主力净流出 0-1 亿 |
| 0 | 主力净流出 > 1 亿 |

### 3.3 维度 3: 研报/机构维度（0-25 分）

数据来源: DSA `/analysis/analyze` 的 `intelligence` + web_search 搜研报

| 分数 | 判据 |
|---|---|
| 25 | ≥3 家头部券商（中信/中金/华泰/招商/广发/国泰君安）一致评级"买入"+ 至少 1 家上调目标价 |
| 20 | 1-2 家头部券商最新覆盖（30 天内）"推荐/买入" |
| 15 | 非头部券商最新覆盖 |
| 10 | 无最新研报但 90 天内有历史覆盖 |
| 5 | 仅有简短点评 / 公开信息有限 |
| 0 | 无研报覆盖 OR 近期被下调评级 |

### 3.4 维度 4: 情绪/技术维度（0-25 分）

数据来源: DSA + AkShare 板块数据 + 雪球热度

| 分数 | 判据 |
|---|---|
| 25 | 雪球评论 24h 增长 > 50% + 所属板块涨幅 > 5% + 当日量比 > 3 + MA5/MA10/MA20 多头排列 |
| 20 | 上述三项中满足两项 |
| 15 | 上述三项中满足一项 |
| 10 | 量价正常无明显信号 |
| 5 | 出现砸盘/出逃迹象（尾盘大单卖出 / 主力净流出加速） |
| 0 | 重大利空发酵中（雪球负面热度 > 正面） |

### 3.5 总分分档

| 总分 | 标签 | 处理 |
|---|---|---|
| 80-100 | ⭐⭐⭐⭐⭐ 强信号 | T1-T3 推送、T4 进 C 档 |
| 60-79 | ⭐⭐⭐⭐ 可关注 | T1-T3 推送、T4 进 B 档 |
| 40-59 | ⭐⭐⭐ 待验证 | T2/T3 不主动推、T4 进 A 档 |
| 20-39 | ⭐⭐ 噪音 | 不推送，仅日志 |
| 0-19 | ❌ 风险标的 | 触发反向求证检查，可能加入"避雷名单" |

---

## 4. 反向求证模块（强制前置）

每次输出报告前，对**主要候选股 / 主要板块 Top 3**强制执行：

```python
REVERSE_KEYWORDS = [
    "{name} 风险",
    "{name} 减持",
    "{name} 立案",
    "{name} 问询函",
    "{name} 利空",
    "{name} 减持公告",
    "{theme} 泡沫",
    "{theme} 见顶",
]

def reverse_verify(target_name: str, target_type: str) -> List[ReverseFinding]:
    """
    target_type: 'stock' | 'theme'
    返回: [{keyword, evidence, severity}, ...]
    """
    findings = []
    keywords = REVERSE_KEYWORDS if target_type == 'stock' else THEME_KEYWORDS
    
    for kw_template in keywords:
        kw = kw_template.format(name=target_name, theme=target_name)
        results = web_search(kw, time_filter='7d')
        for r in results[:3]:
            severity = classify_severity(r)  # 'critical'/'major'/'minor'
            if severity != 'irrelevant':
                findings.append(ReverseFinding(kw, r, severity))
    
    return findings


def apply_reverse_to_score(score: int, findings: List[ReverseFinding]) -> int:
    """
    根据反向证据调整评分
    """
    for f in findings:
        if f.severity == 'critical':
            # 立案/退市/重大违规 → 直接 0 分 + 进红线
            return 0
        elif f.severity == 'major':
            # 大股东减持/业绩下修 → -20 分
            score -= 20
        elif f.severity == 'minor':
            # 一般负面新闻 → -5 分
            score -= 5
    return max(0, score)
```

**输出报告时必须显式列出反向证据**（找不到就写"反向求证: 无重大利空"），不能装作没查。

---

## 5. 红线警报清单（每次任务前置扫描）

```yaml
监管类（最高优先级）:
  P0_即停推送:
    - "立案调查"
    - "证监会立案"
    - "退市风险警示"
    - "终止上市"
    - "*ST" / "ST" 新增标记
  P1_红色警报:
    - 重大违规处罚（金额 > 1000 万）
    - 交易所重大问询函（业绩问询 / 重组问询）
    - 强制信息披露要求

公司基本面类:
  P0_即停推送:
    - 实控人被留置 / 被立案
    - 实控人被批捕
    - 财务造假（媒体披露 + 公司未否认）
  P1_红色警报:
    - 重大资产被冻结
    - 审计意见非标（保留意见 / 无法表示 / 否定）
    - 业绩同比下滑 > 50%
    - 业绩预告变脸（从盈利变亏损）

交易类:
  P0_即停推送:
    - 盘中临停（重大事项核查）
    - 重大事项停牌（不知道复牌时间）
  P1_红色警报:
    - 大股东大规模减持公告（拟减持 > 总股本 5%）
    - 高管集中辞职（同一周 ≥ 2 名核心高管辞职）
```

**触发动作**:
- P0 → 该股直接进"避雷名单"，不出现在任何 T 任务的推送中；如果是 Wallace 持仓股，立即推送红色警报
- P1 → 评分扣 20-50 分，并在输出中显式标注 "🚨 红线"

---

## 6. 输出格式（按场景分 3 套）

### 6.1 早盘速读（T1 用，<300 字）

适用 T1 竞价情报 + T3 13:00 午后开盘速报。

```
📊 [HH:MM] 早盘速读
━━━━━━━━━━━━━━━━

🚨 红线: [无 / XXX 因 YYY 立案]

🔥 主线题材: [板块名]
   驱动: [政策/事件，一句话]
   龙头: [股票名] [+X.X%]
   验证: [真热点 / 发酵中 / 警惕一日游]

⚡ 高开异动 TOP 3:
1. [股票A] +X% [板块] [催化简述]
2. [股票B] +X% [板块] [催化简述]
3. [股票C] +X% [板块] [催化简述]

🎯 9:30 操作思路:
   [激进/稳健/观望] - [一句话理由]
   关注: [1-2 个最值得盯的标的]
```

### 6.2 突发简报（T2/T3 用，<200 字）

适用单条快讯触发的即时推送。

```
🚨 [HH:MM] 突发
━━━━━━━━━━━━━━

事件: [50 字摘要]
来源: [金十/交易所/公告]
影响: [板块] / [涉及标的，最多 3 只]
评分: [XX 分 ⭐⭐⭐⭐]
半衰期: [flash/short/medium/long]

→ [介入/观望/规避]
```

### 6.3 盘后深度（T4 用）

适用 T4 收盘候选三档输出。详细模板见 `prompts/T4_收盘潜力.md`。

骨架:

```
🦞 [日期] 明日打板候选

📊 今日市场速览
- 上证: [+X%] 成交 [XX 亿]
- 涨停 [N] / 跌停 [N]
- 主线题材: [板块A][板块B]
- 风险信号: [无 / XXX]

🟢 C 档（精选 N 只 - 重仓/保守用）
[每只一段：板块/催化/量价/龙头属性/反向求证/操作建议]

🟡 B 档（N 只 - 常规打板）
[同上]

🔴 A 档（N 只 - 情绪极强时博弈）
[简略]

⚠️ 风险提示 + 免责声明
```

---

## 7. 信息半衰期标签

每条情报必须打上半衰期标签，决定是否进去重库 + 多久内不重复推送。

| 标签 | 半衰期 | 适用场景 | 去重窗口 |
|---|---|---|---|
| `flash` | 30 分钟 | 盘中突发（异动、临停） | 30 分钟内同事件不重推 |
| `short` | 1 天 | 短线题材、龙虎榜 | 24 小时内同标的同事件不重推 |
| `medium` | 3-5 天 | 政策类、行业事件 | 3 天内不重推 |
| `long` | 1-2 周 | 业绩类、机构调研 | 7 天内不重推 |
| `permanent` | 长期 | 公司基本面变化（重组/控制权变更） | 永久去重 |

---

## 8. 调用契约（T1-T5 任务如何用本 SKILL）

### 8.1 输入 Schema

```typescript
interface XiaoLongXiaInput {
    task_type: 'T1' | 'T2' | 'T3' | 'T4' | 'T5'
    
    // 目标
    target: string                  // 股票代码 / "market" / sector_name
    target_type: 'stock' | 'market' | 'sector'
    
    // 时间窗
    time_window: '5min' | '30min' | 'today' | 'week'
    
    // 输出格式
    output_format: 'early' | 'alert' | 'deep'
    
    // 模块开关
    enable_reverse: boolean         // 反向求证（默认 true，T4 强制 true）
    enable_redline: boolean         // 红线扫描（默认 true，禁用需说明）
    enable_dsa_api: boolean         // DSA 单股深度（T5 必开，T4 候选股逐个开）
    
    // 上下文
    holdings: string[]              // Wallace 持仓代码（用于价值判定加权）
    watchlist: string[]             // 盯盘池代码
}
```

### 8.2 输出 Schema

```typescript
interface XiaoLongXiaOutput {
    summary: string                 // 一句话总结
    score: number                   // 0-100
    tier: '⭐⭐⭐⭐⭐' | '⭐⭐⭐⭐' | '⭐⭐⭐' | '⭐⭐' | '❌'
    
    redline: null | {
        type: 'P0' | 'P1'
        category: 'regulation' | 'fundamental' | 'trading'
        detail: string
    }
    
    score_breakdown: {
        policy: number       // 0-25
        capital: number      // 0-25
        research: number     // 0-25
        sentiment: number    // 0-25
    }
    
    reverse_findings: Array<{
        keyword: string
        evidence: string
        severity: 'critical' | 'major' | 'minor'
    }>
    
    half_life: 'flash' | 'short' | 'medium' | 'long' | 'permanent'
    operation_advice: string        // 中文操作建议
    
    data_sources: string[]          // 实际成功调用的数据源 ID 列表
    failed_sources: string[]        // 失败的数据源 ID（用于调试）
    degraded: boolean               // 是否处于降级模式
}
```

### 8.3 错误处理协议（必须遵守）

```python
def execute_with_safety(task: XiaoLongXiaInput) -> XiaoLongXiaOutput:
    """SKILL 执行总入口，必须遵守的错误处理协议"""
    failed_sources = []
    successful_sources = []
    
    # 1. 红线扫描永远是第一步（哪怕其他都失败）
    try:
        redline = scan_redline(task.target)
        successful_sources.append('DS1')
    except Exception as e:
        log(f"红线扫描失败: {e}")
        failed_sources.append('DS1')
        redline = None
    
    # 2. 主数据获取，每个数据源单独 try-except
    data = {}
    for source_id, fetcher in DATA_SOURCES.items():
        if not is_enabled_for_task(source_id, task):
            continue
        try:
            data[source_id] = fetcher(task)
            successful_sources.append(source_id)
        except Exception as e:
            log(f"{source_id} 失败: {e}")
            failed_sources.append(source_id)
            # 尝试降级路径
            fallback = FALLBACKS.get(source_id)
            if fallback:
                try:
                    data[source_id] = fallback(task)
                    successful_sources.append(f"{source_id}_fallback")
                except:
                    pass
    
    # 3. 评分（哪怕只有部分数据也要给分，标 degraded=True）
    score = compute_score(data)
    degraded = len(failed_sources) > 0
    
    # 4. 反向求证（永远执行，找不到就写"无")
    reverse_findings = []
    if task.enable_reverse:
        try:
            reverse_findings = reverse_verify(task.target, task.target_type)
            score = apply_reverse_to_score(score, reverse_findings)
        except Exception as e:
            log(f"反向求证失败: {e}, 评分不调整, 标降级")
            degraded = True
    
    # 5. 输出（永远要返回，不能崩）
    return XiaoLongXiaOutput(
        summary=...,
        score=score,
        tier=score_to_tier(score),
        redline=redline,
        ...
        data_sources=successful_sources,
        failed_sources=failed_sources,
        degraded=degraded,
    )
```

**关键原则**:
- 任何单一数据源失败都不能让整个 SKILL 崩溃
- 输出必须永远成功（即使是降级模式）
- 降级模式必须显式标 `degraded=true` 并在用户可见的输出中提示"⚠️ 降级模式: [失败的数据源]"

---

## 9. 代理与环境注意事项（每次调用前置）

### 9.1 调用 AkShare / 任何国内站点前

```python
import os
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
os.environ['HTTP_PROXY'] = ''
os.environ['HTTPS_PROXY'] = ''
os.environ['ALL_PROXY'] = ''
```

### 9.2 用 requests 直接调用时

```python
import requests
session = requests.Session()
session.trust_env = False     # 关键：忽略系统代理
r = session.get(url, timeout=10)
```

### 9.3 调用 DSA API 时

DSA 自己已处理代理（`main.py` 顶部 `os.environ["NO_PROXY"]="*"`），所以 **DSA API 调用不受影响**。

### 9.4 调用 LLM API（DeepSeek/Gemini）时

DeepSeek 是国内服务，不需要代理。Gemini 海外服务，**需要代理**。两者矛盾。

**解决**: 用 DSA 内置的 LLM 客户端（DSA 内部按需切换代理），不要直连。

---

## 10. 测试用例（自验证用）

### Test Case 1: 600519（贵州茅台 - 大白马）

预期评分:
- 政策: 5-15（消费板块无强政策）
- 资金: 视当日实际，10-20
- 研报: 25（顶流覆盖）
- 情绪: 视当日实际
- 总分: 通常 50-70 之间，⭐⭐⭐ 或 ⭐⭐⭐⭐
- 红线: null
- 半衰期: long（基本面稳定）

### Test Case 2: 假设有家公司"XX 科技"被立案调查

预期:
- redline: {type: 'P0', category: 'regulation', detail: '...被证监会立案调查'}
- score: 0
- tier: ❌
- operation_advice: "立即避雷，不参与"

### Test Case 3: AI 算力板块（题材类）

target_type: 'sector'
预期:
- 走 R2 题材判定
- 输出 ThemeStatus + 龙头股名单 + 真热点判定

---

## 11. 与 V3.5 的边界（再强调）

| 场景 | V3.5 | 龙虾雷达 + 小龙虾 SKILL |
|---|---|---|
| 实时分钟级封板预警 | ✅ 它的本职 | ❌ 不做 |
| 自动下单 | ✅ 它的本职 | ❌ 永远不做 |
| 隔夜消息扫描 | ❌ | ✅ T1 |
| 盘中政策快讯 | ❌ | ✅ T2/T3 |
| 板块热度+龙头识别 | ❌ | ✅ T2/T3/T4 |
| 收盘明日候选 | ❌（V3.5 是"盘中即时") | ✅ T4 |
| 单股深度问答 | ❌ | ✅ T5 |
| 反向求证利空 | ❌ | ✅ 强制 |

**重叠不冲突**: V3.5 是"自动腿"，本 SKILL 是"信息眼"，两者数据流独立。

---

## 12. 版本历史

- v4.0 (2026-04-24): 完全重写。落实可执行性。明确 DSA 接口现实差异（不存在 /market/*）。补全代理处理。增加错误处理协议。增加调用契约。
- v3.0 (历史): Wallace 早期版本，规则空泛，已废弃。

---

> 🦞 **本 SKILL 由 Claude Opus 4.7 在 2026-04-24 编写**
> **下一步**: M3 阶段，T1-T5 任务提示词将通过 `task_type` 参数显式调用本 SKILL
