from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import date
from app.models import TaxRegime, EmploymentStatus


# ── Employee ──────────────────────────────────────────────
class SalaryComponents(BaseModel):
    basic: float = Field(..., ge=0, description="Basic salary per month")
    hra: float = Field(0, ge=0)
    special_allowance: float = Field(0, ge=0)
    lta: float = Field(0, ge=0)
    medical_allowance: float = Field(0, ge=0)
    other_allowances: float = Field(0, ge=0)


class EmployeeCreate(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    pan_number: Optional[str] = None
    uan_number: Optional[str] = None
    esic_number: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    date_of_joining: Optional[date] = None
    date_of_birth: Optional[date] = None
    bank_account: Optional[str] = None
    bank_ifsc: Optional[str] = None
    bank_name: Optional[str] = None
    tax_regime: TaxRegime = TaxRegime.new
    basic: float = Field(..., ge=0)
    hra: float = Field(0, ge=0)
    special_allowance: float = Field(0, ge=0)
    lta: float = Field(0, ge=0)
    medical_allowance: float = Field(0, ge=0)
    other_allowances: float = Field(0, ge=0)


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    tax_regime: Optional[TaxRegime] = None
    status: Optional[EmploymentStatus] = None
    basic: Optional[float] = None
    hra: Optional[float] = None
    special_allowance: Optional[float] = None
    lta: Optional[float] = None
    medical_allowance: Optional[float] = None
    other_allowances: Optional[float] = None


class EmployeeOut(BaseModel):
    id: int
    employee_code: str
    name: str
    email: Optional[str]
    phone: Optional[str]
    pan_number: Optional[str]
    uan_number: Optional[str]
    designation: Optional[str]
    department: Optional[str]
    date_of_joining: Optional[date]
    tax_regime: TaxRegime
    status: EmploymentStatus
    basic: float
    hra: float
    special_allowance: float
    lta: float
    medical_allowance: float
    other_allowances: float

    class Config:
        from_attributes = True


# ── Payroll ───────────────────────────────────────────────
class PayrollRunRequest(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2000)
    employee_ids: Optional[list[int]] = None  # None = run for all active employees


class PayrollRunOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    month: int
    year: int
    gross_salary: float
    employee_pf: float
    employer_pf: float
    employee_esi: float
    employer_esi: float
    tds: float
    professional_tax: float
    total_deductions: float
    net_pay: float
    esi_applicable: bool
    is_processed: bool

    class Config:
        from_attributes = True


class PayrollSummary(BaseModel):
    month: int
    year: int
    total_employees: int
    total_gross: float
    total_employee_deductions: float
    total_net_pay: float
    total_employer_pf: float
    total_employer_esi: float
    total_tds: float
    payroll_runs: list[PayrollRunOut]


# ── Salary Calculator (standalone, no employee needed) ────
class SalaryCalcRequest(BaseModel):
    basic: float = Field(..., ge=0)
    hra: float = Field(0, ge=0)
    special_allowance: float = Field(0, ge=0)
    lta: float = Field(0, ge=0)
    medical_allowance: float = Field(0, ge=0)
    other_allowances: float = Field(0, ge=0)
    tax_regime: TaxRegime = TaxRegime.new


class SalaryCalcOut(BaseModel):
    gross_salary: float
    employee_pf: float
    employer_pf: float
    employee_esi: float
    employer_esi: float
    tds_monthly: float
    total_deductions: float
    net_pay: float
    esi_applicable: bool
    annual_gross: float
    annual_tax: float
    ctc: float  # Cost to company


# ── Compliance ────────────────────────────────────────────
class ComplianceSummary(BaseModel):
    month: int
    year: int
    total_pf_remittance: float       # employer + employee PF
    total_esi_remittance: float      # employer + employee ESI
    total_tds_deposit: float
    esi_eligible_employees: int
    pf_due_date: str
    tds_due_date: str
