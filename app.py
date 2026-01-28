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


# -----------------------------
# UI helpers
# -----------------------------
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

# Tabs
tab_inputs, tab_calc, tab_household = st.tabs(
    ["Inputs", "Income calculator", "Household dashboard"]
)

# -----------------------------
# Income calculator tab
# -----------------------------
with tab_calc:
    BG_INDIVIDUAL = "#F2F9F1"
    BG_HOUSEHOLD = "#FFF7E6"
    BG_INVEST = "#F7F0FF"

    st.markdown("## Income calculator")

    hh = st.session_state.household
    is_couple = bool(hh.get("is_couple", True))
    dependant_children = int(hh.get("dependant_children", 0))

    pa = st.session_state.person_a
    pb = st.session_state.person_b

    # -----------------------------
    # Tax engine
    # -----------------------------
    def calc_income_tax_resident_annual(taxable_income: float) -> float:
        x = max(0.0, float(taxable_income))
        if x <= 18200:
            return 0.0
        elif x <= 45000:
            return (x - 18200) * 0.16
        elif x <= 135000:
            return (45000 - 18200) * 0.16 + (x - 45000) * 0.30
        elif x <= 190000:
            return (
                (45000 - 18200) * 0.16
                + (135000 - 45000) * 0.30
                + (x - 135000) * 0.37
            )
        else:
            return (
                (45000 - 18200) * 0.16
                + (135000 - 45000) * 0.30
                + (190000 - 135000) * 0.37
                + (x - 190000) * 0.45
            )

    pa_income_tax = calc_income_tax_resident_annual(0.0)
    pb_income_tax = calc_income_tax_resident_annual(0.0)

    pa_total_tax = pa_income_tax
    pb_total_tax = pb_income_tax

    colA, colB = st.columns(2)

    with colA:
        st.markdown("### Person A")
        with st.expander(f"Tax  **{_fmt_money(pa_total_tax)}**"):
            _render_section_rows(
                [
                    ("Income tax", _fmt_money(pa_income_tax)),
                    ("Division 293", "$0"),
                    ("Medicare", "$0"),
                    ("Negative gearing benefit", "$0"),
                ]
            )

    with colB:
        if is_couple:
            st.markdown("### Person B")
            with st.expander(f"Tax  **{_fmt_money(pb_total_tax)}**"):
                _render_section_rows(
                    [
                        ("Income tax", _fmt_money(pb_income_tax)),
                        ("Division 293", "$0"),
                        ("Medicare", "$0"),
                        ("Negative gearing benefit", "$0"),
                    ]
                )


# -----------------------------
# Household dashboard tab
# -----------------------------
with tab_household:
    BG_HOUSEHOLD = "#FFF7E6"
    BG_INVEST = "#F7F0FF"

    _render_metric_card(
        "Household",
        [
            ("Total salary", "$0"),
            ("Gross investment income ($/year)", "$0"),
            ("Net investment income ($/year)", "$0"),
            ("Total taxable income (approx)", "$0"),
            ("Total super contributions", "$0"),
        ],
        BG_HOUSEHOLD,
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
        BG_INVEST,
    )
