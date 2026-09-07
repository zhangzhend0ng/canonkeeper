# canonkeeper —— 网文长篇验证 harness 方案 v1

> 一句话：给长篇网文的生成/改稿流程装上**三级验证体系**的 harness。
> 模型无关（DeepSeek/GLM 等 OpenAI 兼容 API 可插拔），研究"怎么用模型"，不练模型。
> 本文档自包含、仓无关——可直接拷入新仓库作为 PLAN.md。
> 缘起与完整论证见背景节末尾的关联文档；本文只留可执行的部分。v1（2026-09-07）。

## 0. 核心判断（为什么做）

1. 网文写作是 agent 核心能力（长程状态/规划/伏笔承诺/模糊反馈学习）的上界测试舱
2. AI 网文当前失败的两块根因缺口：**百万字状态管理** 与 **主观域验证器**——
   也是通用 agent 的缺口，网文战场=agent 研究的影子前线
3. 方法论=**验证分层**：硬验证器（可机检子集先吃）→软验证器（模拟读者）→真验证器（追读）
4. 个体约束下的正解：模型是可插拔的被试，**harness 是资产**——架构不随模型换代贬值

## 1. 模型策略（API-first）

- **Provider 抽象层**：只写一个 OpenAI-compatible 适配器（base_url + api_key + model 三参数），
  通吃 DeepSeek / GLM(open.bigmodel.cn) / Kimi / 本地 vLLM——**名字叫 canonkeeper，
  但 DeepSeek 只是默认适配器，不锁死架构**
- 首发适配器=DeepSeek：直连无墙、OpenAI 兼容、便宜（长上下文整书分析一次≈几元）、
  中文强；GLM 同格式为第二适配器（对照被试）
- **分级调用**：低价/快速档做批量抽取与初筛，旗舰档做冲突判定终审——成本-质量分层
  是 harness 的内置策略，不是临时优化
- 研究变量=架构（抽取策略/规则库/persona 设计），模型=受控常量（所有结论标注版本号）

## 2. 架构总图

```
书稿(用户自有 txt/epub)
  → 切章 ingestion
  → [抽取器] LLM 结构化输出(JSON): 每章事件/人物状态变更/新实体登记
  → [状态库] SQLite: 实体表+事件表+关系表+时间线(可查询、可回放)
  → [规则引擎] 程序化不变量检查(不调LLM,零成本零幻觉)
  → [软验证器] persona 读者模拟(N个) → 三指标(意外感/连贯/伏笔回收公平性)
  → [报告] markdown/html: 冲突清单(严重度定位到章/句) + 读者侧报告
```

关键设计：**硬验证器的"判定"环节不经过 LLM**（规则引擎纯程序化）——LLM 只负责抽取，
判定可复现、可单测、无幻觉。这是整个 harness 可信度的地基。

## 3. 状态库 schema 草案

```
entities(id, type[人物|物品|地点|组织|功法], name, aliases[], attrs JSON)
  -- attrs: 年龄/境界/生死/位置/所属/所有权...
events(id, chapter, entity_id, kind[登场|死亡|交易|升级|移师|改名...], payload JSON, quote)
relations(id, subject_id, object_id, kind[师徒|亲属|敌对...], since_chapter, until_chapter)
timeline(chapter, story_time_start, story_time_end, markers[])
violations(id, rule_id, chapter, entity_ids[], evidence_quote, severity)
```

## 4. 不变量规则 20 条起步清单

人物：①死亡后不得以活体出场（复生须登记）②年龄随时间线单调 ③称谓与登记关系一致
④关系变更（拜师/结拜）后称谓必须切换 ⑤位置连续性（无瞬移）
时间：⑥故事时间单调（闪回须显式标记）⑦季节/昼夜与时间线相符 ⑧期限事件倒计时一致
物品：⑨已毁/已耗品不得复用 ⑩唯一物不可两地同时出现 ⑪交易/赠予后所有权转移
等级（网文特化）：⑫境界单调（废功须登记）⑬功法习得后才能使用 ⑭战力描述与境界档位相符
世界观：⑮金钱流水守恒 ⑯组织名称一致（改名须登记）⑰地名/疆域归属一致
文本技术：⑱别名归一（多称呼合并到实体）⑲代词指代实体在场 ⑳数字复述一致（军力/距离/金额）

规则以 YAML/表驱动（rule_id/适用实体/谓词/严重度），新规则零代码接入。

## 5. 阶段计划

| 里程碑 | 内容 | 验收 | 成本 |
|---|---|---|---|
| M0 骨架 | provider 层+切章+抽取管线+最小状态库 | 单书 10 章抽取→入库→回放往返稳定 | API 几元 |
| M1 硬验证器 v0 | 20 条规则+规则引擎+报告 | 试点书（用户自有或公版）人工核对查全/查准 | 几元 |
| M2 软验证器 v0 | 3~5 个 persona 读者+三指标（意外/连贯/伏笔回收） | 同章多读者报告，与 M1 冲突清单交叉印证 | 十元级 |
| M3 生成回路 | 写前查设定/写后跑验证的迭代循环（harness 反哺生成） | 修改建议被采纳率/冲突数下降曲线 | 视用量 |
| M4 真实接线（远期） | 连载平台追读数据（合作/自建） | 在线验证闭环 | 外部依赖 |

M0~M2 纯 API 无 GPU；M1 产出的检测器本身就是可公开的开源工具（验证工具地带）。

## 6. 新仓库目录建议

```
canonkeeper/
  PLAN.md                 ← 本文档
  pyproject.toml          ← python 3.10+；依赖：openai sdk(兼容端点)/pydantic/sqlite3(内置)/typer(可选)
  canonkeeper/
    providers/base.py     # OpenAI 兼容抽象：chat(messages, json_schema, tier)
    providers/deepseek.py # base_url=https://api.deepseek.com 默认
    providers/glm.py      # base_url=https://open.bigmodel.cn/api/paas/v4
    extract/schemas.py    # pydantic: 章事件/实体/关系（LLM 结构化输出契约）
    extract/extractor.py
    store/db.py           # SQLite（stdlib，零依赖）
    rules/engine.py       # 纯程序化判定（不调 LLM）
    rules/builtin/*.yaml
    readers/personas.py   # persona 定义+模拟+指标
    report/render.py
    cli.py                # dsh ingest / dsh check / dsh readers / dsh report
  tests/                  # 规则引擎单测（判定逻辑 100% 可单测=卖点）
  books/                  # 用户自有文稿（gitignore）
  reports/                # gitignore
```

## 8. 风险与开放问题

- **抽取错误率=检测器上限**：LLM 漏抽/错抽事件，规则引擎再对也白搭——M0 的验收
  就是量化抽取往返稳定性；缓解=双遍抽取交叉+廉价模型初筛旗舰复核的分级
- **persona 漂移**：模拟读者聊长后人设不稳（NeurIPS 2025 已研究）——M2 限制在短窗+
  每次重新锚定人设
- **版权边界**：harness 只处理用户自有/公版文稿；不内置任何平台抓取
- **竞争**：span 级幻觉检测、写作 RM 已热（RLMR 等）；但"中文网文设定冲突检测器+
  三级验证整合"的工具位暂无头部——M1 产出即可占位
