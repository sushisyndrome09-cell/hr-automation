from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.models import Employee, EmploymentStatus
from app.schemas import EmployeeCreate, EmployeeUpdate, EmployeeOut

router = APIRouter()


def _generate_code(db: Session) -> str:
    count = db.query(Employee).count()
    return f"EMP{str(count + 1).zfill(4)}"


# ── Create ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(payload: EmployeeCreate, db: Session = Depends(get_db)):
    # Duplicate checks
    if payload.pan_number:
        existing = db.query(Employee).filter(Employee.pan_number == payload.pan_number).first()
        if existing:
            raise HTTPException(status_code=400, detail="PAN number already registered")
    if payload.email:
        existing = db.query(Employee).filter(Employee.email == payload.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

    emp = Employee(
        employee_code=_generate_code(db),
        **payload.model_dump(),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp


# ── List ──────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[EmployeeOut])
def list_employees(
    status: str = None,
    department: str = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    query = db.query(Employee)
    if status:
        query = query.filter(Employee.status == status)
    if department:
        query = query.filter(Employee.department == department)
    return query.offset(skip).limit(limit).all()


# ── Get one ───────────────────────────────────────────────────────────────────

@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: int, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp


# ── Update ────────────────────────────────────────────────────────────────────

@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: int,
    payload: EmployeeUpdate,
    db: Session = Depends(get_db),
):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(emp, field, value)

    db.commit()
    db.refresh(emp)
    return emp


# ── Deactivate / Terminate ────────────────────────────────────────────────────

@router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def terminate_employee(employee_id: int, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    emp.status = EmploymentStatus.terminated
    db.commit()


# ── Salary preview for an employee ───────────────────────────────────────────

@router.get("/{employee_id}/salary-preview")
def salary_preview(employee_id: int, db: Session = Depends(get_db)):
    from app.services.payroll_engine import calculate_payroll

    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")

    result = calculate_payroll(
        basic=emp.basic,
        hra=emp.hra,
        special_allowance=emp.special_allowance,
        lta=emp.lta,
        medical_allowance=emp.medical_allowance,
        other_allowances=emp.other_allowances,
        tax_regime=emp.tax_regime,
    )
    return {
        "employee_id": emp.id,
        "name": emp.name,
        "gross_salary": result.gross_salary,
        "employee_pf": result.employee_pf,
        "employer_pf": result.employer_pf,
        "employee_esi": result.employee_esi,
        "employer_esi": result.employer_esi,
        "tds_monthly": result.tds_monthly,
        "professional_tax": result.professional_tax,
        "total_deductions": result.total_deductions,
        "net_pay": result.net_pay,
        "ctc": result.ctc,
        "esi_applicable": result.esi_applicable,
        "annual_gross": result.annual_gross,
        "annual_taxable_income": result.annual_taxable_income,
        "annual_tax": result.annual_tax,
    }
