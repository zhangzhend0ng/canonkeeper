# 跨领域借鉴地图：游戏工业与其他研究 → canonkeeper 与长篇写作

> 回答一个问题：游戏与其他研究领域，有哪些**更好的艺术表现形式**和**更工程化的内容**可以借鉴。
> 每条按「来源 → 借什么 → 落到哪」组织。落点三类：写书手艺（craft）、canonkeeper 工程（eng）、
> 学术对齐（research）。

## 一、艺术表现形式

### 1. 游戏任务结构（Quest Graph）→ 单元剧的工程化画法
游戏任务 = 目标 → 前置条件 → 步骤/分支 → 高潮 → 报酬的**有向无环图**，且前置条件是显式的
（没拿钥匙开不了门）。网文单元剧与之同构，但作者通常只在脑中隐式持有。
**借什么**：写卷前画 quest graph（任务来源、代价、报酬、失败态、谁知情）；学术对应：
分支任务程序化生成研究（de Lima 2022）、PCG 综述（arXiv 2410.15644）——任务被建模为前置条件图。
**落到哪**：craft 手艺；远期工具化（用 mermaid/图存进 books/ 设定目录，M3 写前查询）。

### 2. 游戏经济平衡（Faucet & Sink）→ 财务流的账本 QA
游戏工业用「收入水龙头 / 支出水槽」模型+ 电子表格模拟来平衡经济系统，QA 有专门的 economy
bug 类别（收入漏记、货币复制、商店定价倒挂）。财务流小说的金币账**就是一个游戏经济**：
本轮 evals 抓到的 31.6 vs 33.6 在游戏 QA 里是标准 economy bug。
**借什么**：收支两条流水表 + 「Σ收入 − Σ支出 = 余额差」的复算器。
**落到哪**：eng——规则⑮的精确实现（对账本数据做区间求和校验，容许模糊写法报 low 级）。

### 3. Flag 系统（JRPG 事件旗标）→ 伏笔与承诺的形式化
JRPG 用变量/旗标表跟踪「玩家是否见过某场景、是否触发某事件」；后续剧情用条件检查旗标。
伏笔 = set flag，回收 = check flag——canonkeeper 计划中的 commitments 表与之完全同构。
**落到哪**：eng（commitments 表的 flag 语义：set_chapter / check_chapter / status）；craft
（写卷时显式列 flag 清单）。

### 4. Beat Chart / 强度曲线（Valve 关卡设计、L4D AI Director）
关卡设计用 beat chart 把「张力/情绪强度 vs 时间」画成曲线，扁平中段一眼可见；L4D 用导演系统
动态调节强度。拆文库的 `节奏.md` 是其手工版。
**借什么**：每章按场景打强度分（1-10）画曲线；连章看曲线形状（锯齿=爽点循环健康，长平台=拖沓）。
**落到哪**：craft（写前 beat chart）；M2 三指标之节奏维度的可视化输出。

### 5. 环境叙事（FromSoftware 式碎片化）
物件描述承载世界观，考据型玩家自己拼图——对应网文的冰山写法与考据党福利。
**借什么**：给重要道具写「描述层」设定（进状态库 attrs），后期回收时引用原文——伏笔的
低成本埋设手法。

### 6. 好感度数值与 NPC 状态机（Galgame/CRPG）
关系不只是"师徒"标签：galgame 的好感度是数值，CRPG 队友有 approval 阶段；NPC 行为是状态机
（敌对→中立→友好需事件驱动）。
**借什么**：关系带数值/阶段（敌对-20 → 缓和 0 → 结盟 +40），转变必须有驱动事件。
**落到哪**：eng（relations 表加可选 value 阶段字段）；craft（人物关系卡）。

### 7. 影视场记制度（Continuity Supervisor）
长剧组有专人做 continuity：lined script、道具/服装/伤势/昼夜连续性清单、"previously on"。
这就是人力版 canonkeeper——他们的**清单分类学**直接可抄：伤口延续、持有的物品、时间流逝、
天气季节。
**落到哪**：规则清单扩展方向（伤势延续：规则①的轻量版；装备持有：规则⑩⑪）。

### 8. TRPG 战役管理（World Anvil / LegendKeeper）与美剧 Series Bible
TRPG 工具的信息架构：互联 wiki + 时间线视图 + 关系图谱 + 会话回顾；美剧的 series bible 是
长篇的官方状态文档；GM 备课法（Lazy DM）：每个 NPC 两行字——want + secret。
**借什么**：`want/secret` 二元组进人物 attrs（动机账本的最小实现，直连文学素养文档第 1 条）。

## 二、工程化

### 9. 混合架构共识（Ink/Yarn 管状态，LLM 管生成）
游戏叙事工具的业界共识：**确定性状态层（变量/条件/旗标）+ 生成层（自然语言）**分离——
LLM NPC 一致性研究（arXiv 2510.13586）同样结论：persona-aware prompting 必须配显式变量跟踪。
canonkeeper 的「LLM 抽取 + 程序化判定」正是同构架构，方向被工业界验证。
**借什么**：它们的**条件语法**——规则 DSL 升级方向：`若 flag[已结丹] 则 断言 境界≥金丹`
（比纯谓词名更有表达力）。

### 10. 事件溯源（Event Sourcing）→ 增量追章
「抽取结果=事件日志，状态库=投影」——我们已经是隐式事件溯源。正式化后：**新章只追加抽取、
增量重放投影**，不必全书 rebuild（README 路线图里的"增量追章"正解）。
**落到哪**：eng（append-only 抽取日志 + 版本化投影；schema 迁移纪律学游戏存档迁移）。

### 11. 叙事规划与模型检查（Narrative Planning / Model Checking）
学术圈把故事建模为状态空间、情节=合法状态转移序列（R.M. Young 叙事规划一脉；交互叙事的
模型检查 NuSMV 应用；Eger 的 CSP 建模）。我们的不变量在这种形式化里就是**时序逻辑约束**
（"死亡后不得未复活出现" ≙ G(dead → ¬alive U revive)）。
**落到哪**：research（把规则引擎的形式化写成文档/论文——「中文网文设定的时序约束检验」
是有差异化卖点的题目）；eng 远期（前置图校验：打 Boss 前须有入场资格）。

### 12. 知识图谱约束体系（Wikidata Constraints / SHACL）
Wikidata 对每条属性定义约束（值域、单值、依赖：有死亡日期则不能在世）并有**约束违规报告**——
与我们 violations 表同构，但表达力成体系。
**落到哪**：eng（规则 DSL 向约束语言靠拢：适用实体类型 + 值域 + 跨实体依赖）。

### 13. 静态分析的 def-use 链 → 伏笔悬空检测
编译器对变量做「定义-使用」分析找未定义引用。叙事同构：伏笔=定义，回收=使用；
**悬空使用**（第 10 章用"那把剑"但剑已在第 4 章毁掉）与**未使用定义**（挖坑不填）
都是 def-use 异常。
**落到哪**：eng（commitments 表 + 实体状态做 def-use 报告；"挖坑/弃坑清单"是作者强需求）。

### 14. 游戏 QA 的快照回归 + CI
游戏渲染回归用黄金截图对比；我们把 evals 挂 CI：**prompt/模型每变一次自动跑 bench-v1、
出对比表、README 基线表自动更新**——评测从"手动跑"变成"回归门禁"。
**落到哪**：eng（GitHub Actions workflow + 结果 diff 注释；本仓库下一步基建）。

### 15. 计算叙事学（Computational Narratology）
Propp 功能位（31 种叙事功能）、Labov 叙事结构、故事文法（Thorndyke）——事件分类学有
学术版。我们 event.kind 目前是自由动词，可向 Propp/Labov 受控词表靠拢以提升可检验性
（trade-off：损失网文黑话表达力，建议做映射层不做替换）。

## 三、优先级建议

| 优先 | 借鉴 | 成本 | 预期收益 |
|---|---|---|---|
| 高 | ⑮ 经济复算器（#2） | 低 | 财务流核心卖点，账本数据已就绪 |
| 高 | ⑭ evals CI 化（#14） | 低 | prompt 迭代不再裸奔 |
| 高 | ⑩ 事件溯源化增量追章（#10） | 中 | 百万字书的可用性前提 |
| 中 | ③ commitments 表（#3/#13） | 中 | 挖坑/弃坑清单，作者强需求 |
| 中 | ⑥ 关系数值阶段（#6） | 低 | M2 代入型 persona 的素材 |
| 低 | ⑪⑫ 形式化与约束语言 | 高 | 论文/长期表达力 |

## 出处

分支任务生成：[de Lima 2022](https://www.sciencedirect.com/science/article/pii/S1875952122000155)、
[QuestVille](https://dl.acm.org/doi/10.1145/3582437.3587188)、
[PCG 综述 arXiv 2410.15644](https://arxiv.org/html/2410.15644v1)；
叙事工具混合架构：[narrative design tools 综述](https://loreweaver.ink/insights/best-narrative-design-tools/)、
[LLM NPC 一致性 arXiv 2510.13586](https://arxiv.org/html/2510.13586v3)；
游戏叙事生成讨论：[HN: Player-Driven Emergence](https://news.ycombinator.com/item?id=40315434)。
Ink/Yarn/articy、World Anvil、场记制度、JRPG 旗标、faucet/sink、beat chart 为工业界通识。
