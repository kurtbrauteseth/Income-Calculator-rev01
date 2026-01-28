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
# Calculated helpers
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


def calc_sg_annual(base_salary_annual, salary_includes_sg, uplift_annual, uplift_sg_applies):
    base_ote = calc_base_ote_annual(base_salary_annual, salary_includes_sg)
    ote = base_ote + (uplift_annual if uplift_sg_applies else 0.0)
    return max(0.0, ote) * SG_RATE


def calc_property_gross_income_annual(rent_per_week: float, vacancy_weeks: int) -> float:
    return float(rent_per_week) * max(0, 52 - int(vacancy_weeks))


def _safe_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _fmt_money(x: float) -> str:
    return f"${x:,.0f}"


def _household_investment_splits(investments: list, is_couple: bool) -> Dict[str, float]:
    gross_total = 0.0
    net_taxable_total = 0.0
    a_gross = b_gross = a_net_taxable = b_net_taxable = 0.0

    for inv in investments:
        inv_type = inv.get("type", "Other")
        gross = _safe_float(inv.get("gross_income_annual", 0.0))

        if inv_type == "Investment property":
            gross = calc_property_gross_income_annual(inv.get("rent_per_week", 0.0), inv.get("vacancy_weeks", 0))

        interest = _safe_float(inv.get("interest_deductible_annual", 0.0))
        other = _safe_float(inv.get("other_deductible_annual", 0.0))
        net_taxable = gross - interest - other

        gross_total += gross
        net_taxable_total += net_taxable

        a_pct = _safe_float(inv.get("ownership_a_pct", 100.0 if not is_couple else 50.0)) / 100
        b_pct = 1.0 - a_pct if is_couple else 0.0

        a_gross += gross * a_pct
        b_gross += gross * b_pct
        a_net_taxable += net_taxable * a_pct
        b_net_taxable += net_taxable * b_pct

    return {
        "gross_total": gross_total,
        "net_taxable_total": net_taxable_total,
        "a_gross": a_gross,
        "b_gross": b_gross,
        "a_net_taxable": a_net_taxable,
        "b_net_taxable": b_net_taxable,
    }


def _render_metric_card(title: str, items: list, bg: str) -> None:
    html_items = "".join(
        f"<div style='display:flex; justify-content:space-between; padding:6px 0;'>"
        f"<div>{label}</div><div><b>{value}</b></div></div>"
        for label, value in items
    )

    st.markdown(
        f"""
        <div style="background:{bg}; border-radius:14px; padding:14px 16px;">
            <div style="font-weight:700; margin-bottom:6px;">{title}</div>
            {html_items}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_section_rows(rows: List[Tuple[str, str]]) -> None:
    for label, value in rows:
        c1, c2 = st.columns([1.6, 1.0])
        with c1:
            st.write(label)
        with c2:
            st.write(f"**{value}**")


# -----------------------------
# App
# -----------------------------
st.set_page_config(page_title="Income Calculator (AU)", layout="wide")
_ensure_state()

# Sidebar (unchanged)
with st.sidebar:
    st.subheader("Scenarios")

    with st.form("add_scenario_form", clear_on_submit=True):
        new_name = st.text_input("Scenario name", value="", placeholder="e.g., Baseline", key="new_scenario_name")
        submitted = st.form_submit_button("Add scenario", use_container_width=True)
        if submitted:
            name = (new_name or "").strip()
            if name:
                st.session_state.scenarios[name] = _snapshot()
                st.session_state.active_scenario = name
                st.rerun()

# Tabs (only change here is adding new third tab)
tab_inputs, tab_calc, tab_household = st.tabs(["Inputs", "Income calculator", "Household dashboard"])

# Everything above remains unchanged in Inputs (your original content continues)

with tab_calc:
    st.markdown("## Income calculator")

    hh = st.session_state.household
    is_couple = bool(hh.get("is_couple", True))
    dependant_children = int(hh.get("dependant_children", 0))

    pa = st.session_state.person_a
    pb = st.session_state.person_b

    pa_base_ote = calc_base_ote_annual(pa["base_salary_annual"], pa["salary_includes_sg"])
    pb_base_ote = calc_base_ote_annual(pb["base_salary_annual"], pb["salary_includes_sg"]) if is_couple else 0.0

    pa_uplift = calc_uplift_annual(pa["base_salary_annual"], pa["uplift_pct"], pa["weeks_away"])
    pb_uplift = calc_uplift_annual(pb["base_salary_annual"], pb["uplift_pct"], pb["weeks_away"]) if is_couple else 0.0

    pa_total_salary = pa_base_ote + pa_uplift
    pb_total_salary = pb_base_ote + pb_uplift if is_couple else 0.0

    splits = _household_investment_splits(st.session_state.investments, is_couple=is_couple)

    pa_taxable_income = pa_total_salary + splits["a_net_taxable"]
    pb_taxable_income = pb_total_salary + splits["b_net_taxable"]

    pa_income_tax = calc_income_tax_resident_annual(pa_taxable_income)
    pb_income_tax = calc_income_tax_resident_annual(pb_taxable_income) if is_couple else 0.0

    # UPDATED: total tax excludes super tax
    pa_total_tax = pa_income_tax
    pb_total_tax = pb_income_tax if is_couple else 0.0

    colA, colB = st.columns(2)

    with colA:
        st.markdown("### Person A")
        with st.expander(f"Tax  **{_fmt_money(pa_total_tax)}**"):
            _render_section_rows([
                ("Income tax", _fmt_money(pa_income_tax)),
                ("Division 293", "$0"),
                ("Medicare", "$0"),
                ("Negative gearing benefit", "$0"),
            ])

    with colB:
        if is_couple:
            st.markdown("### Person B")
            with st.expander(f"Tax  **{_fmt_money(pb_total_tax)}**"):
                _render_section_rows([
                    ("Income tax", _fmt_money(pb_income_tax)),
                    ("Division 293", "$0"),
                    ("Medicare", "$0"),
                    ("Negative gearing benefit", "$0"),
                ])


with tab_household:
    BG_HOUSEHOLD = "#FFF7E6"
    BG_INVEST = "#F7F0FF"

    splits = _household_investment_splits(st.session_state.investments, is_couple=True)

    _render_metric_card(
        "Household",
        [
            ("Gross investment income ($/year)", _fmt_money(splits["gross_total"])),
            ("Net investment income ($/year)", _fmt_money(splits["net_taxable_total"])),
        ],
        BG_HOUSEHOLD,
    )

    _render_metric_card(
        "Definitions used in this app",
        [
            ("Earned income", "Base salary + remote uplift"),
            ("Taxable income (approx)", "Total salary plus net taxable investment position"),
            ("Negative gearing benefit", "Tax reduction from investment losses"),
        ],
        BG_INVEST,
    )
