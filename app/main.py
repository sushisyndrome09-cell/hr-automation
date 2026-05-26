from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import employees, payroll, payslip, compliance, excel_upload
from app.database import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="India HR Payroll System",
    description="Complete payroll automation with PF, ESI, TDS compliance for India",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(employees.router, prefix="/api/employees", tags=["Employees"])
app.include_router(payroll.router, prefix="/api/payroll", tags=["Payroll"])
app.include_router(payslip.router, prefix="/api/payslip", tags=["Payslip"])
app.include_router(compliance.router, prefix="/api/compliance", tags=["Compliance"])
app.include_router(excel_upload.router, prefix="/api/excel", tags=["Excel Upload"])


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "message": "India HR Payroll API is running"}
