from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Employee, PayrollRun
from app.services.payroll_engine import compliance_summary_from_runs
import calendar

router = APIRouter()


@router.get("/summary")
def compliance_summary(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    db: Session = Depends(get_db),
):
    """Statutory remittance summary: PF + ESI + TDS due amounts."""
    runs = db.query(PayrollRun).filter(
        PayrollRun.month == month, PayrollRun.year == year
    ).all()
    if not runs:
        raise HTTPException(status_code=404, detail="No payroll runs found for this period")

    summary = compliance_summary_from_runs(runs)
    summary["month"] = month
    summary["year"] = year
    summary["period"] = f"{calendar.month_name[month]} {year}"
    return summary


@router.get("/pf-report")
def pf_report(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    db: Session = Depends(get_db),
):
    """
    ECR (Electronic Challan cum Return) format data for PF filing.
    Returns per-employee PF contribution details.
    """
    runs = db.query(PayrollRun).filter(
        PayrollRun.month == month, PayrollRun.year == year
    ).all()
    if not runs:
        raise HTTPException(status_code=404, detail="No payroll data for this period")

    records = []
    total_emp_pf = total_er_pf = 0.0

    for run in runs:
        emp = db.query(Employee).filter(Employee.id == run.employee_id).first()
        pf_base = min(run.basic, 15_000)
        eps = min(round(pf_base * 0.0833), 1_250)
        epf = run.employer_pf - eps   # EPF = employer PF minus EPS share

        records.append({
            "employee_code": emp.employee_code if emp else "",
            "name": emp.name if emp else "Unknown",
            "uan": emp.uan_number if emp else "",
            "pf_wages": pf_base,
            "employee_pf": run.employee_pf,
            "employer_epf": epf,
            "eps": eps,
            "total_pf": run.employee_pf + run.employer_pf,
        })
        total_emp_pf += run.employee_pf
        total_er_pf += run.employer_pf

    return {
        "period": f"{calendar.month_name[month]} {year}",
        "due_date": f"15th {calendar.month_name[month % 12 + 1]} {year if month < 12 else year + 1}",
        "total_employee_pf": round(total_emp_pf, 2),
        "total_employer_pf": round(total_er_pf, 2),
        "total_remittance": round(total_emp_pf + total_er_pf, 2),
        "records": records,
    }


@router.get("/esi-report")
def esi_report(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    db: Session = Depends(get_db),
):
    """ESI contribution report for eligible employees (gross ≤ ₹21,000)."""
    runs = db.query(PayrollRun).filter(
        PayrollRun.month == month,
        PayrollRun.year == year,
        PayrollRun.esi_applicable == True,
    ).all()

    if not runs:
        return {"period": f"{calendar.month_name[month]} {year}", "message": "No ESI eligible employees", "records": []}

    records = []
    total_emp_esi = total_er_esi = 0.0

    for run in runs:
        emp = db.query(Employee).filter(Employee.id == run.employee_id).first()
        records.append({
            "employee_code": emp.employee_code if emp else "",
            "name": emp.name if emp else "Unknown",
            "esic_number": emp.esic_number if emp else "",
            "gross_wages": run.gross_salary,
            "employee_esi": run.employee_esi,
            "employer_esi": run.employer_esi,
            "total_esi": run.employee_esi + run.employer_esi,
        })
        total_emp_esi += run.employee_esi
        total_er_esi += run.employer_esi

    return {
        "period": f"{calendar.month_name[month]} {year}",
        "due_date": f"15th {calendar.month_name[month % 12 + 1]} {year if month < 12 else year + 1}",
        "eligible_employees": len(records),
        "total_employee_esi": round(total_emp_esi, 2),
        "total_employer_esi": round(total_er_esi, 2),
        "total_remittance": round(total_emp_esi + total_er_esi, 2),
        "records": records,
    }


@router.get("/tds-report")
def tds_report(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    db: Session = Depends(get_db),
):
    """TDS (Section 192) deduction report for Form 24Q preparation."""
    runs = db.query(PayrollRun).filter(
        PayrollRun.month == month, PayrollRun.year == year
    ).all()
    if not runs:
        raise HTTPException(status_code=404, detail="No payroll data for this period")

    records = []
    total_tds = 0.0

    for run in runs:
        emp = db.query(Employee).filter(Employee.id == run.employee_id).first()
        records.append({
            "employee_code": emp.employee_code if emp else "",
            "name": emp.name if emp else "Unknown",
            "pan": emp.pan_number if emp else "",
            "tax_regime": emp.tax_regime if emp else "",
            "gross_salary": run.gross_salary,
            "tds_deducted": run.tds,
        })
        total_tds += run.tds

    return {
        "period": f"{calendar.month_name[month]} {year}",
        "due_date": f"7th {calendar.month_name[month % 12 + 1]} {year if month < 12 else year + 1}",
        "total_tds": round(total_tds, 2),
        "form": "24Q",
        "section": "192 — Salary",
        "records": records,
    }


@router.get("/filing-calendar")
def filing_calendar():
    """Returns all statutory filing deadlines."""
    return {
        "pf_esi": {
            "description": "PF & ESI monthly remittance",
            "due": "15th of the following month",
            "authority": "EPFO / ESIC",
        },
        "tds_deposit": {
            "description": "TDS deposit to government",
            "due": "7th of the following month",
            "authority": "Income Tax Department",
            "form": "ITNS 281",
        },
        "tds_return_quarterly": [
            {"quarter": "Q1 (Apr–Jun)", "due": "31st July"},
            {"quarter": "Q2 (Jul–Sep)", "due": "31st October"},
            {"quarter": "Q3 (Oct–Dec)", "due": "31st January"},
            {"quarter": "Q4 (Jan–Mar)", "due": "31st May"},
        ],
        "form_16": {
            "description": "TDS certificate issued to employees",
            "due": "15th June each year",
            "form": "Form 16 (Part A + Part B)",
        },
        "professional_tax": {
            "description": "Professional tax remittance (state-specific)",
            "due": "Varies by state — typically monthly or annual",
        },
    }
