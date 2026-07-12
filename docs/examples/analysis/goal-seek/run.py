"""Goal Seek: find the input that makes a formula hit a target.

A car-loan sheet computes the monthly payment with PMT. Goal Seek then
answers the real question — "how much car can I afford at $400/month?"
"""

from abax.core.goalseek import goal_seek
from abax.core.workbook import Workbook

wb = Workbook()
sheet = wb.sheet

sheet.set_cell(0, 0, "Loan amount")
sheet.set_cell(0, 1, "25000")
sheet.set_cell(1, 0, "Annual rate")
sheet.set_cell(1, 1, "0.07")
sheet.set_cell(2, 0, "Years")
sheet.set_cell(2, 1, "5")
sheet.set_cell(3, 0, "Monthly payment")
sheet.set_cell(3, 1, "=-PMT(B2/12, B3*12, B1)")

print(f"Borrowing 25000 costs {sheet.get('B4'):.2f}/month")

# Change B1 (the loan) until B4 (the payment) equals 400.
solution = goal_seek(sheet, "B4", 400.0, "B1", lo=1000, hi=100000)

print(f"For a 400.00/month budget you can borrow {solution:.2f}")
print(f"Check: the sheet now shows payment = {sheet.get('B4'):.2f}")
