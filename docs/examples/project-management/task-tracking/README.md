# Project management: task tracking

Track a project on an ordinary sheet: build a task list, run critical-path
scheduling, and export a status report — then explore the ten PM views in
the GUI (Kanban, Card, Calendar, Gantt, Timeline, Dashboard, Roadmap,
Resources, Budget, OKRs) plus import/export and scenario analysis.

**You'll need:** nothing beyond abax for `run.py` (pure stdlib); a Qt
binding (`pip install "abax[all]"`) for the GUI walkthrough below it.

## Run it

    cd docs/examples/project-management/task-tracking
    python run.py

## What you should see

    5 tasks scheduled; critical path:
      T1 (Design) -> T2 (Build core) -> T4 (Integrate) -> T5 (Ship)

    slack per task (days):
      T1  slack=0  <- critical
      T2  slack=0  <- critical
      T3  slack=2
      T4  slack=0  <- critical
      T5  slack=0  <- critical

    wrote out/status.md, out/gantt.svg, out/sprint.abax
    open the workbook in the GUI (Project menu lights up):
      abax out/sprint.abax

## How it works

- The task sheet is typed exactly the way you would in the grid; headers are
  matched by **alias** (Due/End/Finish all work, Assignee/Owner/Who all work).
- `Project(...)` + `wb.projects.add(...)` registers the sheet region — the
  same thing **Project > New project from sheet…** does in the GUI.
- `parse_tasks` reads the region back as Task objects; `compute_cpm` runs the
  forward/backward critical-path pass and `critical_path` extracts the
  zero-slack chain (T3, the parallel UI track, has 2 days of slack).
- `report_markdown` renders the roll-up (progress, health, overdue,
  milestones) and `export_gantt_svg` draws the chart — both plain files you
  can commit, mail, or publish.
- The saved `out/sprint.abax` carries the project registration, so opening it
  in the GUI lights up the Project menu with everything below already wired.

The rest of this page is a **GUI walkthrough** of the same features.

## Set up a task sheet

1. Open abax (`abax gui`) and create a sheet with these headers in row 1:

       Title | Status | Start | Due | Assignee | Effort | Cost

2. Add a few tasks in the rows below:

       Design UI      | To Do       | 2026-08-01 | 2026-08-15 | Alice | 40 | 5000
       Build backend  | In Progress | 2026-08-05 | 2026-09-01 | Bob   | 80 | 8000
       Write tests    | To Do       | 2026-09-01 | 2026-09-15 | Alice | 20 | 2000
       Deploy         | To Do       | 2026-09-15 | 2026-09-20 | Bob   | 10 | 1000

## Register a project

3. **Project > New project from sheet...** (or type "Project: new" in the
   command palette with `Ctrl+Shift+P`).
4. Name the project, confirm the auto-detected columns, and click OK.

## Explore the views

5. **Project > Open project views** opens the dockable PM panel with ten tabs:
   - **Kanban** — drag cards between status columns.
   - **Card** — responsive grid with sort/filter.
   - **Calendar** — month grid with drag-to-reschedule.
   - **Gantt** — draggable bars, dependency arrows, critical-path highlight.
   - **Timeline** — swim lanes by assignee.
   - **Dashboard** — KPI tiles, health table, milestones.
   - **Roadmap** — multi-project timeline with cross-project links.
   - **Resources** — people x weeks workload heatmap.
   - **Budget** — budget-vs-actual bars, EVM KPI tiles.
   - **OKRs** — objectives and key results.

## Import tasks from CSV or MS Project

6. **Project > Import tasks...** — open a CSV file (auto-detects delimiter
   and header names) or an MS Project XML export. The parsed tasks are
   appended to the active project's sheet (matched to your columns by header
   name) as a single undo step.

## Export a Gantt chart

7. **Project > Export Gantt SVG...** — saves the Gantt chart as an SVG file
   with a colour-key legend.

## What-if scenarios

8. **Project > Scenarios...** — the scenario editor lets you override task
   fields (dates, effort, cost, assignee, status) without touching the sheet.
   Click **Apply to Sheet** to commit the overrides as a single undo step.

## Export a status report

9. **Project > Export report...** — generates a status report with per-project
   tables, task summaries, and milestones. The file dialog offers both HTML and
   Markdown formats — save with a `.md` extension for Markdown output.

   From the CLI:

       abax report myproject.abax -o status.html   # HTML
       abax report myproject.abax -o status.md      # Markdown

## Next steps

- [GUI guide](../../../gui-guide.md) — full menu-bar reference.
- [CLI reference](../../../cli.md) — all subcommands including `report`.
- [Examples catalog](../../README.md) — more tested examples.
