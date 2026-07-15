# Frozen-bundle smoke gate for the Windows binary (run after a PyInstaller build).
#
# The 0.1.8 lesson, twice over: a frozen bundle is an ADVERSARIAL test
# environment -- CLI checks alone prove nothing about lazily-imported or
# data-dependent paths (QSS themes, dynamic formula packs, matplotlib). Every
# step here runs INSIDE the bundle's own interpreter and fails loudly, naming
# what is missing:
#
#   1. the three bundle exes exist (abax.exe / abaxw.exe / abax-worker.exe)
#   2. `abax --version` answers
#   3. `abax get` opens a real file and evaluates a cell (Document/data path)
#   4. an embedded chart renders through BOTH backends -- the stdlib SVG
#      renderer and matplotlib PNG -- via a command macro executed by the
#      frozen interpreter (`abax --macros ... macro run ...`)
#   5. an offscreen `abax gui` launch stays alive (event loop up = pass;
#      an early exit = the 0.1.8 theme flash-crash class of bug)
#
# Usage:  .\packaging\windows\smoke.ps1 [-BundleDir dist\windows\abax]
# Works under Windows PowerShell 5.1 and pwsh 7 (CI uses pwsh).

param(
    [string]$BundleDir = "dist\windows\abax",
    # Seconds the offscreen GUI must survive to count as "event loop alive".
    [int]$GuiGraceSeconds = 15
)

$ErrorActionPreference = "Stop"

function Fail([string]$msg) {
    throw "SMOKE FAIL: $msg"
}

$failed = $false
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("abax-smoke-" + [System.IO.Path]::GetRandomFileName())

try {
    # -- 1: bundle layout ------------------------------------------------------
    $abax = Join-Path $BundleDir "abax.exe"
    if (-not (Test-Path $abax)) {
        Fail "abax.exe not found at '$abax' (build the bundle first: py -m PyInstaller packaging/windows/abax.spec --noconfirm --distpath dist/windows)"
    }
    # Absolute path: Start-Process resolves relative -FilePath inconsistently
    # across PowerShell versions.
    $abax = (Resolve-Path $abax).Path
    foreach ($sibling in @("abaxw.exe", "abax-worker.exe")) {
        if (-not (Test-Path (Join-Path $BundleDir $sibling))) {
            Fail "$sibling is missing from the bundle -- the spec's extra exe targets were not built"
        }
    }
    Write-Host "OK  bundle layout: abax.exe / abaxw.exe / abax-worker.exe present"

    New-Item -ItemType Directory -Path $tmp | Out-Null

    # -- 2: CLI answers --------------------------------------------------------
    $ver = & $abax --version
    if ($LASTEXITCODE -ne 0 -or "$ver" -notmatch "^abax ") {
        Fail "abax --version failed (exit $LASTEXITCODE): $ver"
    }
    Write-Host "OK  --version: $ver"

    # -- 3: data path (Document.open + evaluation through `get`) ---------------
    $csv = Join-Path $tmp "canary.csv"
    Set-Content -Path $csv -Value "1,2`n3,4" -Encoding ascii
    $val = & $abax get $csv B2
    if ($LASTEXITCODE -ne 0 -or "$val".Trim() -ne "4") {
        Fail "abax get canary failed (exit $LASTEXITCODE): got '$val', wanted 4"
    }
    Write-Host "OK  get canary: B2 = $($("$val").Trim())"

    # -- 4: embedded chart renders inside the frozen interpreter ---------------
    # A command macro is the sanctioned way to execute abax code through the
    # CLI, so the render runs in the bundle's interpreter against its bundled
    # modules -- exactly what a user's embedded chart will do. The macro builds
    # a tiny in-memory workbook, adds a ChartObject, and asserts both chart
    # backends: the pure-stdlib SVG renderer (must return <svg) and the
    # matplotlib backend (must return PNG bytes). The Windows bundle always
    # ships matplotlib (see abax.spec / README), so HAS_MATPLOTLIB=False in
    # the frozen build means the charts backend silently vanished -- the macro
    # fails the gate rather than skipping.
    $macroFile = Join-Path $tmp "chart_smoke.py"
    @'
# Written by packaging/windows/smoke.ps1; run inside the frozen bundle via
#   abax.exe --macros <this file> macro run chart_smoke <workbook>
@macro
def chart_smoke(ctx):
    from abax.core.chartobj import ChartObject, render_chart
    from abax.core.workbook import Workbook
    from abax.macros import MacroError

    wb = Workbook()
    for i, v in enumerate((3, 1, 4, 1, 5, 9, 2, 6)):
        wb.sheet.set_cell(i, 0, str(v))
    ch = ChartObject(id="chart1", kind="line", source="A1:A8", title="smoke")

    svg = render_chart(wb, wb.sheet.name, ch)
    if not svg.lstrip().startswith("<svg"):
        raise MacroError(
            "chart smoke: render_chart returned no <svg -- the stdlib chart "
            "renderer (abax.core.science.chartsvg) is broken or missing "
            "from the bundle")
    ctx.log("CHART-SVG-OK %d chars" % len(svg))

    from abax.engine import chartmpl
    if not chartmpl.HAS_MATPLOTLIB:
        raise MacroError(
            "chart smoke: abax.engine.chartmpl.HAS_MATPLOTLIB is False -- "
            "matplotlib was dropped from the frozen bundle, so every "
            "matplotlib-backend chart would silently degrade")
    png = chartmpl.render_chart_mpl(wb, wb.sheet.name, ch)
    if not (isinstance(png, bytes) and png.startswith(b"\x89PNG")):
        raise MacroError(
            "chart smoke: render_chart_mpl did not return PNG bytes -- the "
            "matplotlib Agg backend is broken in the frozen bundle")
    ctx.log("CHART-MPL-OK %d bytes" % len(png))
'@ | Set-Content -Path $macroFile -Encoding ascii
    # stdout is captured for the marker checks; stderr (the macro's failure
    # message, if any) streams through to the build log.
    $chartLog = & $abax --macros $macroFile macro run chart_smoke $csv -o (Join-Path $tmp "out.csv")
    $chartText = ($chartLog | Out-String)
    if ($LASTEXITCODE -ne 0) {
        Fail "chart-render macro failed (exit $LASTEXITCODE) -- see the message above.`n$chartText"
    }
    if ($chartText -notmatch "CHART-SVG-OK") {
        Fail "chart-render macro ran but the SVG marker is missing:`n$chartText"
    }
    if ($chartText -notmatch "CHART-MPL-OK") {
        Fail "chart-render macro ran but the matplotlib PNG marker is missing:`n$chartText"
    }
    Write-Host "OK  embedded chart: stdlib SVG + matplotlib PNG both render in the bundle"

    # -- 5: offscreen GUI launch ------------------------------------------------
    # Event loop still alive after the grace period = pass. An early exit is
    # the startup-crash class the 0.1.8 shakedown hit (unbundled QSS themes):
    # invisible to every CLI check, fatal to the first real user.
    $env:QT_QPA_PLATFORM = "offscreen"
    $gui = Start-Process -FilePath $abax -ArgumentList "gui" -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds $GuiGraceSeconds
    if ($gui.HasExited) {
        Fail "offscreen 'abax gui' exited within $GuiGraceSeconds s (exit $($gui.ExitCode)) -- GUI startup crash in the frozen bundle"
    }
    Stop-Process -Id $gui.Id -Force
    Write-Host "OK  offscreen GUI: event loop alive after $GuiGraceSeconds s"

    Write-Host "SMOKE PASS: frozen bundle at '$BundleDir' survived all checks"
}
catch {
    Write-Host "$_" -ForegroundColor Red
    $failed = $true
}
finally {
    if (Test-Path $tmp) {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}

if ($failed) { exit 1 }
exit 0
