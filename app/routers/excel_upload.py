from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Employee, PayrollRun, EmploymentStatus, TaxRegime
from app.services.payroll_engine import calculate_payroll
import pandas as pd
import io
import math

router = APIRouter()


def safe(val, default=0):
    """Return default if val is NaN/None. Handles duplicate columns (Series)."""
    if isinstance(val, pd.Series):
        val = val.iloc[0] if len(val) > 0 else default
    if val is None:
        return default
    try:
        if math.isnan(float(val)):
            return default
    except (TypeError, ValueError):
        pass
    return val


def safe_str(val, default=""):
    if isinstance(val, pd.Series):
        val = val.iloc[0] if len(val) > 0 else default
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    return str(val).strip()


def generate_code(db: Session) -> str:
    count = db.query(Employee).count()
    return f"EMP{str(count + 1).zfill(4)}"


@router.post("/upload")
async def upload_excel(
    file: UploadFile = File(...),
    month: int = Query(5, ge=1, le=12),
    year: int = Query(2025, ge=2000),
    db: Session = Depends(get_db),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Please upload an Excel file (.xlsx or .xls)")

    contents = await file.read()
    try:
        df = pd.read_excel(io.BytesIO(contents), header=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read Excel file: {str(e)}")

    # Find header row containing NAME and BASIC
    header_row = None
    for i, row in df.iterrows():
        row_upper = [str(v).upper().strip() for v in row.values]
        if any("NAME" in v for v in row_upper) and any("BASIC" in v for v in row_upper):
            header_row = i
            break

    if header_row is None:
        raise HTTPException(status_code=400, detail="Could not find header row. Make sure Excel has NAME and BASIC columns.")

    # Build column names — deduplicate by adding suffix
    raw_cols = [str(v).strip().upper().replace("\n", " ").replace("  ", " ") for v in df.iloc[header_row]]
    seen = {}
    deduped_cols = []
    for c in raw_cols:
        if c in seen:
            seen[c] += 1
            deduped_cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            deduped_cols.append(c)

    df.columns = deduped_cols
    df = df.iloc[header_row + 1:].reset_index(drop=True)
    df = df.dropna(how="all")

    def find_col(keywords):
        for col in df.columns:
            col_clean = col.upper().replace(" ", "").replace(".", "").replace("\n", "")
            for kw in keywords:
                if kw in col_clean:
                    return col
        return None

    col_name     = find_col(["NAME"])
    col_empcode  = find_col(["EMPCODE", "EMPNO", "EMPLOYEECODE"])
    col_uan      = find_col(["UAN"])
    col_bank     = find_col(["BANKNAME", "BANK"])
    col_basic    = find_col(["BASIC"])
    col_da       = find_col(["DA"])
    col_hra      = find_col(["HRA"])
    col_ot       = find_col(["OTDAYS", "OVERTIME"])
    col_lop      = find_col(["LOP"])
    col_pt       = find_col(["PT"])
    col_loan     = find_col(["LOAN", "ADVANCE"])
    col_tds      = find_col(["TDS"])
    col_days     = find_col(["DAYSINMONTH", "NOOFDAYS"])
    col_perday   = find_col(["PERDAY", "PERDAYSALARY"])

    if not col_name:
        raise HTTPException(status_code=400, detail="Could not find NAME column.")
    if not col_basic:
        raise HTTPException(status_code=400, detail="Could not find BASIC column.")

    results = []
    skipped = []
    employees_added = 0
    employees_updated = 0

    for _, row in df.iterrows():
        name = safe_str(row.get(col_name, ""))
        if not name or name.upper() in ["NAME", "TOTAL", "GRAND TOTAL", ""]:
            continue

        basic = float(safe(row.get(col_basic), 0))
        if basic == 0:
            skipped.append({"name": name, "reason": "Basic salary is 0 or missing"})
            continue

        da          = float(safe(row.get(col_da), 0)) if col_da else 0
        hra         = float(safe(row.get(col_hra), 0)) if col_hra else 0
        emp_code    = safe_str(row.get(col_empcode, "")) if col_empcode else ""
        uan         = safe_str(row.get(col_uan, "")) if col_uan else ""
        bank_name   = safe_str(row.get(col_bank, "")) if col_bank else ""
        lop_days    = float(safe(row.get(col_lop), 0)) if col_lop else 0
        ot_days     = float(safe(row.get(col_ot), 0)) if col_ot else 0
        per_day     = float(safe(row.get(col_perday), 0)) if col_perday else 0
        manual_pt   = float(safe(row.get(col_pt), 0)) if col_pt else None
        manual_loan = float(safe(row.get(col_loan), 0)) if col_loan else 0
        manual_tds  = float(safe(row.get(col_tds), 0)) if col_tds else None
        days_in_month = float(safe(row.get(col_days), 30)) if col_days else 30

        fixed_gross = basic + da + hra
        if per_day == 0 and days_in_month > 0:
            per_day = round(fixed_gross / days_in_month, 2)

        lop_deduction = round(per_day * lop_days, 2)
        ot_amount     = round(per_day * ot_days, 2) if ot_days > 0 else 0

        lop_ratio      = lop_days / days_in_month if days_in_month > 0 else 0
        adjusted_basic = round(basic * (1 - lop_ratio), 2)
        adjusted_hra   = round(hra   * (1 - lop_ratio), 2)
        adjusted_da    = round(da    * (1 - lop_ratio), 2)

        # Find or create employee
        emp = None
        if emp_code:
            emp = db.query(Employee).filter(Employee.employee_code == emp_code).first()
        if not emp:
            emp = db.query(Employee).filter(Employee.name == name).first()

        if not emp:
            emp = Employee(
                employee_code=emp_code or generate_code(db),
                name=name,
                uan_number=uan or None,
                bank_name=bank_name or None,
                basic=basic,
                hra=hra,
                special_allowance=da,
                lta=0,
                medical_allowance=0,
                other_allowances=0,
                tax_regime=TaxRegime.new,
                status=EmploymentStatus.active,
            )
            db.add(emp)
            db.flush()
            employees_added += 1
        else:
            emp.basic = basic
            emp.hra   = hra
            emp.special_allowance = da
            if uan: emp.uan_number = uan
            if bank_name: emp.bank_name = bank_name
            employees_updated += 1

        result = calculate_payroll(
            basic=adjusted_basic,
            hra=adjusted_hra,
            special_allowance=adjusted_da,
            lta=0,
            medical_allowance=0,
            other_allowances=ot_amount,
            tax_regime=emp.tax_regime,
        )

        tds_final   = manual_tds if manual_tds is not None else result.tds_monthly
        pt_final    = manual_pt  if manual_pt  is not None else result.professional_tax
        total_ded   = result.employee_pf + result.employee_esi + tds_final + pt_final + manual_loan
        net_pay     = round(result.gross_salary - total_ded, 2)

        existing = db.query(PayrollRun).filter(
            PayrollRun.employee_id == emp.id,
            PayrollRun.month == month,
            PayrollRun.year == year,
        ).first()

        run = existing or PayrollRun(employee_id=emp.id, month=month, year=year)
        run.gross_salary      = result.gross_salary
        run.basic             = adjusted_basic
        run.hra               = adjusted_hra
        run.special_allowance = adjusted_da
        run.lta               = 0
        run.medical_allowance = 0
        run.other_allowances  = ot_amount
        run.employee_pf       = result.employee_pf
        run.employer_pf       = result.employer_pf
        run.employee_esi      = result.employee_esi
        run.employer_esi      = result.employer_esi
        run.tds               = tds_final
        run.professional_tax  = pt_final
        run.total_deductions  = total_ded
        run.net_pay           = net_pay
        run.esi_applicable    = result.esi_applicable
        run.is_processed      = True

        if not existing:
            db.add(run)

        results.append({
            "employee_code": emp.employee_code,
            "name": name,
            "basic": adjusted_basic,
            "lop_days": lop_days,
            "lop_deduction": lop_deduction,
            "ot_days": ot_days,
            "ot_amount": ot_amount,
            "gross_salary": result.gross_salary,
            "employee_pf": result.employee_pf,
            "employer_pf": result.employer_pf,
            "employee_esi": result.employee_esi,
            "tds": tds_final,
            "professional_tax": pt_final,
            "loan_advance": manual_loan,
            "total_deductions": total_ded,
            "net_pay": net_pay,
        })

    db.commit()

    return {
        "status": "success",
        "month": month,
        "year": year,
        "employees_added": employees_added,
        "employees_updated": employees_updated,
        "employees_processed": len(results),
        "skipped": skipped,
        "summary": {
            "total_gross": round(sum(r["gross_salary"] for r in results), 2),
            "total_deductions": round(sum(r["total_deductions"] for r in results), 2),
            "total_net_pay": round(sum(r["net_pay"] for r in results), 2),
            "total_employee_pf": round(sum(r["employee_pf"] for r in results), 2),
            "total_employer_pf": round(sum(r["employer_pf"] for r in results), 2),
        },
        "payroll_runs": results,
    }


@router.get("/template")
def download_template():
    return {
        "required_columns": ["NAME", "BASIC"],
        "optional_columns": ["EMP CODE", "UAN NUMBERS", "BANK NAME", "HRA", "DA",
                             "PER DAY SALARY", "NO. OF DAYS IN MONTH", "LOP", "OT DAYS",
                             "PT", "TDS", "LOAN/ADVANCE"],
        "notes": [
            "Duplicate column names are handled automatically",
            "LOP days reduce salary proportionally",
            "OT days add to salary",
            "TDS and PT from Excel override auto-calculated values",
        ]
    }
