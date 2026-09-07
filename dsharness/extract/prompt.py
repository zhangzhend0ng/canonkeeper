"""抽取 prompt：指令 + JSON Schema 注入 + 章节正文。"""

from __future__ import annotations

import json
from functools import lru_cache

from ..ingest.splitter import Chapter
from .schemas import ChapterExtraction

__all__ = ["SYSTEM_PROMPT", "INSTRUCTIONS", "build_messages"]

SYSTEM_PROMPT = (
    "你是网文文本结构化抽取引擎。只输出一个 JSON 对象，"
    "不要输出解释、markdown 代码围栏或任何其他文本。"
)

INSTRUCTIONS = """\
从下面的章节正文中抽取结构化信息。要求：
- entities: 本章出场或被明确提及的实体(人物/物品/地点/组织/功法), 登记本章出现的别名与可见属性(年龄/境界/生死/位置/所属/所有者等)。
- state_changes: 实体状态的明确变化。attr 取 生死/境界/位置/所有者/所属/状态/称谓 等; kind 用一个动词(死亡/复活/升级/废功/交易/赠予/移师/改名/拜师/加入/退出…)。
- events: 关键情节事件, entities 列出涉事实体名; 若正文明确给出事件发生地点, 填 location(用正文中的地名原词), 否则留空。
- relations: 本章新建立或解除的关系, kind 取 师徒/亲属/敌对/同门/主仆/朋友/所属 等, state 取 建立/解除。
- story_time: 本章故事内时间线索; markers 列出「三日后/翌日清晨/闪回」等时间标记; 仅当原文给出明确累计天数时填 day_offset, 否则填 null。
- 所有 quote 字段必须是章节原文的连续片段(不超过60字), 不得改写; 无依据的字段留空或省略。
- 宁可漏抽, 不可编造。"""


@lru_cache(maxsize=1)
def _schema_json() -> str:
    return json.dumps(ChapterExtraction.model_json_schema(), ensure_ascii=False)


def build_user_prompt(chapter: Chapter) -> str:
    header = f"【第{chapter.number}章 {chapter.title}】" if chapter.title else f"【第{chapter.number}章】"
    return (
        f"{INSTRUCTIONS}\n\n# 输出 JSON Schema\n```json\n{_schema_json()}\n```\n\n"
        f"# 章节正文\n{header}\n{chapter.text}"
    )


def build_messages(chapter: Chapter) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(chapter)},
    ]
