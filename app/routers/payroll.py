from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.models import Employee, PayrollRun, EmploymentStatus
from app.schemas import (
    PayrollRunRequest, PayrollRunOut, PayrollSummary,
    SalaryCalcRequest, SalaryCalcOut,
)
from app.services.payroll_engine import calculate_payroll

router = APIRouter()


# ── Run payroll for a month ───────────────────────────────────────────────────

@router.post("/run", response_model=PayrollSummary)
def run_payroll(payload: PayrollRunRequest, db: Session = Depends(get_db)):
    """
    Process payroll for all active employees (or a subset via employee_ids).
    If a payroll run already exists for the month/year/employee, it is
    overwritten (re-run scenario).
    """
    query = db.query(Employee).filter(Employee.status == EmploymentStatus.active)
    if payload.employee_ids:
        query = query.filter(Employee.id.in_(payload.employee_ids))
    employees = query.all()

    if not employees:
        raise HTTPException(status_code=404, detail="No active employees found")

    runs_out: list[PayrollRunOut] = []
    total_gross = total_emp_deductions = total_net = 0.0
    total_er_pf = total_er_esi = total_tds = 0.0

    for emp in employees:
        result = calculate_payroll(
            basic=emp.basic,
            hra=emp.hra,
            special_allowance=emp.special_allowance,
            lta=emp.lta,
            medical_allowance=emp.medical_allowance,
            other_allowances=emp.other_allowances,
            tax_regime=emp.tax_regime,
        )

        # Upsert payroll run
        existing = (
            db.query(PayrollRun)
            .filter(
                PayrollRun.employee_id == emp.id,
                PayrollRun.month == payload.month,
                PayrollRun.year == payload.year,
            )
            .first()
        )
        run = existing or PayrollRun(employee_id=emp.id, month=payload.month, year=payload.year)

        run.gross_salary = result.gross_salary
        run.basic = result.basic
        run.hra = result.hra
        run.special_allowance = result.special_allowance
        run.lta = result.lta
        run.medical_allowance = result.medical_allowance
        run.other_allowances = result.other_allowances
        run.employee_pf = result.employee_pf
        run.employer_pf = result.employer_pf
        run.employee_esi = result.employee_esi
        run.employer_esi = result.employer_esi
        run.tds = result.tds_monthly
        run.professional_tax = result.professional_tax
        run.total_deductions = result.total_deductions
        run.net_pay = result.net_pay
        run.esi_applicable = result.esi_applicable
        run.is_processed = True

        if not existing:
            db.add(run)
        db.flush()

        total_gross += result.gross_salary
        total_emp_deductions += result.total_deductions
        total_net += result.net_pay
        total_er_pf += result.employer_pf
        total_er_esi += result.employer_esi
        total_tds += result.tds_monthly

        runs_out.append(PayrollRunOut(
            id=run.id,
            employee_id=emp.id,
            employee_name=emp.name,
            month=payload.month,
            year=payload.year,
            gross_salary=run.gross_salary,
            employee_pf=run.employee_pf,
            employer_pf=run.employer_pf,
            employee_esi=run.employee_esi,
            employer_esi=run.employer_esi,
            tds=run.tds,
            professional_tax=run.professional_tax,
            total_deductions=run.total_deductions,
            net_pay=run.net_pay,
            esi_applicable=run.esi_applicable,
            is_processed=run.is_processed,
        ))

    db.commit()

    return PayrollSummary(
        month=payload.month,
        year=payload.year,
        total_employees=len(employees),
        total_gross=round(total_gross, 2),
        total_employee_deductions=round(total_emp_deductions, 2),
        total_net_pay=round(total_net, 2),
        total_employer_pf=round(total_er_pf, 2),
        total_employer_esi=round(total_er_esi, 2),
        total_tds=round(total_tds, 2),
        payroll_runs=runs_out,
    )


# ── Get payroll summary for a month ──────────────────────────────────────────

@router.get("/summary", response_model=PayrollSummary)
def payroll_summary(
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000),
    db: Session = Depends(get_db),
):
    runs = (
        db.query(PayrollRun)
        .filter(PayrollRun.month == month, PayrollRun.year == year)
        .all()
    )
    if not runs:
        raise HTTPException(status_code=404, detail="No payroll data for this period")

    runs_out = []
    total_gross = total_deductions = total_net = 0.0
    total_er_pf = total_er_esi = total_tds = 0.0

    for run in runs:
        emp = db.query(Employee).filter(Employee.id == run.employee_id).first()
        runs_out.append(PayrollRunOut(
            id=run.id,
            employee_id=run.employee_id,
            employee_name=emp.name if emp else "Unknown",
            month=run.month,
            year=run.year,
            gross_salary=run.gross_salary,
            employee_pf=run.employee_pf,
            employer_pf=run.employer_pf,
            employee_esi=run.employee_esi,
            employer_esi=run.employer_esi,
            tds=run.tds,
            professional_tax=run.professional_tax,
            total_deductions=run.total_deductions,
            net_pay=run.net_pay,
            esi_applicable=run.esi_applicable,
            is_processed=run.is_processed,
        ))
        total_gross += run.gross_salary
        total_deductions += run.total_deductions
        total_net += run.net_pay
        total_er_pf += run.employer_pf
        total_er_esi += run.employer_esi
        total_tds += run.tds

    return PayrollSummary(
        month=month,
        year=year,
        total_employees=len(runs),
        total_gross=round(total_gross, 2),
        total_employee_deductions=round(total_deductions, 2),
        total_net_pay=round(total_net, 2),
        total_employer_pf=round(total_er_pf, 2),
        total_employer_esi=round(total_er_esi, 2),
        total_tds=round(total_tds, 2),
        payroll_runs=runs_out,
    )


# ── Standalone salary calculator (no DB) ─────────────────────────────────────

@router.post("/calculate", response_model=SalaryCalcOut)
def calculate_salary(payload: SalaryCalcRequest):
    """
    Calculate salary breakdown without creating any records.
    Useful for what-if analysis and onboarding salary negotiations.
    """
    result = calculate_payroll(
        basic=payload.basic,
        hra=payload.hra,
        special_allowance=payload.special_allowance,
        lta=payload.lta,
        medical_allowance=payload.medical_allowance,
        other_allowances=payload.other_allowances,
        tax_regime=payload.tax_regime,
    )
    return SalaryCalcOut(
        gross_salary=result.gross_salary,
        employee_pf=result.employee_pf,
        employer_pf=result.employer_pf,
        employee_esi=result.employee_esi,
        employer_esi=result.employer_esi,
        tds_monthly=result.tds_monthly,
        total_deductions=result.total_deductions,
        net_pay=result.net_pay,
        esi_applicable=result.esi_applicable,
        annual_gross=result.annual_gross,
        annual_tax=result.annual_tax,
        ctc=result.ctc,
    )


# ── History for a single employee ────────────────────────────────────────────

@router.get("/history/{employee_id}")
def employee_payroll_history(
    employee_id: int,
    db: Session = Depends(get_db),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    runs = (
        db.query(PayrollRun)
        .filter(PayrollRun.employee_id == employee_id)
        .order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
        .all()
    )
    return {
        "employee_id": employee_id,
        "name": emp.name,
        "runs": [
            {
                "month": r.month,
                "year": r.year,
                "gross_salary": r.gross_salary,
                "total_deductions": r.total_deductions,
                "net_pay": r.net_pay,
                "tds": r.tds,
                "employee_pf": r.employee_pf,
            }
            for r in runs
        ],
    }
