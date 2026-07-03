# Jupyter integration

abax works with the Jupyter / IPython ecosystem four ways — notebook I/O, rich
display, a kernel, and an editable widget. The pieces that need extra packages
(`nbformat`, `ipykernel`, `anywidget`) are optional; install them at once with:

```sh
pip install abax[jupyter]
```

(pick *Jupyter integration* in the first-run chooser — or **Tools → Install optional
features** — to fetch these; see [Configuration](configuration.md).)

## Notebook I/O (`.ipynb`) — lossless round-trip

Convert to and from Jupyter notebooks by extension:

```sh
python -m abax convert budget.abax budget.ipynb    # workbook → notebook
python -m abax convert budget.ipynb budget.abax    # notebook → workbook
```

- Export is valid **nbformat 4.5** (every cell carries an `id`), so JupyterLab,
  `nbclient`, and `nbconvert` accept it.
- The **entire workbook** (formulas, multiple sheets, defined names, styles) is
  embedded in the notebook metadata and restored on import — a `.ipynb` written by
  abax round-trips **losslessly** back to a `.abax`.
- Each sheet also renders as a Markdown table cell, so the notebook is readable in
  any viewer. A **foreign** notebook (not written by abax) is imported by scanning
  its Markdown tables.
- `abax.engine.nbvalidate.validate_notebook(nb)` checks a notebook against the
  real nbformat schema when it's installed, or stdlib structural checks otherwise.

## Rich display in Jupyter / IPython

A `Sheet` implements the IPython display protocol, so it renders as a grid:

```python
from abax.engine.document import Document
doc = Document.open("budget.abax")
doc.workbook.sheet          # → an HTML table in Jupyter, a Markdown table in a text console
```

The same protocol drives the abax Python console: typing an expression whose
result has a rich representation prints it readably (`core/richdisplay.py`).

## abax as a Jupyter kernel

Run notebook cells in the abax namespace (with the live workbook helpers `doc`,
`wb`, `sheet`, `cell`, `put`, and the science modules):

```sh
pip install abax[jupyter]
python -m abax.kernel --help          # launched by Jupyter via the kernelspec
```

Register the kernel so it appears in Jupyter's kernel picker:

```python
from abax.kernel import install_kernelspec
install_kernelspec()                   # writes the "abax" kernelspec
```

The kernel returns results in Jupyter execute-result shape (a rich mime-bundle),
so a `Sheet` shows as an HTML table in JupyterLab. It is a **pure-Python kernel**
(it doesn't embed IPython); the default lightweight out-of-process console remains
abax's own default — the kernel is the opt-in path for running abax *inside*
Jupyter.

## Editable sheet widget (anywidget)

Embed an editable abax grid in a notebook:

```python
from abax.engine.document import Document
from abax.widget import sheet_widget
doc = Document.open("budget.abax")
sheet_widget(doc.workbook.sheet)       # an interactive HTML grid; edits recompute formulas
```

Cell edits round-trip back into the live sheet and recompute through abax's
formula engine. Requires `anywidget`.
