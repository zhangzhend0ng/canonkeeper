"""LLM 结构化输出契约（抽取层 ↔ 状态库的唯一数据形状，PLAN §3 的来源）。

信任边界（input-deserialization harness，N 级）：模型输出按不可信输入处理——
只有通过本模块 pydantic 验证的对象才允许进入业务逻辑。未知字段显式忽略
（`extra="ignore"`）：兼容端点的 JSON 行为不稳定，多余字段不得进入状态库，
但也不值得为无害冗余消耗重试；本注释即为该取舍的文档化。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

__all__ = [
    "ENTITY_TYPES",
    "EntityMention",
    "Event",
    "Relation",
    "StateChange",
    "StoryTime",
    "ChapterExtraction",
]

ENTITY_TYPES: tuple[str, ...] = ("人物", "物品", "地点", "组织", "功法")

# 代词/泛称不得成为别名：闭集判定放代码（可复现、零漂移），不依赖模型自觉
_PRONOUN_ALIASES = frozenset(
    {
        "他", "她", "它", "对方", "这人", "那人", "此人",
        "该男子", "该女子", "此女", "此男", "那名男子", "那名女子", "这位",
    }
)


class _StrictBase(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class EntityMention(_StrictBase):
    """本章出场/被提及的实体登记。attrs 为本章可见的属性快照（后章覆盖先章）。"""

    name: str = Field(min_length=1)
    type: str = "人物"
    aliases: list[str] = Field(default_factory=list)
    attrs: dict[str, str] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: Any) -> str:
        text = str(value)
        for entity_type in ENTITY_TYPES:
            if entity_type in text:
                return entity_type
        return "人物"

    @field_validator("aliases", mode="before")
    @classmethod
    def _drop_pronoun_aliases(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [a for a in value if str(a).strip() not in _PRONOUN_ALIASES]
        return value


class StateChange(_StrictBase):
    """一次明确的状态迁移。quote 必须是原文连续片段。chapter 由管线覆盖为权威值。"""

    entity: str = Field(min_length=1)
    attr: str = Field(min_length=1)  # 生死/境界/位置/所有者/所属/状态/称谓…
    new: str = Field(min_length=1)
    old: str = ""
    kind: str = "变更"  # 死亡/复活/升级/废功/交易/赠予/移师/改名/拜师…
    chapter: int = 0
    quote: str = ""


class Event(_StrictBase):
    """关键情节事件。entities 为涉事实体名（未登记名由状态库兜底建未知实体）。
    location 仅在正文明确给出事件发生地时填写（供位置连续性规则使用，缺失即跳过）。"""

    kind: str = Field(min_length=1)  # 登场/死亡/交易/升级/移师/改名/战斗…
    entities: list[str] = Field(default_factory=list)
    payload: dict[str, str] = Field(default_factory=dict)
    quote: str = ""
    location: str = ""

    @field_validator("payload", mode="before")
    @classmethod
    def _flatten_payload(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {str(k): str(v) for k, v in value.items()}


class Relation(_StrictBase):
    """人物/组织关系建立或解除。"""

    subject: str = Field(min_length=1)
    object: str = Field(min_length=1)
    kind: str = Field(min_length=1)  # 师徒/亲属/敌对/同门/主仆/朋友/所属…
    state: str = "建立"  # 建立/解除


class StoryTime(_StrictBase):
    """本章故事内时间线索。day_offset 仅在原文给出明确累计天数时由模型填写。"""

    start: str = ""
    end: str = ""
    markers: list[str] = Field(default_factory=list)  # 三日后/翌日清晨/闪回…
    day_offset: int | None = None


class ChapterExtraction(_StrictBase):
    """单章抽取结果。chapter 由抽取管线覆盖为本章权威序号。"""

    chapter: int
    title: str = ""
    summary: str = ""
    entities: list[EntityMention] = Field(default_factory=list)
    state_changes: list[StateChange] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    story_time: StoryTime = Field(default_factory=StoryTime)
