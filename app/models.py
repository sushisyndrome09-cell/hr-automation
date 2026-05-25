from sqlalchemy import Column, Integer, String, Float, Boolean, Date, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class TaxRegime(str, enum.Enum):
    new = "new"
    old = "old"


class EmploymentStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    terminated = "terminated"


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String, unique=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True)
    phone = Column(String)
    pan_number = Column(String, unique=True)
    uan_number = Column(String)          # Universal Account Number for PF
    esic_number = Column(String)
    designation = Column(String)
    department = Column(String)
    date_of_joining = Column(Date)
    date_of_birth = Column(Date)
    bank_account = Column(String)
    bank_ifsc = Column(String)
    bank_name = Column(String)
    tax_regime = Column(Enum(TaxRegime), default=TaxRegime.new)
    status = Column(Enum(EmploymentStatus), default=EmploymentStatus.active)

    # Salary component (monthly ₹)
    basic = Column(Float, default=0)
    hra = Column(Float, default=0)
    special_allowance = Column(Float, default=0)
    lta = Column(Float, default=0)
    medical_allowance = Column(Float, default=0)
    other_allowances = Column(Float, default=0)

    payroll_runs = relationship("PayrollRun", back_populates="employee")


class PayrollRun(Base):
    __tablename__ = "payroll_runs"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    month = Column(Integer)
    year = Column(Integer)

    # Earnings
    gross_salary = Column(Float)
    basic = Column(Float)
    hra = Column(Float)
    special_allowance = Column(Float)
    lta = Column(Float)
    medical_allowance = Column(Float)
    other_allowances = Column(Float)

    # Deductions
    employee_pf = Column(Float)
    employer_pf = Column(Float)
    employee_esi = Column(Float)
    employer_esi = Column(Float)
    tds = Column(Float)
    professional_tax = Column(Float, default=0)
    total_deductions = Column(Float)

    # Net
    net_pay = Column(Float)

    # Flags
    esi_applicable = Column(Boolean, default=False)
    is_processed = Column(Boolean, default=False)

    employee = relationship("Employee", back_populates="payroll_runs")
