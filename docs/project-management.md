# Project management

abax turns an ordinary sheet into a **task tracker** with ten live views, CPM
scheduling, scenario analysis, import/export, and budget roll-up — because a
spreadsheet that already holds your data is a natural place to manage work.

Open it from **Project** in the menu bar (or the command palette: type
"Project:").

## Quick start

1. Create a sheet with headers: `Title | Status | Start | Due | Assignee | Effort | Cost`.
2. Fill in some tasks below them.
3. **Project > New project from sheet…** — name it and confirm the
   auto-detected columns.
4. **Project > Open project views** — the dockable PM panel opens with ten
   tabs.

## The ten views

| View | What it shows |
|------|---------------|
| **Kanban** | Draggable cards grouped by status column. |
| **Card** | Responsive grid of task cards with sort and filter. |
| **Calendar** | Month grid; drag a task to reschedule. |
| **Gantt** | Draggable bars, dependency arrows, critical-path highlight. |
| **Timeline** | Swim lanes grouped by assignee. |
| **Dashboard** | KPI tiles, health table, milestone summary. |
| **Roadmap** | Multi-project timeline with cross-project links. |
| **Resources** | People × weeks workload heatmap. |
| **Budget** | Budget vs. actual bars, EVM KPI tiles (CPI / SPI). |
| **OKRs** | Objectives and key results. |

All views read from the same task sheet — edit a cell and the views update on
the next refresh.

## Scheduling

**Project > Schedule** runs critical-path method (CPM) scheduling.  abax
computes early/late start and finish dates, total float, and flags the
critical path.  Results are written back to the sheet in-place.

## Import and export

| Action | Menu | What happens |
|--------|------|--------------|
| **Import tasks** | Project > Import tasks… | Open a CSV (delimiter auto-detected) or MS Project XML export. Tasks are appended to the current sheet. |
| **Export Gantt SVG** | Project > Export Gantt SVG… | Saves a colour-keyed Gantt chart as an SVG file. |
| **Export report** | Project > Export report… | Generates an HTML status report with per-project tables, task summaries, and milestones. |

The CLI can generate reports headlessly:

```bash
abax report portfolio.abax -o status.html
```

## Scenarios (what-if)

**Project > Scenarios…** opens the scenario editor where you can override task
fields (dates, effort, cost, assignee, status) without touching the sheet.
Click **Apply to Sheet** to commit the overrides as a single undo step — one
`Ctrl+Z` reverts the entire batch.

## Programmatic access

The PM engine is pure stdlib (`abax/core/pm/`), so you can use it from the
Python console or a script:

```python
from abax.core.pm.taskmodel import parse_tasks
from abax.core.pm.schedule import schedule
from abax.core.pm.exporter import export_gantt_svg

tasks = parse_tasks(sheet, col_map)
schedule(tasks)
svg = export_gantt_svg(tasks, title="Sprint 12")
```

Key modules: `taskmodel` (Task dataclass, header detection, parse/write),
`projects` (project registry), `schedule` (CPM), `portfolio` (cross-project
analytics), `capacity` (resource planning), `finance` (budget roll-up, EVM,
scenarios), `importer` (CSV / MS Project XML), `exporter` (Gantt/timeline SVG,
PDF, reports), `pmsvg` (low-level SVG renderers).

## See also

- [GUI guide](gui-guide.md) — Project menu reference.
- [CLI reference](cli.md) — `report` subcommand.
- [Examples: task tracking](examples/project-management/task-tracking/README.md) — walkthrough.
- [Architecture](architecture.md) — `core/pm/` module map.
