"""状态库测试：M0 验收核心——抽取→入库→回放往返稳定。"""

from __future__ import annotations

from canonkeeper.extract.schemas import StoryTime
from canonkeeper.store.db import StateDB
from helpers import change, entity, event, extraction


def test_rebuild_and_replay_roundtrip(db_path) -> None:
    exts = [
        extraction(
            1,
            entities=[entity("林昼", aliases=["林师弟"], attrs={"境界": "炼气三层"})],
            changes=[change("林昼", "境界", "炼气三层", old="炼气二层", kind="升级", quote="丹田一热，竟是破了。")],
            events=[event("登场", ["林昼"], quote="林昼睁开眼。")],
            story_time=StoryTime(start="清晨", end="入夜", markers=["翌日清晨"], day_offset=1),
        ),
        extraction(2, entities=[entity("林师弟")]),
    ]
    with StateDB(db_path) as db:
        db.rebuild(exts)
        assert db.extractions() == exts  # 往返一致
        assert db.get_extraction(2) is not None
        assert db.get_extraction(9) is None


def test_rebuild_is_idempotent(db_path) -> None:
    exts = [
        extraction(
            1,
            entities=[entity("甲"), entity("乙")],
            changes=[change("甲", "生死", "死亡", kind="死亡")],
        )
    ]
    with StateDB(db_path) as db:
        db.rebuild(exts)
        first = (db.entity_count(), len(db.state_changes()), len(db.extractions()))
        db.rebuild(exts)
        second = (db.entity_count(), len(db.state_changes()), len(db.extractions()))
        assert first == second


def test_unregistered_reference_backfills_unknown_entity(db_path) -> None:
    """变更/事件引用了未登记实体时兜底建「未知」实体，不丢引用。"""
    with StateDB(db_path) as db:
        db.rebuild([extraction(1, changes=[change("幽灵人", "位置", "北城")])])
        names = {row["name"]: row["type"] for row in db.list_entities()}
        assert names["幽灵人"] == "未知"


def test_alias_collisions_persisted_to_meta(db_path) -> None:
    exts = [
        extraction(1, entities=[entity("老王", aliases=["王掌柜"])]),
        extraction(2, entities=[entity("老李", aliases=["王掌柜"])]),
    ]
    with StateDB(db_path) as db:
        db.rebuild(exts)
        assert db.get_meta("alias_collisions") != ""


def test_violations_replace_semantics(db_path) -> None:
    from canonkeeper.store.db import Violation

    with StateDB(db_path) as db:
        db.replace_violations([Violation(rule_id="A", message="一")])
        db.replace_violations([Violation(rule_id="B", message="二")])
        rows = db.violations()
        assert len(rows) == 1 and rows[0]["rule_id"] == "B"
