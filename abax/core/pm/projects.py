"""Project registry — named project definitions stored in the workbook envelope.

Mirrors :mod:`abax.core.tables`: a :class:`Project` holds the geometry and
configuration for one task-sheet project, and :class:`ProjectRegistry` is the
case-insensitive ``name → Project`` store that the integrator attaches to the
workbook.  Envelope-serialized, structural-edit aware (region shifts on
row/col insert/delete, like Tables do).

This module is pure stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "Project",
    "ProjectRegistry",
    "CrossProjectLink",
    "Milestone",
    "Objective",
    "KeyResult",
]


# ---------------------------------------------------------------------------
# Supporting dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Milestone:
    """A named milestone within a project."""

    name: str
    date: str = ""
    done: bool = False

    def to_dict(self) -> dict:
        return {"name": self.name, "date": self.date, "done": self.done}

    @classmethod
    def from_dict(cls, d: dict) -> Milestone:
        return cls(
            name=d.get("name", ""),
            date=d.get("date", ""),
            done=bool(d.get("done", False)),
        )


@dataclass
class CrossProjectLink:
    """A dependency link between tasks in different projects."""

    from_project: str
    from_id: str
    to_project: str
    to_id: str

    def to_dict(self) -> dict:
        return {
            "from_project": self.from_project,
            "from_id": self.from_id,
            "to_project": self.to_project,
            "to_id": self.to_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CrossProjectLink:
        return cls(
            from_project=d.get("from_project", ""),
            from_id=d.get("from_id", ""),
            to_project=d.get("to_project", ""),
            to_id=d.get("to_id", ""),
        )


@dataclass
class KeyResult:
    """One key result under an objective."""

    name: str
    target: float = 100.0
    current_formula: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "target": self.target,
            "current_formula": self.current_formula,
        }

    @classmethod
    def from_dict(cls, d: dict) -> KeyResult:
        return cls(
            name=d.get("name", ""),
            target=float(d.get("target", 100.0)),
            current_formula=d.get("current_formula", ""),
        )


@dataclass
class Objective:
    """An OKR objective with key results."""

    objective: str
    key_results: list[KeyResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "objective": self.objective,
            "key_results": [kr.to_dict() for kr in self.key_results],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Objective:
        return cls(
            objective=d.get("objective", ""),
            key_results=[
                KeyResult.from_dict(kr) for kr in d.get("key_results", [])
            ],
        )


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


@dataclass
class Project:
    """A named project definition — geometry, view configs, milestones, OKRs.

    Geometry fields mirror :class:`~abax.core.tables.Table`: ``sheet``,
    ``header_row``, ``first_data_row``, ``last_data_row``, ``first_col``,
    ``last_col``.  Alternatively, ``table_ref`` names a Table whose geometry
    is used (the Table's bounds track structural edits automatically).
    """

    name: str
    sheet: str = ""
    header_row: int = 0
    first_data_row: int = 1
    last_data_row: int = -1
    first_col: int = 0
    last_col: int = -1
    table_ref: str = ""
    default_view: str = "kanban"
    view_configs: dict[str, Any] = field(default_factory=dict)
    milestones: list[Milestone] = field(default_factory=list)
    cross_links: list[CrossProjectLink] = field(default_factory=list)
    budget_total: float = 0.0
    objectives: list[Objective] = field(default_factory=list)

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"name": self.name}
        if self.table_ref:
            d["table_ref"] = self.table_ref
        else:
            d["sheet"] = self.sheet
            d["header_row"] = self.header_row
            d["first_data_row"] = self.first_data_row
            d["last_data_row"] = self.last_data_row
            d["first_col"] = self.first_col
            d["last_col"] = self.last_col
        d["default_view"] = self.default_view
        if self.view_configs:
            d["view_configs"] = dict(self.view_configs)
        if self.milestones:
            d["milestones"] = [m.to_dict() for m in self.milestones]
        if self.cross_links:
            d["cross_links"] = [cl.to_dict() for cl in self.cross_links]
        if self.budget_total:
            d["budget_total"] = self.budget_total
        if self.objectives:
            d["objectives"] = [o.to_dict() for o in self.objectives]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        return cls(
            name=d.get("name", ""),
            sheet=d.get("sheet", ""),
            header_row=int(d.get("header_row", 0)),
            first_data_row=int(d.get("first_data_row", 1)),
            last_data_row=int(d.get("last_data_row", -1)),
            first_col=int(d.get("first_col", 0)),
            last_col=int(d.get("last_col", -1)),
            table_ref=d.get("table_ref", ""),
            default_view=d.get("default_view", "kanban"),
            view_configs=dict(d.get("view_configs", {})),
            milestones=[Milestone.from_dict(m) for m in d.get("milestones", [])],
            cross_links=[
                CrossProjectLink.from_dict(cl)
                for cl in d.get("cross_links", [])
            ],
            budget_total=float(d.get("budget_total", 0.0)),
            objectives=[
                Objective.from_dict(o) for o in d.get("objectives", [])
            ],
        )

    # -- structural-edit support --------------------------------------------

    def shift_rows(self, at_row: int, delta: int) -> None:
        """Adjust row bounds after rows are inserted (delta > 0) or deleted
        (delta < 0) at *at_row* on this project's sheet."""
        if self.table_ref:
            return
        if delta > 0:
            if at_row <= self.header_row:
                self.header_row += delta
            if at_row <= self.first_data_row:
                self.first_data_row += delta
            if at_row <= self.last_data_row:
                self.last_data_row += delta
        elif delta < 0:
            count = -delta
            if at_row + count <= self.header_row:
                self.header_row += delta
            if at_row + count <= self.first_data_row:
                self.first_data_row += delta
            if at_row + count <= self.last_data_row:
                self.last_data_row += delta

    def shift_cols(self, at_col: int, delta: int) -> None:
        """Adjust column bounds after columns are inserted/deleted."""
        if self.table_ref:
            return
        if delta > 0:
            if at_col <= self.first_col:
                self.first_col += delta
            if at_col <= self.last_col:
                self.last_col += delta
        elif delta < 0:
            count = -delta
            if at_col + count <= self.first_col:
                self.first_col += delta
            if at_col + count <= self.last_col:
                self.last_col += delta


# ---------------------------------------------------------------------------
# ProjectRegistry
# ---------------------------------------------------------------------------


class ProjectRegistry:
    """Case-insensitive registry of :class:`Project` objects.

    Mirrors :class:`~abax.core.tables.TableRegistry`: keyed on upper-cased
    project name, preserving display case.
    """

    def __init__(self) -> None:
        self._by_upper: dict[str, Project] = {}
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def touch(self) -> None:
        self._version += 1

    def __len__(self) -> int:
        return len(self._by_upper)

    def __iter__(self):
        return iter(self._by_upper.values())

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.upper() in self._by_upper

    def add(self, project: Project) -> None:
        self._by_upper[project.name.upper()] = project
        self._version += 1

    def get(self, name: str) -> Project | None:
        return self._by_upper.get(name.upper())

    def has(self, name: str) -> bool:
        return name.upper() in self._by_upper

    def remove(self, name: str) -> None:
        key = name.upper()
        if key not in self._by_upper:
            raise KeyError(f"no such project: {name!r}")
        del self._by_upper[key]
        self._version += 1

    def rename(self, old: str, new: str) -> None:
        old_key = old.upper()
        if old_key not in self._by_upper:
            raise KeyError(f"no such project: {old!r}")
        new_key = new.upper()
        if new_key != old_key and new_key in self._by_upper:
            raise KeyError(f"project already exists: {new!r}")
        project = self._by_upper.pop(old_key)
        project.name = new
        self._by_upper[new_key] = project
        self._version += 1

    def names(self) -> list[str]:
        return sorted((p.name for p in self._by_upper.values()), key=str.upper)

    def for_sheet(self, sheet: str) -> list[Project]:
        """Return all projects whose data lives on *sheet*."""
        return [p for p in self._by_upper.values() if p.sheet == sheet]

    def shift_rows(self, sheet: str, at_row: int, delta: int) -> None:
        """Propagate a row insert/delete to every project on *sheet*."""
        for p in self._by_upper.values():
            if p.sheet == sheet:
                p.shift_rows(at_row, delta)
        self._version += 1

    def shift_cols(self, sheet: str, at_col: int, delta: int) -> None:
        """Propagate a column insert/delete to every project on *sheet*."""
        for p in self._by_upper.values():
            if p.sheet == sheet:
                p.shift_cols(at_col, delta)
        self._version += 1

    # -- serialization ------------------------------------------------------

    def to_dict(self) -> dict:
        return {p.name: p.to_dict() for p in self._by_upper.values()}

    @classmethod
    def from_dict(cls, d: dict) -> ProjectRegistry:
        reg = cls()
        for payload in d.values():
            reg.add(Project.from_dict(payload))
        return reg
