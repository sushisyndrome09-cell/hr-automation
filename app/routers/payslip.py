from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Employee, PayrollRun
import calendar

router = APIRouter()

MONTH_NAMES = {i: calendar.month_name[i] for i in range(1, 13)}


@router.get("/{employee_id}")
def get_payslip(
    employee_id: int,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    db: Session = Depends(get_db),
):
    """
    Returns a structured payslip for an employee for a given month/year.
    Run payroll first (/api/payroll/run) before fetching payslips.
    """
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    run = (
        db.query(PayrollRun)
        .filter(
            PayrollRun.employee_id == employee_id,
            PayrollRun.month == month,
            PayrollRun.year == year,
        )
        .first()
    )
    if not run:
        raise HTTPException(
            status_code=404,
            detail=f"Payroll not processed for {MONTH_NAMES[month]} {year}. Run payroll first.",
        )

    return {
        "payslip": {
            "period": f"{MONTH_NAMES[month]} {year}",
            "month": month,
            "year": year,
        },
        "employee": {
            "id": emp.id,
            "employee_code": emp.employee_code,
            "name": emp.name,
            "email": emp.email,
            "designation": emp.designation,
            "department": emp.department,
            "pan_number": emp.pan_number,
            "uan_number": emp.uan_number,
            "bank_account": f"XXXX{emp.bank_account[-4:]}" if emp.bank_account and len(emp.bank_account) >= 4 else emp.bank_account,
            "bank_name": emp.bank_name,
            "date_of_joining": emp.date_of_joining,
            "tax_regime": emp.tax_regime,
        },
        "earnings": {
            "basic": run.basic,
            "hra": run.hra,
            "special_allowance": run.special_allowance,
            "lta": run.lta,
            "medical_allowance": run.medical_allowance,
            "other_allowances": run.other_allowances,
            "gross_salary": run.gross_salary,
        },
        "deductions": {
            "employee_pf": run.employee_pf,
            "employee_esi": run.employee_esi,
            "tds": run.tds,
            "professional_tax": run.professional_tax,
            "total_deductions": run.total_deductions,
        },
        "employer_contributions": {
            "employer_pf": run.employer_pf,
            "employer_esi": run.employer_esi,
            "note": "Employer contributions are not deducted from employee salary",
        },
        "net_pay": run.net_pay,
        "esi_applicable": run.esi_applicable,
        "in_words": _amount_in_words(run.net_pay),
    }


@router.get("/bulk/{month}/{year}")
def get_all_payslips(
    month: int,
    year: int,
    db: Session = Depends(get_db),
):
    """Return payslips for all employees for a given period."""
    runs = (
        db.query(PayrollRun)
        .filter(PayrollRun.month == month, PayrollRun.year == year)
        .all()
    )
    if not runs:
        raise HTTPException(status_code=404, detail="No payroll data for this period")

    result = []
    for run in runs:
        emp = db.query(Employee).filter(Employee.id == run.employee_id).first()
        result.append({
            "employee_code": emp.employee_code if emp else "N/A",
            "name": emp.name if emp else "Unknown",
            "designation": emp.designation if emp else "",
            "gross_salary": run.gross_salary,
            "total_deductions": run.total_deductions,
            "net_pay": run.net_pay,
            "bank_account": emp.bank_account if emp else "",
            "bank_name": emp.bank_name if emp else "",
        })
    return {
        "period": f"{MONTH_NAMES[month]} {year}",
        "total_employees": len(result),
        "payslips": result,
    }


# ── Utility ───────────────────────────────────────────────────────────────────

def _amount_in_words(amount: float) -> str:
    """Convert a rupee amount to words (simplified)."""
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def _to_words(n: int) -> str:
        if n == 0:
            return "Zero"
        if n < 20:
            return ones[n]
        if n < 100:
            return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")
        if n < 1000:
            return ones[n // 100] + " Hundred" + (" and " + _to_words(n % 100) if n % 100 else "")
        if n < 100_000:
            return _to_words(n // 1000) + " Thousand" + (" " + _to_words(n % 1000) if n % 1000 else "")
        if n < 10_000_000:
            return _to_words(n // 100_000) + " Lakh" + (" " + _to_words(n % 100_000) if n % 100_000 else "")
        return _to_words(n // 10_000_000) + " Crore" + (" " + _to_words(n % 10_000_000) if n % 10_000_000 else "")

    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    words = "Rupees " + _to_words(rupees)
    if paise:
        words += f" and {paise} Paise"
    return words + " Only"
