"""Drive the abax CLI without a screen: view, get, convert, profile.

This script calls the CLI in-process (abax.app.main). In a shell you'd
type the `abax ...` lines shown in the README — same arguments, same
output.
"""

from pathlib import Path

from abax.app import main

out = Path("out")
out.mkdir(exist_ok=True)

# A tiny sales sheet — formulas travel fine inside a CSV.
(out / "sales.csv").write_text(
    "Product,Units,Price,Revenue\n"
    "Widget,10,2.50,=B2*C2\n"
    "Gadget,4,11.00,=B3*C3\n"
    "Doodad,25,0.80,=B4*C4\n"
    "TOTAL,,,=SUM(D2:D4)\n",
    encoding="utf-8",
)

print("$ abax view out/sales.csv")
main(["view", str(out / "sales.csv")])

print("\n$ abax get out/sales.csv D5")
main(["get", str(out / "sales.csv"), "D5"])

print("\n$ abax convert out/sales.csv out/sales.md")
main(["convert", str(out / "sales.csv"), str(out / "sales.md")])
print((out / "sales.md").read_text(encoding="utf-8"))

print("$ abax profile out/sales.csv --limit 3")
main(["profile", str(out / "sales.csv"), "--limit", "3"])
