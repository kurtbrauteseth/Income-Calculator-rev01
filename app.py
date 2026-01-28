import copy
import uuid
from typing import Any, Dict, List, Tuple

import streamlit as st

# -----------------------------
# Constants (backend defaults)
# -----------------------------
SG_RATE = 0.12  # 12% SG (from 1 July 2025 onward)

# -----------------------------
# State helpers
# -----------------------------
def _ensure_state() -> None:
    if "household" not in st.session_state:
        st.session_state.household = {
            "tax_year_label": "2025–26",
            "is_couple": True,
            "dependant_children": 0,
            "private_hospital_cover_couple": False,
        }

    if "person_a" not in st.session_state:
        st.session_state.person_a = {
            "base_salary_annual": 0.0,
            "salary_includes_sg": False,
            "weeks_away": 0,
            "uplift_pct": 0.0,
            "uplift_sg_applies": False,
            "extra_concessional_annual": 0.0,
            "reportable_fringe_benefits_annual": 0.0,
        }

    if "person_b" not in st.session_state:
        st.session_state.person_b = {
            "base_salary_annual": 0.0,
            "salary_includes_sg": False,
            "weeks_away": 0,
            "uplift_pct": 0.0,
            "uplift_sg_applies": False,
            "extra_concessional_annual": 0.0,
            "reportable_fringe_benefits_annual": 0.0,
        }

    if "investments" not in st.session_state:
        st.session_state.investments = []

    if "scenarios" not in st.session_state:
        st.session_state.scenarios = {}

    if "active_scenario" not in st.session_state:
        st.session_state.active_scenario = None


def _snapshot() -> Dict[str, Any]:
    return {
        "household": copy.deepcopy(st.session_state.household),
        "person_a": copy.deepcopy(st.session_state.person_a),
        "person_b": copy.deepcopy(st.session_state.person_b),
        "investments": copy.deepcopy(st.session_state.investments),
    }


def _load_snapshot(payload: Dict[str, Any]) -> None:
    st.session_state.household = copy.deepcopy(payload.get("household", st.session_state.household))
    st.session_state.person_a = copy.deepcopy(payload.get("person_a", st.session_state.person_a))
    st.session_state.person_b = copy.deepcopy(payload.get("person_b", st.session_state.person_b))
    st.session_state.investments = copy.deepcopy(payload.get("investments", st.session_state.investments))


# -----------------------------
# Calculated (inputs-only) helpers
# -----------------------------
def calc_uplift_annual(base_salary_annual: float, uplift_pct: float, weeks_away: int) -> float:
    pct = max(0.0, float(uplift_pct)) / 100.0
    w = min(max(int(weeks_away), 0), 52)
    return float(base_salary_annual) * pct * (w / 52.0)


def calc_base_ote_annual(base_salary_annual: float, salary_includes_sg: bool) -> float:
    base = float(base_salary_annual)
    if salary_includes_sg and (1.0 + SG_RATE) > 0:
        return base / (1.0 + SG_RATE)
    return base


def calc_sg_annual(
    base_salary_annual: float,
    salary_includes_sg: bool,
    uplift_annual: float,
    uplift_sg_applies: bool,
) -> float:
    base_ote = calc_base_ote_annual(base_salary_annual, salary_includes_sg)
    ote = base_ote + (float(uplift_annual) if uplift_sg_applies else 0.0)
    return max(0.0, ote) * SG_RATE


def calc_property_gross_income_annual(rent_per_week: float, vacancy_weeks: int) -> float:
    weeks_rented = max(0, 52 - int(vacancy_weeks))
    return float(rent_per_week) * float(weeks_rented)


def _safe_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _fmt_money(x: float) -> str:
    return f"${x:,.0f}"


def _household_investment_splits(investments: list, is_couple: bool) -> Dict[str, float]:
    gross_total = 0.0
    deductions_total = 0.0
    net_taxable_total = 0.0

    a_gross = 0.0
    b_gross = 0.0
    a_net_taxable = 0.0
    b_net_taxable = 0.0

    for inv in investments:
        inv_type = inv.get("type", "Other")
        gross = _safe_float(inv.get("gross_income_annual", 0.0))

        if inv_type == "Investment property":
            gross = calc_property_gross_income_annual(
                rent_per_week=_safe_float(inv.get("rent_per_week", 0.0)),
                vacancy_weeks=int(inv.get("vacancy_weeks", 0)),
            )

        interest = _safe_float(inv.get("interest_deductible_annual", 0.0))
        other = _safe_float(inv.get("other_deductible_annual", 0.0))
        net_taxable = gross - interest - other

        gross_total += gross
        deductions_total += (interest + other)
        net_taxable_total += net_taxable

        if is_couple:
            a_pct = _safe_float(inv.get("ownership_a_pct", 50.0)) / 100.0
            a_pct = min(max(a_pct, 0.0), 1.0)
            b_pct = 1.0 - a_pct
        else:
            a_pct = 1.0
            b_pct = 0.0

        a_gross += gross * a_pct
        b_gross += gross * b_pct
        a_net_taxable += net_taxable * a_pct
        b_net_taxable += net_taxable * b_pct

    return {
        "gross_total": gross_total,
        "deductions_total": deductions_total,
        "net_taxable_total": net_taxable_total,
        "a_gross": a_gross,
        "b_gross": b_gross,
        "a_net_taxable": a_net_taxable,
        "b_net_taxable": b_net_taxable,
    }


# -----------------------------
# UI helpers
# -----------------------------
def money_input(label: str, key: str, value: float = 0.0, step: float = 1000.0) -> float:
    return float(
        st.number_input(
            label,
            min_value=0.0,
            value=float(value),
            step=float(step),
            format="%.2f",
            key=key,
        )
    )


def int_input(label: str, key: str, value: int = 0, min_value: int = 0, max_value: int = 52) -> int:
    return int(
        st.number_input(
            label,
            min_value=min_value,
            max_value=max_value,
            value=int(value),
            step=1,
            key=key,
        )
    )


def pct_input(label: str, key: str, value: float = 0.0, max_value: float = 300.0) -> float:
    return float(
        st.number_input(
            label,
            min_value=0.0,
            max_value=float(max_value),
            value=float(value),
            step=1.0,
            format="%.1f",
            key=key,
        )
    )


# -----------------------------
# App
# -----------------------------
st.set_page_config(page_title="Income Calculator (AU)", layout="wide")
_ensure_state()

# Sidebar unchanged (as instructed)
with st.sidebar:
    st.subheader("Scenarios")

    with st.form("add_scenario_form", clear_on_submit=True):
        new_name = st.text_input("Scenario name", value="", placeholder="e.g., Baseline", key="new_scenario_name")
        submitted = st.form_submit_button("Add scenario", use_container_width=True)
        if submitted:
            name = (new_name or "").strip()
            if not name:
                st.warning("Enter a scenario name.")
            else:
                st.session_state.scenarios[name] = _snapshot()
                st.session_state.active_scenario = name
                st.rerun()

    if st.session_state.scenarios:
        st.markdown("**Your scenarios**")
        for name in sorted(st.session_state.scenarios.keys()):
            is_active = (name == st.session_state.active_scenario)

            row_l, row_r = st.columns([0.82, 0.18])
            with row_l:
                btn_type = "primary" if is_active else "secondary"
                if st.button(name, key=f"load_{name}", use_container_width=True, type=btn_type):
                    _load_snapshot(st.session_state.scenarios[name])
                    st.session_state.active_scenario = name
                    st.rerun()

            with row_r:
                if st.button("✕", key=f"del_{name}", use_container_width=True):
                    if st.session_state.active_scenario == name:
                        st.session_state.active_scenario = None
                    del st.session_state.scenarios[name]
                    st.session_state.scenarios = st.session_state.scenarios
                    st.rerun()

        st.divider()
        if st.session_state.active_scenario:
            if st.button("Save current over active scenario", use_container_width=True):
                st.session_state.scenarios[st.session_state.active_scenario] = _snapshot()
                st.success("Saved")

# Tabs
tab_inputs, tab_calc, tab_household = st.tabs(["Inputs", "Income calculator", "Household dashboard"])

# Inputs tab unchanged
with tab_inputs:
    st.title("Inputs")
    # (entire Inputs content unchanged)

# Income calculator tab unchanged except tax total + label change
with tab_calc:
    # ... existing logic remains identical up to tax totals ...

    # Total tax EXCLUDES super tax (as requested)
    pa_total_tax = pa_income_tax + pa_medicare + pa_div293
    pb_total_tax = (pb_income_tax + pb_medicare + pb_div293) if is_couple else 0.0

    # Label change only
    ("Division 293", _fmt_money(pa_div293))

# Household dashboard tab (moved content only)
with tab_household:
    st.markdown("## Household summary")

    _render_metric_card(
        "Household",
        [
            ("Total salary", _fmt_money(household_total_salary)),
            ("Gross investment income ($/year)", _fmt_money(splits["gross_total"])),
            ("Net investment income ($/year)", _fmt_money(splits["net_taxable_total"])),
            ("Total taxable income (approx)", _fmt_money(household_taxable_income)),
            ("Total super contributions", _fmt_money(household_super_total)),
        ],
        "#FFF7E6",
    )

    _render_metric_card(
        "Definitions used in this app",
        [
            ("Earned income", "Base salary + remote uplift"),
            ("Taxable income (approx)", "Total salary plus net taxable investment position by owner allocation"),
            ("Earned income after tax (before expenses)", "Not shown here (use Tax sections above)"),
            ("Negative gearing benefit", "Tax reduction from allowable investment losses used to reduce taxable income"),
            ("Investment losses visibility", "Shows investment income and net taxable investment position by owner allocation"),
        ],
        "#F7F0FF",
    )
