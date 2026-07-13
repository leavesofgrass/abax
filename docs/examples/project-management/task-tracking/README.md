# Project management: task tracking

Set up a task sheet, register it as a project, and explore the ten PM views
(Kanban, Card, Calendar, Gantt, Timeline, Dashboard, Roadmap, Resources,
Budget, OKRs) plus import/export and scenario analysis.

**You'll need:** abax with a Qt binding (`pip install "abax[all]"`).

This is a **walkthrough** (nothing to run here).

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
   and header names) or an MS Project XML export. The dialog parses the file
   and reports how many tasks it found; writing them into the sheet is not
   yet wired up (use the `import_csv` / `tasks_to_csv` Python API to
   round-trip task lists).

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
