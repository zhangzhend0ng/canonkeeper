"""实体归一测试（规则⑱ 的数据基础）。"""

from __future__ import annotations

from dsharness.store.resolver import EntityResolver
from helpers import entity, extraction


def test_first_seen_name_is_canonical() -> None:
    resolver = EntityResolver()
    resolver.ingest(extraction(1, entities=[entity("林昼", aliases=["林师弟"])]))
    resolver.ingest(extraction(2, entities=[entity("林师弟", attrs={"境界": "筑基"})]))
    found = resolver.lookup("林师弟")
    assert found is not None
    assert found.name == "林昼"
    assert found.attrs == {"境界": "筑基"}  # 后章属性覆盖
    assert found.first_chapter == 1 and found.last_chapter == 2


def test_alias_pointing_to_two_entities_is_collision() -> None:
    resolver = EntityResolver()
    resolver.ingest(extraction(1, entities=[entity("老王", aliases=["王掌柜"])]))
    resolver.ingest(extraction(2, entities=[entity("老李", aliases=["王掌柜"])]))
    assert resolver.collisions["王掌柜"] == {1, 2}


def test_ensure_merges_with_existing_entity() -> None:
    resolver = EntityResolver()
    resolver.ingest(extraction(1, entities=[entity("青云宗", entity_type="组织")]))
    found = resolver.ensure("青云宗", 2)
    assert found.entity_id == 1
    assert found.type == "组织"


def test_ensure_backfills_unknown_for_unregistered_name() -> None:
    resolver = EntityResolver()
    found = resolver.ensure("从天而降的人", 3)
    assert found.type == "未知"
    assert found.first_chapter == 3
