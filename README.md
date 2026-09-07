# dsharness —— 网文长篇验证 harness

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
.venv/Scripts/pytest                        # 69 项单测，全部离线
```

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
dsh ingest book.txt --db books/demo.db --provider deepseek [--limit 10] [--skip-errors]
dsh check   books/demo.db                       # 规则引擎，冲突写回状态库
dsh report  books/demo.db                       # markdown 冲突报告 → reports/
dsh replay  books/demo.db 3                     # 回放第3章抽取 JSON（往返核对）
dsh stability book.txt --provider deepseek --runs 2   # M0 验收：抽取往返稳定性
dsh rules                                        # 列出内置规则
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

**加规则零代码**：写一个 YAML（`rule_id/name/severity/predicate/params`），`dsh check --rules your.yaml`。
境界阶梯等参数按书自定义，示例见 [examples/custom_rules.yaml](examples/custom_rules.yaml)。
PLAN §4 二十条中余下 12 条（称谓一致性、金钱流水守恒、数字复述一致、代词指代…）
需要更强的抽取契约支撑，按里程碑逐步补谓词。

## 当前状态

- **M0 完成**：provider 层（deepseek/glm/mock + 分级档位）、切章、抽取管线
  （错误反馈重试 ×1、`--skip-errors` 降级）、SQLite 状态库、`stability` 验收工具。
  对真实 API 的往返稳定性测量（M0 验收：单书 10 章）待有 key 后执行。
- **M1 起步**：规则引擎 + 8 条内置规则 + 报告。计划 20 条中其余谓词逐步接入。
  自定义规则示例：`dsh check books/demo.db --rules examples/custom_rules.yaml`。
- **M2 占位**：persona 契约与内置画像已定义（`readers/personas.py`），模拟实现待 M2。
- 重建策略：`rebuild()` 以全书抽取为事实源单事务全量重建；增量追章优化留后续里程碑。

## 工程约定

- 异常策略：统一异常；层边界翻译为 `ProviderError`/`ExtractionError`/`RuleError`
  并附上下文；CLI 顶层统一打印一次错误（`--debug` 看栈）。
- LLM 输出与规则 YAML 一律按不可信输入处理：pydantic 严格验证 / `yaml.safe_load`。
- API key 只从环境变量读取；任何错误消息与日志不含密钥。
- 文稿版权：只处理用户自有/公版文稿，不内置任何平台抓取。
