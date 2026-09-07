"""软验证器（M2）：persona 读者模拟 + 三指标（意外感/连贯/伏笔回收公平性）。

v0 占位：先固定 persona 契约与内置画像；模拟实现在 M2 落地（PLAN §5）。
persona 漂移缓解（PLAN §8）：评估限制在单章短窗，每次调用重新锚定人设 brief。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Persona", "BUILTIN_PERSONAS", "ReadersNotImplemented", "simulate"]


@dataclass(frozen=True)
class Persona:
    """一个模拟读者的最小锚定描述：短窗评估时整段注入 prompt。"""

    name: str
    brief: str


BUILTIN_PERSONAS: tuple[Persona, ...] = (
    Persona(name="追更爽点型", brief="追更新读者：期待打脸与升级节奏，对拖沓敏感，只记得近几章情节。"),
    Persona(name="设定考据型", brief="设定党：逐条记录伏笔、数字与境界体系，对前后矛盾零容忍。"),
    Persona(name="沉浸代入型", brief="代入党：跟随主角视角，对动机断裂与人设崩坏敏感。"),
    Persona(name="老书虫挑剔型", brief="十年书龄：见多识广，对套路陈旧、巧合堆砌与说教敏感。"),
)


class ReadersNotImplemented(NotImplementedError):
    """M2 未实现的显式占位。"""


def simulate(*args: object, **kwargs: object) -> object:
    """persona 读者模拟（M2 实现）。当前调用即报 ReadersNotImplemented。"""
    raise ReadersNotImplemented("软验证器在 M2 实现：persona 模拟 + 三指标（见 PLAN §5/M2）")
