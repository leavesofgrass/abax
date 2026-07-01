# Jupyter integration

qcell works with the Jupyter / IPython ecosystem four ways — notebook I/O, rich
display, a kernel, and an editable widget. The pieces that need extra packages
(`nbformat`, `ipykernel`, `anywidget`) are optional; install them at once with:

```sh
pip install qcell[jupyter]
```

(qcell also auto-installs these in the background on first launch — see
[Configuration](configuration.md).)

## Notebook I/O (`.ipynb`) — lossless round-trip

Convert to and from Jupyter notebooks by extension:

```sh
python -m qcell convert budget.qcell budget.ipynb    # workbook → notebook
python -m qcell convert budget.ipynb budget.qcell    # notebook → workbook
```

- Export is valid **nbformat 4.5** (every cell carries an `id`), so JupyterLab,
  `nbclient`, and `nbconvert` accept it.
- The **entire workbook** (formulas, multiple sheets, defined names, styles) is
  embedded in the notebook metadata and restored on import — a `.ipynb` written by
  qcell round-trips **losslessly** back to a `.qcell`.
- Each sheet also renders as a Markdown table cell, so the notebook is readable in
  any viewer. A **foreign** notebook (not written by qcell) is imported by scanning
  its Markdown tables.
- `qcell.engine.nbvalidate.validate_notebook(nb)` checks a notebook against the
  real nbformat schema when it's installed, or stdlib structural checks otherwise.

## Rich display in Jupyter / IPython

A `Sheet` implements the IPython display protocol, so it renders as a grid:

```python
from qcell.engine.document import Document
doc = Document.open("budget.qcell")
doc.workbook.sheet          # → an HTML table in Jupyter, a Markdown table in a text console
```

The same protocol drives the qcell Python console: typing an expression whose
result has a rich representation prints it readably (`core/richdisplay.py`).

## qcell as a Jupyter kernel

Run notebook cells in the qcell namespace (with the live workbook helpers `doc`,
`wb`, `sheet`, `cell`, `put`, and the science modules):

```sh
pip install qcell[jupyter]
python -m qcell.kernel --help          # launched by Jupyter via the kernelspec
```

Register the kernel so it appears in Jupyter's kernel picker:

```python
from qcell.kernel import install_kernelspec
install_kernelspec()                   # writes the "qcell" kernelspec
```

The kernel returns results in Jupyter execute-result shape (a rich mime-bundle),
so a `Sheet` shows as an HTML table in JupyterLab. It is a **pure-Python kernel**
(it doesn't embed IPython); the default lightweight out-of-process console remains
qcell's own default — the kernel is the opt-in path for running qcell *inside*
Jupyter.

## Editable sheet widget (anywidget)

Embed an editable qcell grid in a notebook:

```python
from qcell.engine.document import Document
from qcell.widget import sheet_widget
doc = Document.open("budget.qcell")
sheet_widget(doc.workbook.sheet)       # an interactive HTML grid; edits recompute formulas
```

Cell edits round-trip back into the live sheet and recompute through qcell's
formula engine. Requires `anywidget`.
