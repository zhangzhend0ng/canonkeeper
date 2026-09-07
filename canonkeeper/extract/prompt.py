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
从下面的章节正文中做完备的结构化抽取。本结果是设定一致性检查的数据底座：漏记 = 检查盲区。
- 实体完备: 登记正文中出现的全部具名实体(人物/物品/材料/技能/地点/组织), 有名字就要登记, 不要只挑主要角色; aliases 收全本章出现的所有称呼。注意: 代词与泛指(他/她/它/对方/这家伙/那人)不得进 aliases; 材料与道具(草药/矿石/布料/药水)的 type 是 物品 不是 人物; 技能与功法(招式/书)的 type 是 功法; AI/系统类存在按其载体定(应用/道具→物品)。
- 数字纪律(最重要): 正文出现的每一个数值都必须落库, 禁止遗漏——
  · 持续属性 → 实体 attrs: 余额/剩余次数/每日额度/等级/单价标签/库存/上下文上限/截止日期/公测日期/位置等;
  · 一次性事实 → 所在 event 的 payload: 单价/数量/总价/利润/成本/时长/次数/人数/距离/期限/酬金等;
  · 例: 售卖药水事件 payload 应含 {定价:3金币, 数量:7瓶, 时长:17分钟, 利润:16金币}。数值保留原文写法。
- 状态变更: 实体属性每发生一次变化记一条 state_change(余额/剩余次数/位置/等级/所有者/生死/连接状态…), old 尽量回填上一值; 每条都必须带原文 quote。
- 事件完备: 覆盖全部情节节拍(交易/摆摊/租借/委托/战斗/邮件/接近/警告/回忆闪回…), 不只挑主线大事件; payload 按数字纪律填。
- relations: 本章新建立或解除的关系(师徒/亲属/敌对/同门/主仆/朋友/所属/雇佣等), state 取 建立/解除。
- story_time: 本章故事内时间; markers 收集「三日前/翌日/凌晨四点」等全部时间标记; day_offset 填相对故事开局的累计天数(可推断才填, 否则 null)。
- quote 必须是章节原文的连续片段(不超过60字), 不得改写。
- 禁止编造原文没有的实体与数值; 反过来, 原文出现的数值与实体不得遗漏。"""


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
