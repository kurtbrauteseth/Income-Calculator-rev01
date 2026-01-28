# app.py
# Inputs page ONLY (no tax calculations). Minimal inputs to later compute:
# - Individual taxable income (before/after negative gearing)
# - Super (SG + contributions tax + optional extra concessional)
# - Income tax + Medicare levy (family-aware) + Div 293 (given user-supplied FY26+ parameters)
# - Household totals, gross investment income, negative gearing benefit (tax effect)

import copy
import uuid
from typing import Any, Dict, List

import pandas as pd
import streamlit as st


# -----------------------------
# Helpers
# -----------------------------
def _money_input(label: str, key: str, value: float = 0.0, help_: str | None = None) -> float:
    return float(
        st.number_input(
            label,
            min_value=0.0,
            value=float(value),
            step=100.0,
            format="%.2f",
            key=key,
            help=help_,
        )
    )


def _pct_input(label: str, key: str, value: float = 50.0, help_: str | None = None) -> float:
    return float(
        st.number_input(
            label,
            min_value=0.0,
            max_value=100.0,
            value=float(value),
            step=1.0,
            format="%.0f",
            key=key,
            help=help_,
        )
    )


def _ensure_state():
    if "household" not in st.session_state:
        st.session_state.household = {
            "tax_year_label": "2025–26",
            "is_couple": True,
            "dependant_children": 0,
        }

    if "person_a" not in st.session_state:
        st.session_state.person_a = {
            "name": "Person A",
            "resident_for_tax": True,
            "base_salary_annual": 0.0,
            "salary_includes_sg": False,
            "remote_uplift_taxable_annual": 0.0,
            "remote_uplift_sg_applies": False,
            "extra_concessional_annual": 0.0,
            "reportable_fringe_benefits_annual": 0.0,
            "reportable_employer_super_annual": 0.0,  # RESC other than SG
        }

    if "person_b" not in st.session_state:
        st.session_state.person_b = {
            "name": "Person B",
            "resident_for_tax": True,
            "base_salary_annual": 0.0,
            "salary_includes_sg": False,
            "remote_uplift_taxable_annual": 0.0,
            "remote_uplift_sg_applies": False,
            "extra_concessional_annual": 0.0,
            "reportable_fringe_benefits_annual": 0.0,
            "reportable_employer_super_annual": 0.0,  # RESC other than SG
        }

    if "investments" not in st.session_state:
        # List[dict] of investment items
        st.session_state.investments = []

    if "tax_params" not in st.session_state:
        # User-supplied FY26+ parameters; NO guessing/hardcoding.
        st.session_state.tax_params = {
            "income_tax_brackets": [
                # Minimal editable template; user must fill correct FY year values.
                # threshold_from, threshold_to, rate, base_tax (optional; can be derived, but kept explicit to avoid assumptions)
                {"from": 0.0, "to": 0.0, "rate": 0.0, "base_tax": 0.0},
            ],
            "medicare": {
                "single_lower": 0.0,
                "single_upper": 0.0,
                "family_lower_base": 0.0,
                "family_upper_base": 0.0,
                "family_lower_per_child": 0.0,
                "family_upper_per_child": 0.0,
            },
            "super": {
                "sg_rate": 0.0,  # e.g., 0.12 for 12%
                "concessional_cap": 0.0,
                "contributions_tax_rate": 0.15,  # typical; user can change
            },
            "div293": {
                "enabled": True,
                "threshold": 0.0,
                "rate": 0.0,
                "income_definition_components": {
                    "include_taxable_income": True,
                    "include_reportable_fringe_benefits": True,
                    "include_net_investment_losses": True,
                    "include_concessional_contributions": True,
                    "include_reportable_employer_super": True,  # RESC
                },
            },
        }

    if "scenarios" not in st.session_state:
        st.session_state.scenarios = {}  # name -> payload dict


def _snapshot_current_inputs() -> Dict[str, Any]:
    return {
        "household": copy.deepcopy(st.session_state.household),
        "person_a": copy.deepcopy(st.session_state.person_a),
        "person_b": copy.deepcopy(st.session_state.person_b),
        "investments": copy.deepcopy(st.session_state.investments),
        "tax_params": copy.deepcopy(st.session_state.tax_params),
    }


def _load_snapshot(payload: Dict[str, Any]) -> None:
    st.session_state.household = copy.deepcopy(payload.get("household", st.session_state.household))
    st.session_state.person_a = copy.deepcopy(payload.get("person_a", st.session_state.person_a))
    st.session_state.person_b = copy.deepcopy(payload.get("person_b", st.session_state.person_b))
    st.session_state.investments = copy.deepcopy(payload.get("investments", st.session_state.investments))
    st.session_state.tax_params = copy.deepcopy(payload.get("tax_params", st.session_state.tax_params))


def _investment_allocations(is_couple: bool) -> pd.DataFrame:
    """
    Purely input-derived summary (no tax rules). Used to validate ownership splits and totals.
    """
    rows = []
    for inv in st.session_state.investments:
        inv_type = inv.get("type", "Other")
        name = inv.get("name", "Investment")
        gross = float(inv.get("gross_income_annual", 0.0))
        interest = float(inv.get("interest_deductible_annual", 0.0))
        other_ded = float(inv.get("other_deductible_annual", 0.0))
        net_taxable = gross - interest - other_ded

        if is_couple:
            a_pct = float(inv.get("ownership_a_pct", 50.0)) / 100.0
            b_pct = 1.0 - a_pct
        else:
            a_pct = 1.0
            b_pct = 0.0

        rows.append(
            {
                "Type": inv_type,
                "Name": name,
                "Gross income (annual)": gross,
                "Deductible interest (annual)": interest,
                "Other deductions (annual)": other_ded,
                "Net taxable (annual)": net_taxable,
                "Allocated to A (gross)": gross * a_pct,
                "Allocated to B (gross)": gross * b_pct,
                "Allocated to A (net taxable)": net_taxable * a_pct,
                "Allocated to B (net taxable)": net_taxable * b_pct,
                "A ownership %": a_pct * 100.0,
            }
        )

    if not rows:
        return pd.DataFrame(columns=[
            "Type", "Name",
            "Gross income (annual)", "Deductible interest (annual)", "Other deductions (annual)", "Net taxable (annual)",
            "Allocated to A (gross)", "Allocated to B (gross)",
            "Allocated to A (net taxable)", "Allocated to B (net taxable)",
            "A ownership %"
        ])

    return pd.DataFrame(rows)


# -----------------------------
# App
# -----------------------------
st.set_page_config(page_title="Family Tax + Negative Gearing (AU) — Inputs", layout="wide")
_ensure_state()

st.title("Inputs — AU Family Tax + Investments (FY2025–26 onwards)")
st.caption(
    "This page collects the *minimum* inputs needed to later compute your requested key metrics. "
    "No tax rates/thresholds are assumed — you must enter FY26+ parameters in **Tax settings**."
)

with st.expander("Scenario management", expanded=True):
    left, mid, right = st.columns([2, 2, 3])

    with left:
        scenario_name = st.text_input("Scenario name", value="Baseline", key="scenario_name_input")
        if st.button("Save / overwrite scenario", use_container_width=True):
            st.session_state.scenarios[scenario_name] = _snapshot_current_inputs()
            st.success(f"Saved scenario: {scenario_name}")

    with mid:
        scenario_choices = sorted(list(st.session_state.scenarios.keys()))
        selected = st.selectbox("Load scenario", options=["(select)"] + scenario_choices, index=0)
        if st.button("Load selected", use_container_width=True, disabled=(selected == "(select)")):
            _load_snapshot(st.session_state.scenarios[selected])
            st.success(f"Loaded scenario: {selected}")
            st.rerun()

    with right:
        delete_sel = st.selectbox("Delete scenario", options=["(select)"] + scenario_choices, index=0, key="delete_scenario_sel")
        if st.button("Delete", use_container_width=True, disabled=(delete_sel == "(select)")):
            del st.session_state.scenarios[delete_sel]
            st.warning(f"Deleted scenario: {delete_sel}")
            st.rerun()


st.divider()

# -----------------------------
# Household / Year
# -----------------------------
with st.expander("Household", expanded=True):
    col1, col2, col3 = st.columns([1.2, 1.2, 1.2])

    with col1:
        st.session_state.household["tax_year_label"] = st.selectbox(
            "Tax year label (FY)",
            options=["2025–26", "2026–27", "2027–28", "2028–29", "2029–30"],
            index=["2025–26", "2026–27", "2027–28", "2028–29", "2029–30"].index(st.session_state.household["tax_year_label"]),
            help="Label only. Actual rates/thresholds must be entered under Tax settings.",
        )

    with col2:
        st.session_state.household["is_couple"] = st.toggle(
            "Couple mode (Person A + Person B)",
            value=bool(st.session_state.household["is_couple"]),
        )

    with col3:
        st.session_state.household["dependant_children"] = int(
            st.number_input(
                "Dependent children (for Medicare family thresholds)",
                min_value=0,
                value=int(st.session_state.household["dependant_children"]),
                step=1,
            )
        )

is_couple = bool(st.session_state.household["is_couple"])

st.divider()

# -----------------------------
# People inputs
# -----------------------------
def render_person_inputs(person_key: str, title: str):
    p = st.session_state[person_key]

    with st.expander(title, expanded=True):
        c1, c2, c3 = st.columns([1.2, 1.2, 1.2])

        with c1:
            p["name"] = st.text_input("Label", value=p.get("name", title), key=f"{person_key}_name")
            p["resident_for_tax"] = st.toggle(
                "Australian resident for tax purposes",
                value=bool(p.get("resident_for_tax", True)),
                key=f"{person_key}_resident",
            )

        with c2:
            p["base_salary_annual"] = float(
                st.number_input(
                    "Base salary (annual, $)",
                    min_value=0.0,
                    value=float(p.get("base_salary_annual", 0.0)),
                    step=1000.0,
                    format="%.2f",
                    key=f"{person_key}_base_salary",
                    help="Annual gross base salary. If you want weekly/fortnightly later, we can add that.",
                )
            )
            p["salary_includes_sg"] = st.toggle(
                "Salary figure includes SG",
                value=bool(p.get("salary_includes_sg", False)),
                key=f"{person_key}_salary_includes_sg",
                help="If ON, base salary is treated as total package including SG (so SG is backed out).",
            )

        with c3:
            p["remote_uplift_taxable_annual"] = float(
                st.number_input(
                    "Remote work allowance / uplift (taxable, annual $)",
                    min_value=0.0,
                    value=float(p.get("remote_uplift_taxable_annual", 0.0)),
                    step=500.0,
                    format="%.2f",
                    key=f"{person_key}_remote_uplift",
                    help="For v1 inputs: enter the final taxable annual amount. If you want rule-based calculation, we'll add inputs once you provide the formula.",
                )
            )
            p["remote_uplift_sg_applies"] = st.toggle(
                "SG applies to uplift",
                value=bool(p.get("remote_uplift_sg_applies", False)),
                key=f"{person_key}_remote_uplift_sg",
                help="Some allowances are ordinary time earnings (OTE) and may attract SG. Choose what you want applied.",
            )

        st.markdown("**Super + Div 293 supporting inputs (minimal)**")
        c4, c5, c6 = st.columns([1.2, 1.2, 1.2])

        with c4:
            p["extra_concessional_annual"] = float(
                st.number_input(
                    "Extra concessional contributions (annual $)",
                    min_value=0.0,
                    value=float(p.get("extra_concessional_annual", 0.0)),
                    step=500.0,
                    format="%.2f",
                    key=f"{person_key}_extra_concessional",
                    help="Salary sacrifice / personal deductible concessional contributions (in addition to SG).",
                )
            )

        with c5:
            p["reportable_fringe_benefits_annual"] = float(
                st.number_input(
                    "Reportable fringe benefits (annual $)",
                    min_value=0.0,
                    value=float(p.get("reportable_fringe_benefits_annual", 0.0)),
                    step=500.0,
                    format="%.2f",
                    key=f"{person_key}_rfb",
                    help="Only needed if your Div 293 income definition includes it. Set to 0 if none.",
                )
            )

        with c6:
            p["reportable_employer_super_annual"] = float(
                st.number_input(
                    "Reportable employer super (RESC) excluding SG (annual $)",
                    min_value=0.0,
                    value=float(p.get("reportable_employer_super_annual", 0.0))_
