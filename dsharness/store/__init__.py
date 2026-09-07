"""状态库：SQLite（stdlib sqlite3）+ 实体别名归一（PLAN §3）。"""

from .resolver import EntityResolver, ResolvedEntity
from .db import StateDB, Violation, build_book_view

__all__ = ["StateDB", "Violation", "EntityResolver", "ResolvedEntity", "build_book_view"]
