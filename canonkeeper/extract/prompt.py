"""抽取 prompt（G&O 两段式，arXiv 2402.13364 的落地）：
第一段自由收集事实笔记（不受格式约束，查全优先），第二段照 schema 组织成 JSON（不丢不编）。
单段直出 JSON 会迫使模型边读边组织——实测压低 attr/relation 查全（见 evals 基线）。"""

from __future__ import annotations

import json
from functools import lru_cache

from ..ingest.splitter import Chapter
from .schemas import ChapterExtraction

__all__ = [
    "SYSTEM_PROMPT",
    "build_collect_messages",
    "build_organize_messages",
]

SYSTEM_PROMPT = (
    "你是网文文本结构化抽取引擎。第一遍任务只输出事实笔记，第二遍任务只输出一个 JSON 对象，"
    "严格按当次指令执行，不要输出多余文本。"
)

# 前情状态注入（跨章有状态抽取）：修 day_offset 断链与账本 old 回填断裂
COLLECT_INSTRUCTIONS = """\
通读下面的章节正文，用清单式笔记（不限格式、不输出 JSON）穷举本章事实，分类列出：
1. 出场/被提及的每一个具名实体（人物/物品/材料/技能/地点/组织），含本章所有称呼；
2. 每一个数值事实（余额/次数/等级/单价/数量/时长/距离/期限/排名/分值/规则参数），写明属于谁、上下文；
3. 每一次状态变化（谁、什么属性、从什么变到什么），附原文短句；
4. 每一个情节节拍（交易/战斗/委托/邮件/警告/接近/回忆闪回…），不只挑主线；
5. 人物关系的建立/解除；
6. 本章故事时间与全部时间标记。
只记录原文依据，不编造；宁多勿漏。"""

ORGANIZE_INSTRUCTIONS = """\
把事实笔记完整整理为 JSON。规则：
- 笔记中的每一条事实都必须进入 JSON，不得丢弃；也不得编造笔记之外的事实。
- entities: type 取 人物/物品/地点/组织/功法（材料道具→物品，技能功法→功法）；aliases 收全部称呼，
  代词与泛指(他/她/对方/这人)不得作为别名。
- state_changes: 每次属性变化一条，attr 取 生死/境界/位置/所有者/所属/状态/余额/剩余次数/等级 等，
  old 尽量回填（可参考前情状态），quote 用原文连续片段(≤60字)。
- events: kind 用一个动词；payload 收一次性数值(单价/数量/总价/利润/时长/次数/酬金)，值保留原文写法。
- 数字归位(最易失分): 笔记中的每一个数值都必须出现在 JSON 的某个结构化字段里——
  持续属性进 entity.attrs，一次性事实进 event.payload，变化前后进 state_change.old/new；
  数值只出现在 quote 或 summary 里视为遗漏。
- relations: subject/object/kind(师徒/亲属/敌对/同门/主仆/朋友/所属/雇佣等)/state(建立/解除)。
- story_time.day_offset: 在前情状态给出的累计天数基础上，按本章时间标记累计；无法推断才填 null。
- 禁止编造；原文出现的数值与实体不得遗漏。"""


@lru_cache(maxsize=1)
def _schema_json() -> str:
    return json.dumps(ChapterExtraction.model_json_schema(), ensure_ascii=False)


def _chapter_header(chapter: Chapter) -> str:
    return f"【第{chapter.number}章 {chapter.title}】" if chapter.title else f"【第{chapter.number}章】"


def build_collect_messages(chapter: Chapter, context_note: str = "") -> list[dict[str, str]]:
    parts = [COLLECT_INSTRUCTIONS]
    if context_note:
        parts.append(f"\n# 前情状态（截至上一章末）\n{context_note}")
    parts.append(f"\n# 章节正文\n{_chapter_header(chapter)}\n{chapter.text}")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]


def build_organize_messages(
    chapter: Chapter, notes: str, context_note: str = ""
) -> list[dict[str, str]]:
    parts = [ORGANIZE_INSTRUCTIONS]
    if context_note:
        parts.append(f"\n# 前情状态（截至上一章末）\n{context_note}")
    parts.append(f"\n# 事实笔记（必须全部整理进 JSON）\n{notes}")
    parts.append(f"\n# 输出 JSON Schema\n```json\n{_schema_json()}\n```")
    parts.append(f"\n# 章节正文（核对用）\n{_chapter_header(chapter)}\n{chapter.text}")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(parts)},
    ]
