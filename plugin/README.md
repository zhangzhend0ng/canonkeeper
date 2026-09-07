# canonkeeper × dsh 插件 bundle

把 [canonkeeper](../README.md)（网文长篇验证 harness）作为插件接入
[deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness)（CLI 名 `dsh`）。

## 架构

```
dsh agent 循环 ── ctx.tools ── @deepseek-ai/dsh-mcp-client (stdio)
                                    └── canonkeeper-mcp (本仓库 Python MCP server)
                                            ├── ingest_book      写后入库
                                            ├── check_consistency 写后验证（纯程序化规则引擎）
                                            ├── query_entity      写前查设定
                                            ├── replay_chapter    抽取回放/定位误报
                                            └── get_report        markdown 冲突报告
```

dsh 的插件一等公民是 TypeScript/Cordis；Python 工具包的标准接入路径是 MCP server。
本目录是薄 bundle：不包含任何 TS 逻辑，只插入一行 mcp-client 配置。

## 安装

```bash
# 1. 装本包（MCP extra + canonkeeper-mcp 命令）
pip install "git+https://example.com/canonkeeper.git#egg=canonkeeper[mcp]"
#   或本地: pip install "C:/build/canonkeeper[mcp]"

# 2. 把 bundle 装进 dsh 的某个 profile
dsh plugin --profile <你的profile> add file:C:/build/canonkeeper/plugin

# 3. 重启 dsh 后，模型工具列表出现 mcp__canonkeeper__* 五个工具
```

不想发 npm 包的零安装替代：把 `cordis.patch.yml` 里 `- insert:` 段落手工并入
`$DSH_HOME/profiles/<profile>/cordis.patch.yml`（用户层 patch，last-write-wins）。

## 密钥

dsh 对 stdio 子进程做环境净化，`DEEPSEEK_API_KEY` 等不会自动透传；
`cordis.patch.yml` 已用 `!!js process.env.*` 从宿主进程显式转发抽取所需变量。
`mock` provider 无需任何密钥，可先离线体验全链路。

## 开发状态

对应 PLAN.md 的 M3（生成回路）：agent 写完一章 → 调 `ingest_book` 入库 →
`check_consistency` 拿冲突清单按证据改稿 → `query_entity` 在写下一段前查设定。
