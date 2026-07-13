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

That's it — you have a live Kanban, Gantt chart, calendar, and more, all
reading from the same sheet. Edit a cell and the views update on the next
refresh.

---

## Task model

Every PM feature builds on the **Task dataclass** (`abax/core/pm/taskmodel.py`).
A task is a row in your sheet, described by these fields:

| Field | Type | Source header aliases |
|-------|------|----------------------|
| `title` | str | Title, Task, Name, Summary, Subject |
| `status` | str | Status |
| `start` | date or None | Start |
| `due` | date or None | Due, End, Finish, Deadline |
| `assignee` | str | Assignee, Owner, Who, Resource |
| `effort` | float or None | Effort, Hours, Estimate, Duration, Work |
| `cost` | float or None | Cost, Budget |
| `priority` | str | Priority |
| `percent_done` | float | % Done, Progress, Complete, % Complete, Pct |
| `depends` | list[str] | Depends, DependsOn, Blocked By, Predecessors |
| `tags` | list[str] | Tags, Labels, Category |
| `id` | str | ID, Key, TaskID, UID |
| `milestone` | bool | *(auto-detected from task type)* |

Header matching is **case-insensitive** and alias-aware — abax tries to map
your existing headers automatically. You can use headers from MS Project, Jira
CSV exports, or your own naming and they will usually just work. The column
picker in **Project > New project from sheet…** lets you override anything the
auto-detection gets wrong.

### The write-back protocol

Views that allow editing (Kanban drag-and-drop, Calendar reschedule, Gantt bar
drag) follow a strict protocol:

1. Update the Task dataclass field.
2. Call `write_task` to persist the change to the sheet cell.
3. The write goes through an `on_set` callback that creates an undo checkpoint.

This means every change made through a PM view is undoable with `Ctrl+Z`, just
like a manual cell edit.

---

## The ten views

### Kanban

Draggable cards grouped by your **Status** column. Drag a card from "To Do" to
"In Progress" and the underlying cell updates. Cards show the task title,
assignee, and due date.

### Card / Gallery

A responsive grid of task cards with sort and filter controls. Good for getting
an overview when you have many tasks — the grid reflows to fit the panel width.

### Calendar

A month grid. Tasks span from their start to their due date as coloured bars.
**Drag a task to reschedule** — the start and due dates update in the sheet.
Milestones appear as diamonds on their due date.

### Gantt

The classic project-management view:

- **Draggable bars** — grab a bar's edge to change a date, or its body to
  shift the whole task.
- **Dependency arrows** — drawn from each task to its successors (from the
  Depends column).
- **Critical-path highlight** — colours critical-path tasks red. Run
  **Project > Schedule (CPM)…** to compute the critical path and push it to the
  Gantt (and Roadmap) views — see [Scheduling](#scheduling).
- **Today line** — a vertical marker for the current date.
- **Month axis** — auto-scaled to fit the project's date range.

### Timeline

Horizontal swim lanes, one per **assignee**. Shows who is working on what and
when, and makes overlaps and gaps visible at a glance.

### Dashboard

A portfolio-level overview with:

- **KPI tiles** — total tasks, done count, overdue count, overall progress.
- **Health table** — one row per project with a Green / Amber / Red health
  indicator (based on the ratio of overdue tasks).
- **Milestone summary** — how many milestones are done vs. total.

The Dashboard aggregates data from **all registered projects**, not just the
active one — it is the place to get the big picture.

### Roadmap

A multi-project timeline. Each project gets a horizontal lane; task bars are
stacked within it. **Cross-project links** (set up via the Project dataclass)
are drawn as dashed arrows between projects, showing upstream/downstream
dependencies.

### Resources

A **people x weeks workload heatmap**. Each cell shows how many hours an
assignee has scheduled in that week. Cells turn red when someone is
overallocated.

The underlying engine (`abax/core/pm/capacity.py`) also provides
overallocation detection, skill matching, and a `suggest_reassignment` helper
for rebalancing work.

### Budget

Two panels:

- **Budget vs. actual bars** — one bar per project (or per task group)
  comparing the planned cost to the actual cost accrued.
- **EVM KPI tiles** — Earned Value Management metrics:
  - **PV** (Planned Value) — the budget for work scheduled.
  - **EV** (Earned Value) — the budget for work actually completed.
  - **AC** (Actual Cost) — what was spent.
  - **SPI** (Schedule Performance Index) — EV / PV (> 1 is ahead).
  - **CPI** (Cost Performance Index) — EV / AC (> 1 is under budget).
  - **EAC** (Estimate at Completion) — projected total cost.

Fill in the **Cost** and **Effort** columns and EVM lights up automatically.

### OKRs

Objectives and Key Results, defined on the Project object. Each objective has a
list of key results; a key result has a `target` value and a `current_formula`
that can reference sheet cells, so progress updates automatically as you work.

---

## Scheduling

The **Critical Path Method (CPM)** scheduler lives in
`abax/core/pm/schedule.py`. Run it from the GUI with
**Project > Schedule (CPM)…** (or the command palette:
"Project: Schedule (CPM)…"), or call it programmatically from the Python
console or a script. Either way the pipeline is the same:

1. **Build the DAG** from the Depends column.
2. **Detect cycles** (DFS colouring) — if any exist, the cycle is reported
   and scheduling stops.
3. **Topological sort** (Kahn's algorithm) — establishes task order.
4. **Forward pass** — computes early start and early finish for each task.
5. **Backward pass** — computes late start and late finish.
6. **Slack** — the difference between late and early start; tasks with zero
   slack form the **critical path**.

`compute_cpm(tasks)` returns a `CpmResult` per task (`early_start`,
`early_finish`, `late_start`, `late_finish`, `slack_days`, `critical`); it
does not modify the sheet. **Project > Schedule (CPM)…** runs it on the active
project, then feeds the critical-path IDs to the Gantt and Roadmap views'
`setCritical(ids)` slots so those tasks turn red; the status bar reports how
many tasks are on the critical path. To persist proposed dates instead, write
them back with `write_task` (see
[Programmatic access](#programmatic-access)). Date arithmetic is business-day
aware (weekends are skipped).

### Auto-schedule

`auto_schedule(tasks, start_date, hours_per_day)` goes further: given a
project start date and a daily capacity, it proposes concrete start and finish
dates for every task, respecting dependencies and skipping weekends. The return
value is a list of `(task_id, suggested_start, suggested_finish)` tuples.

### Slip-impact analysis

The portfolio engine (`abax/core/pm/portfolio.py`) includes `slip_impact`,
which cascades a delay through the dependency graph via CPM to show how
slipping one task affects downstream tasks — potentially across projects.

---

## Scenarios (what-if analysis)

Scenarios let you explore alternative plans **without touching the sheet**.

### Opening the scenario editor

**Project > Scenarios…** opens a dialog with two panels:

| Panel | What it shows |
|-------|---------------|
| **Left: Scenario list** | Named scenarios. A starter "Scenario 1" is created automatically. Click **Add** to create more; **Remove** to delete. |
| **Right: Override table** | The overrides for the selected scenario — columns: Task ID, Field, Original value, New value. |

### Creating overrides

Below the override table is a row of controls:

1. **Task combo** — pick the task to override (shows `ID: Title`).
2. **Field combo** — choose which field to change: `start`, `due`, `effort`,
   `cost`, `assignee`, `status`, or `percent_done`.
3. **New value** — type the replacement value.
4. Click **Add Override**.

The override appears in the table, with the **Original** column showing what
the task currently has in the sheet. You can add multiple overrides to a single
scenario — different fields on the same task, or overrides on different tasks.

### Applying a scenario

At the bottom of the dialog:

| Button | Effect |
|--------|--------|
| **Apply to Sheet** | Writes every override to the sheet as a **single undo step**. One `Ctrl+Z` reverts the entire batch. The dialog closes. |
| **Keep as Scenario** | Closes the dialog without changing the sheet, but **saves the scenario definitions on the project**. They are stored in the workbook envelope, so they survive save/load and reappear (with their overrides) the next time you open **Project > Scenarios…**. |
| **Cancel** | Discards everything (including edits to the scenario list) and closes without saving. |

Both **Apply to Sheet** and **Keep as Scenario** persist the current scenario
list onto the project; only **Cancel** leaves it untouched.

### What happens under the hood

When you click **Apply to Sheet**, abax calls
`apply_scenario_to_sheet(tasks, scenario, col_map, first_col, sheet, on_set)`:

1. For each override in the scenario, the engine locates the task's row and the
   target column via the column map.
2. `write_task` pushes the new value to the sheet through the `on_set` callback.
3. The callback creates an undo checkpoint tagged `"pm_scenario"`, so the
   entire batch is one undo group.
4. The function returns a change log: `[(task, field, old_value, new_value), …]`.

### Scenario delta (before/after comparison)

The engine provides `scenario_delta` — it applies the scenario to an
in-memory copy of the task list, re-runs CPM, and returns a before/after
comparison of finish dates and cost totals. The scenario editor calls it
**live**: the **Before / After Delta** area at the bottom of the dialog updates
every time you add or remove an override (or switch scenarios), showing the
project's old → new finish date (with the day delta) and old → new cost (with
the amount delta). The same function is also available from the Python console
/ scripts for headless analysis.

### Example workflow

> *"What if Alice's design phase slips two weeks?"*
>
> 1. Open **Project > Scenarios…**
> 2. Select "Scenario 1" (or create a new one).
> 3. Pick task **"Design UI"**, field **due**, new value **2026-08-29**.
> 4. Click **Add Override**.
> 5. If acceptable, click **Apply to Sheet**. If not, adjust or **Cancel** —
>    the sheet is untouched until you apply.

---

## Import and export

### Importing tasks

**Project > Import tasks…** opens a file dialog accepting:

| Format | Details |
|--------|---------|
| **CSV** | Delimiter auto-detected (comma, tab, semicolon, pipe). Headers are matched against the alias table, so a Jira export, a Trello CSV, or a hand-written file usually just works. BOM-safe. |
| **MS Project XML** | Parses the `http://schemas.microsoft.com/project` namespace. Extracts task name, UID, start, finish, duration, predecessors, milestone status, and percent complete. |

The parsed tasks are **appended to the active project's sheet**, in the first
free rows below the existing tasks, matched to the sheet's columns by the same
header-alias detection. The whole import is a **single undo step** — one
`Ctrl+Z` removes every appended row. If the project's data range was
explicitly bounded, it grows to cover the new rows so the views pick them up.
Columns present in the file but not in the target sheet are ignored.

### Exporting

| Action | Menu path | Output |
|--------|-----------|--------|
| **Gantt SVG** | Project > Export Gantt SVG… | A colour-keyed SVG with bars, dependency arrows, critical-path colouring, milestone diamonds, and a today line. |
| **Timeline SVG** | *(via the Python API)* | Horizontal bars on a date axis, multi-lane, 8-colour palette. |
| **Status report (HTML)** | Project > Export report… | A self-contained HTML page with a summary table, embedded Gantt SVGs per project, and milestone checklists. |
| **Status report (Markdown)** | Project > Export report… | A Markdown document with a summary table and per-project detail sections (progress, health, overdue tasks, milestones as checkboxes). |

The file dialog for **Export report** offers both HTML and Markdown — save with
a `.md` extension (or select "Markdown files" in the filter) to get Markdown
output.

### CLI report

The `report` subcommand generates a report headlessly:

```bash
# HTML (default)
abax report portfolio.abax -o status.html

# Markdown
abax report portfolio.abax -o status.md
```

The output format is chosen by the file extension: `.md` produces Markdown,
anything else produces HTML. If `-o` is omitted the report is written to
`report.html` in the current directory.

---

## Resource capacity planning

The capacity module (`abax/core/pm/capacity.py`) provides:

| Function | What it does |
|----------|--------------|
| `workload_by_week` | Returns `{assignee: {week_monday_iso: hours}}` — the raw data behind the Resources heatmap. |
| `overallocation` | Flags assignees whose weekly hours exceed a configurable threshold. |
| `suggest_reassignment` | Given overallocated weeks, proposes moving tasks to under-loaded people. |
| `skill_match` | Matches tasks to people by skill tags. |
| `rebalance` | Redistributes work to even out the workload across the team. |

The Resources view in the GUI visualises `workload_by_week`; the other
functions are available from the Python console or scripts.

---

## Budget and Earned Value

The finance module (`abax/core/pm/finance.py`) provides:

### Budget roll-up

`budget_rollup(projects)` returns a dict with:

- `total_budget`, `total_cost`, `remaining` — portfolio-wide totals.
- `per_project` — a list of `{name, budget, cost, remaining, pct_used}` dicts.

### Burn tracking

`burn_by_completion` and `burn_by_elapsed` compute burn-down curves — the
former based on task completion percentage, the latter based on elapsed
calendar time.

### Earned Value Management

`evm(tasks, today, budget)` returns `{PV, EV, AC, SPI, CPI, EAC}`. The Budget
view shows these as KPI tiles.

---

## Portfolio analytics

When you have multiple projects registered in a workbook, the portfolio module
(`abax/core/pm/portfolio.py`) provides cross-project analysis:

| Function | What it computes |
|----------|------------------|
| `project_progress` | Effort-weighted progress per project. |
| `status_counts` | Counts by status category per project. |
| `overdue_tasks` | Tasks past their due date and not done. |
| `at_risk_tasks` | Tasks due within N days but less than 80% complete. |
| `milestone_schedule` | Milestone dates and done/not-done status. |
| `project_health` | Green / Amber / Red based on overdue ratio. |
| `portfolio_kpis` | Cross-project roll-up of all the above. |
| `resolve_cross_links` | Resolves cross-project dependency links. |
| `slip_impact` | Cascading delay analysis across projects via CPM. |

The Dashboard and Roadmap views surface these automatically.

---

## Milestones

Define milestones via **Project > Milestones…** — a simple text dialog where
each line is `name<tab>date<tab>done`. Milestones appear as diamonds in the
Gantt and Calendar views, and as a checklist in exported reports.

Milestones are stored on the Project object (not as sheet rows), so they serve
as external markers — release dates, review gates, demos — independent of the
task list.

---

## Cross-project links

Projects can declare dependencies on tasks in other projects via
`CrossProjectLink(from_project, from_id, to_project, to_id)`. These appear as
dashed arrows in the Roadmap view and are factored into `slip_impact` analysis.

---

## Programmatic access

The PM engine is pure stdlib (`abax/core/pm/`), so you can use it from the
Python console or a script without importing Qt:

```python
from abax.core.pm.taskmodel import parse_tasks, detect_columns
from abax.core.pm.schedule import auto_schedule, compute_cpm
from abax.core.pm.finance import budget_rollup, evm
from abax.core.pm.capacity import workload_by_week
from abax.core.pm.portfolio import portfolio_kpis, slip_impact
from abax.core.pm.exporter import export_gantt_svg
from abax.core.pm.importer import import_csv, import_mpp_xml
from abax.core.pm.report import report_html, report_markdown
```

### Parse tasks from a sheet

```python
tasks = parse_tasks(sheet, header_row=0, first_col=0, last_col=6)
```

### Schedule and find the critical path

```python
from abax.core.pm.schedule import compute_cpm, critical_path

result = compute_cpm(tasks)
crit = critical_path(tasks)
# result[task_id].early_start, .late_finish, .slack_days, .critical
```

### Generate a report

```python
from datetime import date
from abax.core.pm.report import report_markdown

md = report_markdown([(project, tasks)], date.today(), title="Sprint 12")
with open("report.md", "w") as f:
    f.write(md)
```

### Import from CSV

```python
from abax.core.pm.importer import import_csv

tasks = import_csv("jira-export.csv")
# tasks is a list of Task objects, ready for schedule() or export
```

Key modules: `taskmodel` (Task dataclass, header detection, parse/write),
`projects` (project registry), `schedule` (CPM), `portfolio` (cross-project
analytics), `capacity` (resource planning), `finance` (budget roll-up, EVM,
scenarios), `importer` (CSV / MS Project XML), `exporter` (Gantt/timeline SVG,
PDF, reports), `pmsvg` (low-level SVG renderers).

---

## See also

- [GUI guide](gui-guide.md) — Project menu reference.
- [CLI reference](cli.md) — `report` subcommand (HTML and Markdown output).
- [Examples: task tracking](examples/project-management/task-tracking/README.md)
  — walkthrough of the entire PM workflow.
- [Architecture](architecture.md) — `core/pm/` module map.
