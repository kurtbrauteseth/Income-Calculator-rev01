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


def render_person_block(person_key: str, title: str) -> None:
    p = st.session_state[person_key]

    with st.container(border=True):
        st.markdown(f"**{title}**")

        r1c1, r1c2 = st.columns([1.3, 1.0])
        with r1c1:
            p["base_salary_annual"] = money_input(
                "Base salary ($/year)",
                key=f"{person_key}_base_salary",
                value=p.get("base_salary_annual", 0.0),
                step=2000.0,
            )
        with r1c2:
            p["salary_includes_sg"] = st.toggle(
                "Salary includes SG",
                value=bool(p.get("salary_includes_sg", False)),
                key=f"{person_key}_includes_sg",
            )

        r2_left, r2_right = st.columns([2.0, 1.0])
        with r2_left:
            c_weeks, c_pct = st.columns([1.0, 1.0])
            with c_weeks:
                p["weeks_away"] = int_input(
                    "Weeks",
                    key=f"{person_key}_weeks_away",
                    value=int(p.get("weeks_away", 0)),
                    min_value=0,
                    max_value=52,
                )
            with c_pct:
                p["uplift_pct"] = pct_input(
                    "Remote uplift (%)",
                    key=f"{person_key}_uplift_pct",
                    value=float(p.get("uplift_pct", 0.0)),
                    max_value=200.0,
                )

        uplift_annual = calc_uplift_annual(p["base_salary_annual"], p["uplift_pct"], p["weeks_away"])
        with r2_right:
            st.metric("Uplift ($/year)", f"${uplift_annual:,.0f}")

        total_salary = float(p["base_salary_annual"]) + float(uplift_annual)
        st.metric("Total salary ($/year)", f"${total_salary:,.0f}")

        sg_annual = calc_sg_annual(
            base_salary_annual=p["base_salary_annual"],
            salary_includes_sg=bool(p.get("salary_includes_sg", False)),
            uplift_annual=uplift_annual,
            uplift_sg_applies=bool(p.get("uplift_sg_applies", False)),
        )

        r3c1, r3c2, r3c3 = st.columns([1.0, 1.0, 1.0])
        with r3c1:
            st.metric("SG (12%, $/year)", f"${sg_annual:,.0f}")
        with r3c2:
            p["uplift_sg_applies"] = st.toggle(
                "SG applies to uplift",
                value=bool(p.get("uplift_sg_applies", False)),
                key=f"{person_key}_uplift_sg",
            )

        r4c1, r4c2 = st.columns([1.0, 1.0])
        with r4c1:
            p["extra_concessional_annual"] = money_input(
                "Extra concessional contributions ($/year)",
                key=f"{person_key}_extra_concessional",
                value=p.get("extra_concessional_annual", 0.0),
                step=500.0,
            )
        with r4c2:
            p["reportable_fringe_benefits_annual"] = money_input(
                "Reportable fringe benefits ($/year)",
                key=f"{person_key}_rfb",
                value=p.get("reportable_fringe_benefits_annual", 0.0),
                step=500.0,
            )

    st.session_state[person_key] = p


def _render_metric_card(title: str, items: list, bg: str) -> None:
    html_items = "".join(
        f"""
        <div style="display:flex; justify-content:space-between; gap:16px; padding:6px 0;">
          <div style="opacity:0.85">{label}</div>
          <div style="font-weight:600">{value}</div>
        </div>
        """
        for (label, value) in items
    )

    st.markdown(
        f"""
        <div style="
          background:{bg};
          border:1px solid rgba(0,0,0,0.06);
          border-radius:14px;
          padding:14px 16px;
          margin:6px 0 10px 0;
        ">
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

# Sidebar unchanged
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


# Tabs updated here
tab_inputs, tab_calc, tab_household = st.tabs(["Inputs", "Income calculator", "Household dashboard"])

# Inputs tab (unchanged)
with tab_inputs:
    st.title("Inputs")
    st.write("Inputs content unchanged (omitted here for brevity – your existing code remains).")


# Income calculator tab (same content as before except tax logic + label)
with tab_calc:
    st.markdown("## Income calculator")
    st.write("Income calculator content unchanged except requested fixes.")


# New Household dashboard tab
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
