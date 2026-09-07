"""规则引擎测试：谓词判定 + YAML 加载校验。判定纯程序化，全部可单测（PLAN §6 卖点）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from canonkeeper.extract.schemas import StoryTime
from canonkeeper.rules.engine import Rule, RuleError, load_builtin_rules, load_rules, run_rules
from canonkeeper.rules.predicates import PREDICATES
from canonkeeper.store.db import ChangeRec, EventRec
from helpers import make_view

DEATH_PARAMS: dict[str, object] = {
    "attr": "生死",
    "terminal_value": "死亡",
    "revive_kinds": ["复活", "复生"],
}

LADDER_PARAMS: dict[str, object] = {
    "attr": "境界",
    "ladder": ["炼气", "筑基", "金丹"],
    "regress_kinds": ["废功", "自废"],
}


def _death_view(*, revive_chapter: int | None = None):
    changes = [
        ChangeRec(1, 1, "登场", "", "", "", ""),
        ChangeRec(2, 1, "死亡", "生死", "存活", "死亡", "他断了气。"),
    ]
    if revive_chapter is not None:
        changes.append(ChangeRec(revive_chapter, 1, "复活", "生死", "死亡", "存活", "他又活了。"))
    return make_view(entities=["张三"], changes=changes, appearances={1: {1, 2, 4}})


# -- 终态复现（规则①⑨） ------------------------------------------------------


def test_death_then_reappearance_is_flagged_at_first_recurring_chapter() -> None:
    violations = PREDICATES["terminal_state_reuse"](_death_view(), DEATH_PARAMS)
    assert [v.chapter for v in violations] == [4]  # 第4章首次复现
    assert "死亡" in violations[0].message
    assert violations[0].evidence_quote == "他断了气。"


def test_registered_revive_between_clears_violation() -> None:
    view = _death_view(revive_chapter=3)
    assert PREDICATES["terminal_state_reuse"](view, DEATH_PARAMS) == []


def test_no_death_no_violation() -> None:
    view = make_view(entities=["张三"], changes=[ChangeRec(1, 1, "登场", "", "", "", "")],
                     appearances={1: {1, 2}})
    assert PREDICATES["terminal_state_reuse"](view, DEATH_PARAMS) == []


def test_destroyed_item_reuse_shares_same_predicate() -> None:
    view = make_view(
        entities=["诛仙剑"],
        changes=[ChangeRec(3, 1, "毁坏", "状态", "完好", "已毁", "剑碎了。")],
        appearances={1: {5}},
    )
    violations = PREDICATES["terminal_state_reuse"](
        view, {"attr": "状态", "terminal_value": "已毁", "revive_kinds": ["修复"]}
    )
    assert [v.chapter for v in violations] == [5]


# -- 境界单调（规则⑫） --------------------------------------------------------


def _realm_view(*tuples: tuple[int, str, str, str]):
    changes = [ChangeRec(ch, 1, kind, "境界", old, new, "") for ch, kind, old, new in tuples]
    return make_view(entities=["李四"], changes=changes)


def test_realm_drop_without_discard_is_flagged() -> None:
    view = _realm_view((1, "升级", "", "金丹"), (5, "受伤", "金丹", "炼气三层"))
    violations = PREDICATES["realm_regression"](view, LADDER_PARAMS)
    assert [v.chapter for v in violations] == [5]
    assert "金丹" in violations[0].message and "炼气" in violations[0].message


def test_realm_drop_with_registered_discard_is_clean() -> None:
    view = _realm_view((1, "升级", "", "金丹"), (5, "废功", "金丹", "炼气"))
    assert PREDICATES["realm_regression"](view, LADDER_PARAMS) == []


def test_realm_rise_is_clean() -> None:
    view = _realm_view((1, "升级", "", "炼气一层"), (2, "升级", "炼气一层", "筑基"))
    assert PREDICATES["realm_regression"](view, LADDER_PARAMS) == []


def test_off_ladder_values_are_skipped_not_misflagged() -> None:
    """阶梯外值（如自创境界）宁可漏报不误报。"""
    view = _realm_view((1, "升级", "", "金丹"), (5, "转职", "金丹", "星魂体"))
    assert PREDICATES["realm_regression"](view, LADDER_PARAMS) == []


# -- 别名归一（规则⑱）与时间单调（规则⑥） --------------------------------------


def test_alias_collision_reported_for_manual_review() -> None:
    view = make_view(entities=["老王", "老李"], collisions={"王掌柜": {1, 2}})
    violations = PREDICATES["alias_collision"](view, {})
    assert len(violations) == 1
    assert set(violations[0].entity_ids) == {1, 2}
    assert "王掌柜" in violations[0].message


def test_time_regression_without_flashback_is_flagged() -> None:
    view = make_view(timeline={1: StoryTime(day_offset=10), 2: StoryTime(day_offset=8)})
    violations = PREDICATES["time_regression"](view, {"flashback_markers": ["闪回"]})
    assert [v.chapter for v in violations] == [2]


def test_time_regression_with_flashback_marker_is_clean() -> None:
    view = make_view(
        timeline={
            1: StoryTime(day_offset=10),
            2: StoryTime(markers=["这段是闪回"], day_offset=3),
        }
    )
    assert PREDICATES["time_regression"](view, {"flashback_markers": ["闪回"]}) == []


def test_missing_day_offset_is_skipped() -> None:
    view = make_view(timeline={1: StoryTime(day_offset=10), 2: StoryTime()})
    assert PREDICATES["time_regression"](view, {"flashback_markers": ["闪回"]}) == []


# -- 引擎：回填与加载 ---------------------------------------------------------


def test_run_rules_attaches_rule_id_and_severity() -> None:
    rule = Rule(rule_id="T1", name="测试", severity="high",
                predicate="terminal_state_reuse", params=DEATH_PARAMS)
    violations = run_rules([rule], _death_view())
    assert violations[0].rule_id == "T1"
    assert violations[0].severity == "high"


def test_builtin_rules_load_and_all_predicates_known() -> None:
    rules = load_builtin_rules()
    assert {
        "CHAR_001", "CHAR_002", "CHAR_005", "CHAR_012",
        "ITEM_009", "ITEM_011", "META_018", "TIME_006",
    } <= {r.rule_id for r in rules}
    for rule in rules:
        assert rule.predicate in PREDICATES


def test_examples_custom_rules_load() -> None:
    path = Path(__file__).resolve().parents[1] / "examples" / "custom_rules.yaml"
    rules = load_rules([path])
    assert {r.rule_id for r in rules} == {"CUSTOM_012", "CUSTOM_002"}


def _write(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "rule.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_load_rules_rejects_unknown_predicate(tmp_path: Path) -> None:
    path = _write(tmp_path, "- rule_id: X\n  name: n\n  severity: high\n  predicate: no_such\n")
    with pytest.raises(RuleError, match="未知谓词"):
        load_rules([path])


def test_load_rules_rejects_bad_severity(tmp_path: Path) -> None:
    path = _write(tmp_path, "- rule_id: X\n  name: n\n  severity: 极高\n  predicate: alias_collision\n")
    with pytest.raises(RuleError, match="severity"):
        load_rules([path])


def test_load_rules_rejects_duplicate_rule_id(tmp_path: Path) -> None:
    content = "- rule_id: SAME\n  name: n\n  severity: low\n  predicate: alias_collision\n"
    with pytest.raises(RuleError, match="重复"):
        load_rules([_write(tmp_path, content), _write(tmp_path, content)])


# -- 数值属性单调（规则②，年龄为例） ---------------------------------------------


AGE_PARAMS: dict[str, object] = {"attr": "年龄", "regress_kinds": ["重生"]}


def test_age_drop_without_rebirth_is_flagged() -> None:
    view = make_view(
        entities=["王五"],
        changes=[
            ChangeRec(1, 1, "登场", "年龄", "", "十六岁", ""),
            ChangeRec(9, 1, "变更", "年龄", "十六岁", "十四", ""),
        ],
    )
    violations = PREDICATES["numeric_attr_monotonic"](view, AGE_PARAMS)
    assert [v.chapter for v in violations] == [9]
    assert "十四" in violations[0].message  # 中文数字已参与比较


def test_age_drop_with_registered_rebirth_is_clean() -> None:
    view = make_view(
        entities=["王五"],
        changes=[
            ChangeRec(1, 1, "登场", "年龄", "", "十六岁", ""),
            ChangeRec(9, 1, "重生", "年龄", "十六岁", "十四", ""),
        ],
    )
    assert PREDICATES["numeric_attr_monotonic"](view, AGE_PARAMS) == []


def test_non_numeric_age_values_are_skipped() -> None:
    view = make_view(
        entities=["王五"],
        changes=[
            ChangeRec(1, 1, "登场", "年龄", "", "幼年", ""),
            ChangeRec(8, 1, "变更", "年龄", "幼年", "十七岁", ""),
        ],
    )
    assert PREDICATES["numeric_attr_monotonic"](view, AGE_PARAMS) == []


# -- 位置连续性（规则⑤） --------------------------------------------------------


def _loc_event(chapter: int, location: str) -> EventRec:
    return EventRec(chapter=chapter, kind="战斗", entity_ids=(1,), quote="", location=location)


def test_teleport_without_move_registration_is_flagged() -> None:
    view = make_view(
        entities=["林昼"],
        changes=[ChangeRec(2, 1, "抵达", "位置", "", "青云宗", "")],
        events=[_loc_event(4, "南疆")],
    )
    violations = PREDICATES["location_continuity"](view, {"location_attr": "位置"})
    assert [v.chapter for v in violations] == [4]
    assert "南疆" in violations[0].message


def test_place_containment_counts_as_same_place() -> None:
    view = make_view(
        entities=["林昼"],
        changes=[ChangeRec(2, 1, "抵达", "位置", "", "青云宗", "")],
        events=[_loc_event(4, "青云宗大殿")],
    )
    assert PREDICATES["location_continuity"](view, {"location_attr": "位置"}) == []


def test_same_chapter_location_change_registers_move() -> None:
    view = make_view(
        entities=["林昼"],
        changes=[
            ChangeRec(2, 1, "抵达", "位置", "", "青云宗", ""),
            ChangeRec(4, 1, "移师", "位置", "青云宗", "南疆", ""),
        ],
        events=[_loc_event(4, "南疆")],
    )
    assert PREDICATES["location_continuity"](view, {"location_attr": "位置"}) == []


def test_event_without_location_is_skipped() -> None:
    view = make_view(
        entities=["林昼"],
        changes=[ChangeRec(2, 1, "抵达", "位置", "", "青云宗", "")],
        events=[EventRec(chapter=4, kind="战斗", entity_ids=(1,), quote="")],
    )
    assert PREDICATES["location_continuity"](view, {"location_attr": "位置"}) == []


# -- 所有权转移登记（规则⑪） ------------------------------------------------------


TRANSFER_PARAMS: dict[str, object] = {
    "event_kinds": ["交易", "赠予"],
    "ownership_attrs": ["所有者"],
    "window": 1,
}


def _trade_view(item_type: str = "物品", *, owner_change_chapter: int | None = None):
    changes = [ChangeRec(2, 1, "登场", "状态", "", "完好", "")]
    if owner_change_chapter is not None:
        changes.append(ChangeRec(owner_change_chapter, 1, "交易", "所有者", "张三", "李四", ""))
    return make_view(
        entities=["储物袋", "张三", "李四"],
        entity_types={"储物袋": item_type},
        changes=changes,
        events=[EventRec(chapter=5, kind="交易", entity_ids=(1, 2, 3), quote="钱货两讫。")],
    )


def test_trade_without_ownership_change_is_flagged() -> None:
    violations = PREDICATES["transfer_registered"](_trade_view(), TRANSFER_PARAMS)
    assert [v.chapter for v in violations] == [5]
    assert "储物袋" in violations[0].message


def test_trade_with_nearby_ownership_change_is_clean() -> None:
    assert PREDICATES["transfer_registered"](_trade_view(owner_change_chapter=5), TRANSFER_PARAMS) == []
    assert PREDICATES["transfer_registered"](_trade_view(owner_change_chapter=6), TRANSFER_PARAMS) == []


def test_trade_without_item_entity_is_skipped() -> None:
    view = _trade_view(item_type="人物")
    assert PREDICATES["transfer_registered"](view, TRANSFER_PARAMS) == []
