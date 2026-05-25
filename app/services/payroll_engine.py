"""
India Payroll Calculation Engine
─────────────────────────────────
Implements statutory rules as of FY 2024-25:

  PF   : Employee & Employer 12% of basic (capped at ₹15,000/month)
         EPS = 8.33% of basic (max ₹1,250/month) — part of employer share
  ESI  : Applicable when gross ≤ ₹21,000/month
         Employee 0.75% | Employer 3.25%
  TDS  : Section 192 — New vs Old regime slabs
  PT   : Professional Tax (Karnataka default — override per state)
"""

from dataclasses import dataclass
from app.models import TaxRegime


# ── Constants ─────────────────────────────────────────────────────────────────

PF_WAGE_CEILING = 15_000          # ₹/month — PF computed on min(basic, ceiling)
PF_EMPLOYEE_RATE = 0.12
PF_EMPLOYER_RATE = 0.12
EPS_RATE = 0.0833                  # Part of employer share
EPS_MAX = 1_250                    # ₹/month max EPS

ESI_WAGE_CEILING = 21_000         # ₹/month gross — if gross > this, no ESI
ESI_EMPLOYEE_RATE = 0.0075
ESI_EMPLOYER_RATE = 0.0325

STANDARD_DEDUCTION_NEW = 75_000   # FY 2024-25 new regime
STANDARD_DEDUCTION_OLD = 50_000

# New regime slabs (FY 2024-25) — (slab_limit, rate)
NEW_REGIME_SLABS = [
    (300_000, 0.00),
    (400_000, 0.05),   # 3L – 7L
    (300_000, 0.10),   # 7L – 10L
    (200_000, 0.15),   # 10L – 12L
    (300_000, 0.20),   # 12L – 15L
    (float("inf"), 0.30),
]

# Old regime slabs
OLD_REGIME_SLABS = [
    (250_000, 0.00),
    (250_000, 0.05),   # 2.5L – 5L
    (500_000, 0.20),   # 5L – 10L
    (float("inf"), 0.30),
]

REBATE_87A_NEW = 25_000           # Rebate if taxable income ≤ ₹7L (new)
REBATE_87A_OLD = 12_500           # Rebate if taxable income ≤ ₹5L (old)
SURCHARGE_THRESHOLD = 5_000_000   # ₹50L — simplified; full surcharge not modelled

# Karnataka Professional Tax (most common reference; adjust per state)
PT_SLABS = [
    (15_000, 0),
    (float("inf"), 200),          # ₹200/month above ₹15,000 gross
]


# ── Dataclass result ──────────────────────────────────────────────────────────

@dataclass
class PayrollResult:
    gross_salary: float
    basic: float
    hra: float
    special_allowance: float
    lta: float
    medical_allowance: float
    other_allowances: float

    employee_pf: float
    employer_pf: float
    eps: float                    # Pension component inside employer PF
    employee_esi: float
    employer_esi: float
    tds_monthly: float
    professional_tax: float

    esi_applicable: bool
    annual_gross: float
    annual_taxable_income: float
    annual_tax: float

    @property
    def total_deductions(self) -> float:
        return round(
            self.employee_pf + self.employee_esi
            + self.tds_monthly + self.professional_tax, 2
        )

    @property
    def net_pay(self) -> float:
        return round(self.gross_salary - self.total_deductions, 2)

    @property
    def ctc(self) -> float:
        """Cost to company = gross + employer PF + employer ESI"""
        return round(self.gross_salary + self.employer_pf + self.employer_esi, 2)


# ── Core engine ───────────────────────────────────────────────────────────────

def calculate_payroll(
    basic: float,
    hra: float = 0,
    special_allowance: float = 0,
    lta: float = 0,
    medical_allowance: float = 0,
    other_allowances: float = 0,
    tax_regime: TaxRegime = TaxRegime.new,
    professional_tax_state: str = "KA",
) -> PayrollResult:
    """
    Calculate monthly payroll for one employee.

    Parameters
    ----------
    basic, hra, ... : monthly salary components in ₹
    tax_regime      : 'new' or 'old'
    professional_tax_state : 2-letter state code (default Karnataka)

    Returns
    -------
    PayrollResult with all computed fields
    """
    gross = round(basic + hra + special_allowance + lta + medical_allowance + other_allowances, 2)

    # ── Provident Fund ────────────────────────────────────────────────────────
    pf_base = min(basic, PF_WAGE_CEILING)
    emp_pf = round(pf_base * PF_EMPLOYEE_RATE)
    er_pf = round(pf_base * PF_EMPLOYER_RATE)
    eps = min(round(pf_base * EPS_RATE), EPS_MAX)   # informational

    # ── ESI ───────────────────────────────────────────────────────────────────
    esi_applicable = gross <= ESI_WAGE_CEILING
    emp_esi = round(gross * ESI_EMPLOYEE_RATE) if esi_applicable else 0
    er_esi = round(gross * ESI_EMPLOYER_RATE) if esi_applicable else 0

    # ── Professional Tax (Karnataka) ─────────────────────────────────────────
    pt = _professional_tax(gross, professional_tax_state)

    # ── TDS ───────────────────────────────────────────────────────────────────
    annual_gross = gross * 12
    annual_tax, annual_taxable = _compute_tds(
        annual_gross=annual_gross,
        annual_emp_pf=emp_pf * 12,
        tax_regime=tax_regime,
    )
    tds_monthly = round(annual_tax / 12)

    return PayrollResult(
        gross_salary=gross,
        basic=basic,
        hra=hra,
        special_allowance=special_allowance,
        lta=lta,
        medical_allowance=medical_allowance,
        other_allowances=other_allowances,
        employee_pf=emp_pf,
        employer_pf=er_pf,
        eps=eps,
        employee_esi=emp_esi,
        employer_esi=er_esi,
        tds_monthly=tds_monthly,
        professional_tax=pt,
        esi_applicable=esi_applicable,
        annual_gross=annual_gross,
        annual_taxable_income=annual_taxable,
        annual_tax=annual_tax,
    )


# ── TDS helpers ───────────────────────────────────────────────────────────────

def _compute_tds(
    annual_gross: float,
    annual_emp_pf: float,
    tax_regime: TaxRegime,
) -> tuple[float, float]:
    """
    Returns (annual_tax, taxable_income).
    Simplified model — does not include HRA exemption, 80C, etc. for old regime.
    For old regime, a ₹1.5L 80C deduction is assumed (common case).
    """
    if tax_regime == TaxRegime.new:
        std_ded = STANDARD_DEDUCTION_NEW
        taxable = max(0, annual_gross - std_ded)
        tax = _apply_slabs(taxable, NEW_REGIME_SLABS)
        # Rebate u/s 87A — if taxable ≤ ₹7L, tax = 0
        if taxable <= 700_000:
            tax = 0
    else:
        std_ded = STANDARD_DEDUCTION_OLD
        deductions_80c = min(annual_emp_pf, 150_000)   # PF qualifies under 80C
        taxable = max(0, annual_gross - std_ded - deductions_80c)
        tax = _apply_slabs(taxable, OLD_REGIME_SLABS)
        if taxable <= 500_000:
            tax = max(0, tax - REBATE_87A_OLD)

    # 4% health & education cess
    tax = round(tax * 1.04)
    return tax, round(taxable)


def _apply_slabs(
    taxable_income: float,
    slabs: list[tuple[float, float]],
) -> float:
    tax = 0.0
    remaining = taxable_income
    for slab_limit, rate in slabs:
        if remaining <= 0:
            break
        chunk = min(remaining, slab_limit)
        tax += chunk * rate
        remaining -= chunk
    return round(tax)


def _professional_tax(gross: float, state: str) -> float:
    """Returns monthly professional tax amount."""
    if state == "KA":
        return 200 if gross > 15_000 else 0
    if state == "MH":
        if gross <= 7_500:
            return 0
        elif gross <= 10_000:
            return 175
        else:
            return 200
    if state == "TN":
        return 208 if gross > 21_000 else 0
    # Default: no PT
    return 0


# ── Compliance summary helper ─────────────────────────────────────────────────

def compliance_summary_from_runs(runs: list) -> dict:
    """
    Aggregate payroll runs into a compliance summary.
    `runs` is a list of PayrollRun ORM objects.
    """
    total_pf = sum(r.employee_pf + r.employer_pf for r in runs)
    total_esi = sum(r.employee_esi + r.employer_esi for r in runs)
    total_tds = sum(r.tds for r in runs)
    esi_count = sum(1 for r in runs if r.esi_applicable)

    return {
        "total_pf_remittance": round(total_pf, 2),
        "total_esi_remittance": round(total_esi, 2),
        "total_tds_deposit": round(total_tds, 2),
        "esi_eligible_employees": esi_count,
        "pf_due_date": "15th of following month",
        "tds_due_date": "7th of following month",
    }
