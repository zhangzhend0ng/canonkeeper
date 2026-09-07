"""实体归一（规则⑱ 的数据基础）：名字/别名 → 规范实体。

归一策略 v0（显式取舍）：首次 sighting 的 name 为规范名；名字相同即视为同一实体
（同名不同类型的罕见情形留给 ALIAS_001 冲突报告由人工裁决）。同一别名先后映射到
不同规范名时记入 collisions——这正是规则 META_018 的输入。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..extract.schemas import ChapterExtraction

__all__ = ["ResolvedEntity", "EntityResolver"]


@dataclass
class ResolvedEntity:
    entity_id: int
    name: str
    type: str
    aliases: set[str] = field(default_factory=set)
    attrs: dict[str, str] = field(default_factory=dict)  # 当前值；后章覆盖先章
    first_chapter: int = 0
    last_chapter: int = 0


class EntityResolver:
    """按章节顺序灌入抽取结果，维护 别名→实体 的归一索引。"""

    def __init__(self) -> None:
        self._next_id = 1
        self._by_alias: dict[str, int] = {}
        self.entities: dict[int, ResolvedEntity] = {}
        # 别名 → 指向过的全部实体 id（>1 即冲突）
        self.collisions: dict[str, set[int]] = {}

    # -- 查询 ---------------------------------------------------------------

    def lookup(self, name: str) -> ResolvedEntity | None:
        entity_id = self._by_alias.get(name)
        return self.entities.get(entity_id) if entity_id is not None else None

    # -- 写入 ---------------------------------------------------------------

    def ingest(self, extraction: ChapterExtraction) -> list[ResolvedEntity]:
        """灌入一章；返回本章涉及（新建或更新）的实体，按首次触及顺序去重。"""
        touched: list[ResolvedEntity] = []
        seen_this_chapter: set[int] = set()
        for mention in extraction.entities:
            entity = self._find_or_create(mention.name, mention.type, extraction.chapter)
            for alias in mention.aliases:
                self._find_or_create(alias, entity.type, extraction.chapter, merge_into=entity)
            entity.attrs.update(mention.attrs)
            entity.last_chapter = max(entity.last_chapter, extraction.chapter)
            if entity.entity_id not in seen_this_chapter:
                seen_this_chapter.add(entity.entity_id)
                touched.append(entity)
        return touched

    def ensure(self, name: str, chapter: int) -> ResolvedEntity:
        """按名字取实体；未登记（漏抽 mention）时兜底建「未知」类型实体，不丢引用。"""
        return self._find_or_create(name, "未知", chapter)

    # -- 内部 ---------------------------------------------------------------

    def _find_or_create(
        self, alias: str, entity_type: str, chapter: int, *, merge_into: ResolvedEntity | None = None
    ) -> ResolvedEntity:
        known = self.lookup(alias)
        if known is not None and (merge_into is None or known is merge_into):
            self._register_alias(alias, known.entity_id)
            return known
        if merge_into is not None:
            # 已知别名挂到了别的实体上 → 冲突登记，归一到 merge_into（首次 sighting 优先）
            self._register_alias(alias, merge_into.entity_id)
            return merge_into

        entity = ResolvedEntity(
            entity_id=self._next_id, name=alias, type=entity_type,
            aliases={alias}, first_chapter=chapter, last_chapter=chapter,
        )
        self._next_id += 1
        self.entities[entity.entity_id] = entity
        self._register_alias(alias, entity.entity_id)
        return entity

    def _register_alias(self, alias: str, entity_id: int) -> None:
        previous = self._by_alias.setdefault(alias, entity_id)
        if previous != entity_id:
            self.collisions.setdefault(alias, {previous, entity_id}).add(entity_id)
