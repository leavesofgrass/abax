"""Track a small project headlessly: tasks -> CPM schedule -> report.

Builds a five-task sprint on a sheet, registers it as an abax project, runs
critical-path scheduling, and writes a Markdown status report + a Gantt SVG
to out/. Everything here is the pure-stdlib core — no optional packages.
"""

from datetime import date
from pathlib import Path

from abax.core.pm.exporter import export_gantt_svg
from abax.core.pm.projects import Milestone, Project
from abax.core.pm.report import report_markdown
from abax.core.pm.schedule import compute_cpm, critical_path
from abax.core.pm.taskmodel import parse_tasks
from abax.core.workbook import Workbook

wb = Workbook()
sheet = wb.sheet
sheet.name = "Sprint"

# A task sheet the way you would type it — headers are matched by alias
# (Due/End/Finish all work; Assignee/Owner/Who all work).
rows = [
    ("ID", "Title",       "Status",      "Start",      "Due",        "Assignee", "Effort", "% Done", "Depends"),
    ("T1", "Design",      "Done",        "2026-07-01", "2026-07-03", "Ann",      "16",     "100",    ""),
    ("T2", "Build core",  "In Progress", "2026-07-04", "2026-07-10", "Bob",      "40",     "60",     "T1"),
    ("T3", "Build UI",    "In Progress", "2026-07-04", "2026-07-08", "Ann",      "24",     "40",     "T1"),
    ("T4", "Integrate",   "To Do",       "2026-07-11", "2026-07-14", "Bob",      "16",     "0",      "T2,T3"),
    ("T5", "Ship",        "To Do",       "2026-07-15", "2026-07-15", "Ann",      "4",      "0",      "T4"),
]
for r, row in enumerate(rows):
    for c, value in enumerate(row):
        sheet.set_cell(r, c, str(value))

# Register the sheet region as a project (this is what the GUI's
# "Project > New project from sheet..." dialog does).
project = Project(
    name="Sprint 12", sheet=sheet.name,
    header_row=0, first_col=0, last_col=len(rows[0]) - 1,
    first_data_row=1, last_data_row=len(rows) - 1,
    milestones=[Milestone(name="Ship", date="2026-07-15", done=False)],
)
wb.projects.add(project)

# Parse the tasks back off the sheet and run the CPM scheduler.
tasks = parse_tasks(sheet, header_row=0, first_col=0, last_col=8,
                    first_data_row=1, last_data_row=len(rows) - 1)
cpm = compute_cpm(tasks)
crit = critical_path(cpm)

print(f"{len(tasks)} tasks scheduled; critical path:")
by_id = {t.id: t for t in tasks}
print("  " + " -> ".join(f"{tid} ({by_id[tid].title})" for tid in crit))
print()
print("slack per task (days):")
for tid, res in sorted(cpm.items()):
    mark = "  <- critical" if res.critical else ""
    print(f"  {tid}  slack={res.slack_days:g}{mark}")

# Write the deliverables: a Markdown status report and a Gantt chart.
out = Path("out")
out.mkdir(exist_ok=True)
today = date(2026, 7, 9)  # pinned so the report is reproducible

md = report_markdown([(project, tasks)], today)
(out / "status.md").write_text(md, encoding="utf-8")
export_gantt_svg(tasks, out / "gantt.svg", today=today, title=project.name)
wb.save_json(out / "sprint.abax")

print()
print("wrote out/status.md, out/gantt.svg, out/sprint.abax")
print("open the workbook in the GUI (Project menu lights up):")
print("  abax out/sprint.abax")
