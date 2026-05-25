# India HR Payroll System — FastAPI

Complete payroll automation backend for Indian companies.
Handles **PF, ESI, TDS (Section 192)**, and Professional Tax.

---

## Project structure

```
payroll/
├── app/
│   ├── main.py               # FastAPI app + CORS
│   ├── database.py           # SQLAlchemy (SQLite by default)
│   ├── models.py             # ORM models: Employee, PayrollRun
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── routers/
│   │   ├── employees.py      # CRUD + salary preview
│   │   ├── payroll.py        # Run payroll, calculator, history
│   │   ├── payslip.py        # Individual & bulk payslips
│   │   └── compliance.py     # PF / ESI / TDS reports
│   └── services/
│       └── payroll_engine.py # Core calculation logic
├── seed.py                   # Sample data loader
├── requirements.txt
└── README.md
```

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Seed sample employees + May 2025 payroll
python seed.py

# 3. Start the API
uvicorn app.main:app --reload
```

Open **http://127.0.0.1:8000/docs** for interactive Swagger UI.

---

## API reference

### Employees `/api/employees`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/` | Add a new employee |
| GET | `/` | List employees (filter: status, department) |
| GET | `/{id}` | Get employee by ID |
| PATCH | `/{id}` | Update employee details / salary |
| DELETE | `/{id}` | Terminate employee |
| GET | `/{id}/salary-preview` | Preview salary breakdown |

### Payroll `/api/payroll`

| Method | Path | Description |
|--------|------|-------------|
| POST | `/run` | Run payroll for a month |
| GET | `/summary?month=5&year=2025` | Monthly payroll summary |
| POST | `/calculate` | Standalone salary calculator (no DB) |
| GET | `/history/{employee_id}` | Employee's payroll history |

### Payslip `/api/payslip`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/{employee_id}?month=5&year=2025` | Single employee payslip |
| GET | `/bulk/{month}/{year}` | All payslips for a period |

### Compliance `/api/compliance`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/summary?month=5&year=2025` | PF + ESI + TDS totals |
| GET | `/pf-report?month=5&year=2025` | ECR-format PF report |
| GET | `/esi-report?month=5&year=2025` | ESI contribution report |
| GET | `/tds-report?month=5&year=2025` | TDS (Form 24Q) report |
| GET | `/filing-calendar` | All statutory due dates |

---

## Statutory rules implemented (FY 2024-25)

### Provident Fund
- Employee & Employer: **12% of basic** (capped at ₹15,000/month)
- EPS (pension): **8.33%** of PF wages, max ₹1,250/month
- Due: **15th of following month**

### ESI
- Applicable when **gross ≤ ₹21,000/month**
- Employee: **0.75%** | Employer: **3.25%**
- Due: **15th of following month**

### TDS (Section 192)
**New regime slabs:**
| Income (annual) | Rate |
|----------------|------|
| Up to ₹3,00,000 | 0% |
| ₹3L – ₹7L | 5% |
| ₹7L – ₹10L | 10% |
| ₹10L – ₹12L | 15% |
| ₹12L – ₹15L | 20% |
| Above ₹15L | 30% |
- Standard deduction: ₹75,000 (new) / ₹50,000 (old)
- Rebate 87A: no tax if taxable ≤ ₹7L (new) / ≤ ₹5L (old)
- 4% health & education cess on computed tax
- TDS deposit due: **7th of following month**

### Professional Tax
- Karnataka default: ₹200/month if gross > ₹15,000
- Override `professional_tax_state` in `calculate_payroll()` for other states (MH, TN supported)

---

## Switching to PostgreSQL

In `app/database.py`, replace:
```python
SQLALCHEMY_DATABASE_URL = "sqlite:///./payroll.db"
```
with:
```python
SQLALCHEMY_DATABASE_URL = "postgresql://user:password@localhost/payroll_db"
```
Remove `connect_args={"check_same_thread": False}` from `create_engine`.
