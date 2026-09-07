# canonkeeper —— 网文长篇验证 harness

给长篇网文的生成/改稿流程装上**三级验证体系**。模型无关（OpenAI 兼容 API 可插拔），
研究"怎么用模型"，不练模型——模型是可插拔的被试，harness 是资产。

方案全文见 [PLAN.md](PLAN.md)（v1，2026-09-07）。

```
书稿 txt → 切章 → [抽取器] LLM 结构化输出 → [状态库] SQLite
         → [规则引擎] 纯程序化不变量检查（不调 LLM，零幻觉）
         → [软验证器 M2] persona 读者 → [报告] markdown 冲突清单
```

关键设计：**硬验证器的"判定"环节不经过 LLM**——LLM 只负责抽取，判定可复现、可单测、无幻觉。
规则引擎的谓词是纯函数，100% 单测覆盖（`tests/`）。

## 安装

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[dev]"      # Windows；Linux/macOS 用 .venv/bin/
.venv/Scripts/pytest                        # 75 项单测，全部离线
```

命令行入口：`canonkeeper`（主）、`canonkeeper-mcp`（MCP server）。`dsh` 仅作遗留别名保留——
deepseek-harness 的 CLI 也叫 `dsh`，同环境安装会撞名。

## 配置（密钥只走环境变量，绝不写入代码/配置/日志）

| provider | 环境变量 | fast 档 | flagship 档 |
|---|---|---|---|
| deepseek（默认） | `DEEPSEEK_API_KEY` | deepseek-chat | deepseek-reasoner |
| glm | `ZHIPU_API_KEY` | glm-4-flash | glm-4-plus |
| mock（离线冒烟） | 无 | — | — |

模型名可用 `DSH_FAST_MODEL` / `DSH_FLAGSHIP_MODEL` 覆盖（上游改名零代码适配）。
分级调用策略：fast 档做批量抽取，flagship 档留作终审/复核。

## 用法

```bash
canonkeeper ingest book.txt --db books/demo.db --provider deepseek [--limit 10] [--skip-errors]
canonkeeper check   books/demo.db                  # 规则引擎，冲突写回状态库
canonkeeper report  books/demo.db                  # markdown 冲突报告 → reports/
canonkeeper replay  books/demo.db 3                # 回放第3章抽取 JSON（往返核对）
canonkeeper stability book.txt --provider deepseek --runs 2  # M0 验收：抽取往返稳定性
canonkeeper rules                                  # 列出内置规则
```

无 API key 时可用 `--provider mock` 跑通全链路（返回与正文无关的固定样例抽取）。

## 内置规则（M1 起步集，PLAN §4 20 条中的可机检子集）

| 规则 | 检查 | 谓词 |
|---|---|---|
| `CHAR_001` | 死亡后不得以活体出场（复生须登记） | `terminal_state_reuse` |
| `ITEM_009` | 已毁/已耗品不得复用（修复/复得须登记） | `terminal_state_reuse`（同谓词异参数） |
| `CHAR_012` | 境界单调（废功须登记；阶梯前缀匹配，阶梯外值跳过不误报） | `realm_regression` |
| `CHAR_002` | 年龄等数值属性随时间线单调（重生/回溯须登记；支持中文数字） | `numeric_attr_monotonic` |
| `CHAR_005` | 位置连续性（瞬移须登记；依赖事件 location，缺失自动跳过） | `location_continuity` |
| `ITEM_011` | 交易/赠予后所有权转移须登记（前后 window 章内查登记） | `transfer_registered` |
| `TIME_006` | 故事时间单调（闪回须显式标记；依赖 day_offset，缺失自动跳过） | `time_regression` |
| `META_018` | 别名归一（别名指向多实体 → info，人工裁决） | `alias_collision` |

**加规则零代码**：写一个 YAML（`rule_id/name/severity/predicate/params`），`canonkeeper check --rules your.yaml`。
境界阶梯等参数按书自定义，示例见 [examples/custom_rules.yaml](examples/custom_rules.yaml)。
PLAN §4 二十条中余下 12 条（称谓一致性、金钱流水守恒、数字复述一致、代词指代…）
需要更强的抽取契约支撑，按里程碑逐步补谓词。

## 作为 dsh（deepseek-harness）插件接入（MCP）

[deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)（CLI 名 `dsh`，
"everything is a plugin"）的插件一等公民是 TypeScript/Cordis；Python 工具包的标准接入路径是
**MCP server**。本仓库内置两端：

- **MCP server**（`canonkeeper/mcp.py`，`pip install "canonkeeper[mcp]"` 后由 `canonkeeper-mcp` 启动），
  工具面对应 PLAN M3 生成回路：

  | 工具 | 时机 | 作用 |
  |---|---|---|
  | `ingest_book` | 写后 | 切章 + LLM 抽取 + 入库 |
  | `check_consistency` | 写后 | 规则引擎冲突清单（JSON，纯程序化判定） |
  | `query_entity` | 写前 | 按名/别名查实体属性、状态史、关系、出场章 |
  | `replay_chapter` | 复核 | 回放某章抽取 JSON，定位误报来源 |
  | `get_report` | 复核 | markdown 冲突报告全文 |

- **dsh bundle**（[plugin/](plugin/)）：薄壳，只插一行 `@deepseek-ai/dsh-mcp-client` 配置。
  安装：`dsh plugin --profile <name> add file:<repo>/plugin`，工具即以
  `mcp__canonkeeper__*` 出现在模型工具列表。详见 [plugin/README.md](plugin/README.md)。

## 评测基准（evals）

事实级查全评测，代替手工对账成为质量门：标注 YAML（数值/实体/属性/变更/事件/关系/时间/信号
八类事实）+ 评测器。**number 只认结构化字段**（attrs 值/payload 值/change old|new），
quote 原文回显不算捕获——与人工对账同口径。版权边界：第三方热门文原文不入仓库，
`--texts` 指向本地目录，标注仅含事实与 ≤25 字定位短语。

```bash
.venv/Scripts/python evals/run_eval.py --labels evals/labels/bench-v1.yaml \
    --texts <本地章节目录> --provider deepseek --out evals/results/latest.md
```

当前基线 → 前沿技术迭代（bench-v1：艾尔德兰 3 章 + 热门财务流第 1 章万字体量，deepseek-chat）：

| 品类 | number | entity | attr | change | event | relation | time | signal |
|---|---|---|---|---|---|---|---|---|
| 旧单段基线 | 75% | 84% | 38% | 40% | 62% | 0% | 33% | 80% |
| **G&O×3 自洽+跨章状态** | **88%** | **100%** | **50%** | **60%** | 62% | **100%** | **67%** | **100%** |

三项落地技术：**G&O 两段式抽取**（先自由笔记后组织 JSON，arXiv 2402.13364——entity 100%、
关系抽取从 0 到有）、**置信度自洽合并**（N 遍并集投票，`ingest --samples N`，arXiv 2502.06233
——number 75→88%）、**跨章有状态注入**（前情状态随章累积回灌 prompt——time 33→67%，账本章界
衔接）。附带修复：万字章 JSON 输出被默认 max_tokens 截断（组织段提至 8192）。

历史发现（仍成立）：对参与过 prompt 迭代的自家书查全偏高、未见过的热门文偏低——
**过拟合风险靠"基准必须含未见书"对冲**。标注格式见 `evals/labels/bench-v1.yaml` 头部注释。

**已知代价（下一杠杆）**：自洽并集是查全面向的——万字章合并后实体 97 个/事件 124 条，
**精度未度量**；下一步加 precision 指标 + min_votes 阈值去噪。数字归位依赖组织段服从度，
attr 50% 仍有空间。

## 写作知识库（docs/craft/）

M2 persona 与 M3 生成回路的领域弹药库，每条技法按「机理 → 一致性要求 → 可机检信号」组织：

- [长篇网文写作技巧](docs/craft/longform-webnovel-craft.md)：金手指预算规则、爽点循环、
  承诺管理、信息差、数字叙事、卷结构、配角退场纪律、反派阶梯、章末钩子、追读设计
- [文学素养基础](docs/craft/literary-craft.md)：动机与弧光、场景三要素、展示而非陈述、
  对白潜台词、伏笔公平性、时序节奏、POV 纪律、时钟张力、主题母题
- [跨领域借鉴地图](docs/craft/borrowings.md)：游戏工业（任务图/经济平衡/旗标系统/beat chart/
  混合架构/事件溯源）与叙事学研究的可借鉴清单，附优先级

## 当前状态

- **M0 完成（真实 API，两轮质量迭代，2026-09-07/08）**：provider 层（deepseek/glm/mock + 分级
  档位）、切章、抽取管线、SQLite 状态库、`stability` 验收工具。deepseek-chat 实测用户自有书稿 3 章：
  - v1 基线：全链路通，但人工对账第一章关键事实查全仅 ~40%——19 项核心数字只捕获 4 项
    （约 25%），次数/金币账本几乎缺失；稳定性 0.651。**「管线跑通」≠「质量好」。**
  - v2 迭代（抽取温度 0.0 + prompt 数字纪律/实体事件完备性 + 代词别名代码层硬过滤）：
    第一章数字捕获 17/19（约 90%），次数账本（50→47→24→3）与金币账本全链入库，
    实体类型正确（暗影石→物品、闪光突刺→功法），代词别名滤净；稳定性 **0.714**
    （第 2 章 1.000；散文化的第 3 章 0.476 仍差——完备性压力放大其波动，待研究）。
  - 真实命中：ITEM_011 报出暗影石交易的所有权登记缺失（low 级交叉印证通道）。
  - 已知缺口（下一杠杆）：day_offset 需跨章上下文（单章自算：3/None/3，应为 3/4/5）；
    金币账 old 回填在章界断裂（第 1 章末 21 vs 第 2 章 old=16）；伏笔节拍（刺客接近）仍漏；
    双遍抽取交叉 + 旗舰复核（PLAN §8）未做。glm 适配器未实测（无 ZHIPU_API_KEY）。
  - **评测基线（evals，2026-09-08）**：自建事实级基准实测 overall——number 75%、entity 84%、
    attr 38%、change 40%、event 62%、relation 0%、time 33%。自家书数字 87% vs 未见热门文 45%，
    过拟合风险实锤。详见上方「评测基准」。
- **M1 起步**：规则引擎 + 8 条内置规则 + 报告。计划 20 条中其余谓词逐步接入；
  金钱流水守恒（⑮）与数字复述一致（⑳）因账本数据已可抽取，列入下一批。
  自定义规则示例：`canonkeeper check books/demo.db --rules examples/custom_rules.yaml`。
- **M2 占位**：persona 契约与内置画像已定义（`readers/personas.py`），模拟实现待 M2。
- **dsh 插件接入（MCP）**：server + bundle 完成，stdio 端到端测试覆盖；真实 dsh 运行时
  `plugin add` + `--dump-config` 层叠加验证通过（工具注册的启动级验证待 LLM 凭据）。
- 重建策略：`rebuild()` 以全书抽取为事实源单事务全量重建；增量追章优化留后续里程碑。

## 工程约定

- 异常策略：统一异常；层边界翻译为 `ProviderError`/`ExtractionError`/`RuleError`
  并附上下文；CLI 顶层统一打印一次错误（`--debug` 看栈）。
- LLM 输出与规则 YAML 一律按不可信输入处理：pydantic 严格验证 / `yaml.safe_load`。
- API key 只从环境变量读取；任何错误消息与日志不含密钥。
- 文稿版权：只处理用户自有/公版文稿，不内置任何平台抓取。
