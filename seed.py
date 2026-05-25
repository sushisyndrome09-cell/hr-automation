"""
seed.py — Populate the database with sample employees and run May 2025 payroll.
Run: python seed.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.database import SessionLocal, engine, Base
from app.models import Employee, TaxRegime, EmploymentStatus
from app.services.payroll_engine import calculate_payroll
from app.models import PayrollRun
import datetime

Base.metadata.create_all(bind=engine)

SAMPLE_EMPLOYEES = [
    dict(name="Priya Sharma",   email="priya@example.com",   designation="Senior Engineer",  department="Engineering", pan_number="ABCPS1111A", basic=60000, hra=24000, special_allowance=15000, lta=4000, medical_allowance=1250, tax_regime=TaxRegime.new),
    dict(name="Arjun Mehta",    email="arjun@example.com",   designation="Product Manager",  department="Product",     pan_number="ABCPM2222B", basic=75000, hra=30000, special_allowance=20000, lta=5000, medical_allowance=1250, tax_regime=TaxRegime.new),
    dict(name="Kavitha Nair",   email="kavitha@example.com", designation="HR Executive",     department="HR",          pan_number="ABCKN3333C", basic=30000, hra=12000, special_allowance=8000,  lta=2000, medical_allowance=1250, tax_regime=TaxRegime.old),
    dict(name="Rahul Gupta",    email="rahul@example.com",   designation="Data Analyst",     department="Analytics",   pan_number="ABCRG4444D", basic=45000, hra=18000, special_allowance=12000, lta=3000, medical_allowance=1250, tax_regime=TaxRegime.new),
    dict(name="Sneha Iyer",     email="sneha@example.com",   designation="UX Designer",      department="Design",      pan_number="ABCSI5555E", basic=50000, hra=20000, special_allowance=13000, lta=3500, medical_allowance=1250, tax_regime=TaxRegime.new),
    dict(name="Vikram Rao",     email="vikram@example.com",  designation="DevOps Engineer",  department="Engineering", pan_number="ABCVR6666F", basic=55000, hra=22000, special_allowance=14000, lta=4000, medical_allowance=1250, tax_regime=TaxRegime.new),
]

db = SessionLocal()

try:
    existing = db.query(Employee).count()
    if existing > 0:
        print(f"Database already has {existing} employees. Skipping seed.")
    else:
        for i, data in enumerate(SAMPLE_EMPLOYEES, start=1):
            emp = Employee(
                employee_code=f"EMP{str(i).zfill(4)}",
                date_of_joining=datetime.date(2022, 1, 15),
                bank_name="HDFC Bank",
                bank_account=f"5020000{i:04d}",
                bank_ifsc="HDFC0001234",
                status=EmploymentStatus.active,
                **data,
            )
            db.add(emp)
        db.commit()
        print(f"✓ Added {len(SAMPLE_EMPLOYEES)} employees")

    # Run payroll for May 2025
    employees = db.query(Employee).filter(Employee.status == EmploymentStatus.active).all()
    month, year = 5, 2025
    count = 0
    for emp in employees:
        existing_run = db.query(PayrollRun).filter(
            PayrollRun.employee_id == emp.id,
            PayrollRun.month == month,
            PayrollRun.year == year,
        ).first()
        if existing_run:
            continue
        r = calculate_payroll(
            basic=emp.basic, hra=emp.hra,
            special_allowance=emp.special_allowance, lta=emp.lta,
            medical_allowance=emp.medical_allowance,
            other_allowances=emp.other_allowances,
            tax_regime=emp.tax_regime,
        )
        run = PayrollRun(
            employee_id=emp.id, month=month, year=year,
            gross_salary=r.gross_salary, basic=r.basic, hra=r.hra,
            special_allowance=r.special_allowance, lta=r.lta,
            medical_allowance=r.medical_allowance, other_allowances=r.other_allowances,
            employee_pf=r.employee_pf, employer_pf=r.employer_pf,
            employee_esi=r.employee_esi, employer_esi=r.employer_esi,
            tds=r.tds_monthly, professional_tax=r.professional_tax,
            total_deductions=r.total_deductions, net_pay=r.net_pay,
            esi_applicable=r.esi_applicable, is_processed=True,
        )
        db.add(run)
        count += 1
    db.commit()
    if count:
        print(f"✓ Payroll processed for May 2025 ({count} employees)")
    else:
        print("✓ Payroll for May 2025 already exists")

    print("\nAll done! Start the API with:")
    print("  uvicorn app.main:app --reload")
    print("\nSwagger UI: http://127.0.0.1:8000/docs")

finally:
    db.close()
