# app.py
# Inputs page ONLY — clean minimal inputs for FY2025–26 onwards.
# Tax brackets / Medicare / MLS / Div 293 rules will be implemented in backend later
# using official ATO sources (no user-entered tax settings UI).

import copy
import uuid
from typing import Any, Dict

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
            # Minimal MLS inputs (kept optional; can be ignored later if you decide not to model MLS)
            "has_private_hospital_cover_a": False,
            "has_private_hospital_cover_b": False,
        }

    if "person_a" not in st.session_state:
        st.session_state.person_a = {
            "name": "Person A",
            "resident_for_tax": True,
            "base_salary_annual": 0.0,
            "salary_includes_sg": False,  # advanced/optional
            "weeks_away": 0,
            "uplift_pct": 0.0,  # percent uplift
            "uplift_sg_applies": False,
            "extra_concessional_annual": 0.0,
            "reportable_fringe_benefits_annual": 0.0,
        }

    if "person_b" not in st.session_state:
        st.session_state.person_b = {
            "name": "Person B",
            "resident_for_tax": True,
            "base_salary_annual": 0.0,
            "salary_includes_sg": False,  # advanced/optional
            "weeks_away": 0,
            "uplift_pct": 0.0,
            "uplift_sg_applies": False,
            "extra_concessional_annual": 0.0,
            "reportable_fringe_benefits_annual": 0.0,
        }

    if "investments" not in st.session_state:
        st.session_state.investments = []  # list of dicts

    if "scenarios" not in st.session_state:
        st.session_state.scenarios = {}  # name -> payload


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
    # uplift_pct provided as percent (e.g., 20 = 20%)
    pct = max(0.0, uplift_pct) / 100.0
    w = min(max(int(weeks_away), 0), 52)
    return float(base_salary_annual) * pct * (w / 52.0)


def calc_sg_annual(base_salary_annual: float, salary_includes_sg: bool, uplift_annual: float, uplift_sg_applies: bool) -> float:
    """
    Inputs-only SG estimate.
    - OTE base assumed = base salary (and optionally uplift).
    - If user says salary includes SG (total package), we back out an OTE estimate:
        OTE ≈ package / (1 + SG_RATE)
      This is an assumption; you can later adjust if you prefer a different convention.
    """
    base = float(base_salary_annual)

    if salary_includes_sg and (1.0 + SG_RATE) > 0:
        base_ote = base / (1.0 + SG_RATE)
    else:
        base_ote = base

    ote = base_ote + (float(uplift_annual) if uplift_sg_applies else 0.0)
    return max(0.0, ote) * SG_RATE


# -----------------------------
# UI helpers
# -----------------------------
def money_input(label: str, key: str, value: float = 0.0, step: float = 1000.0, help_text: str | None = None) -> float:
    return float(
        st.number_input(
            label,
            min_value=0.0,
            value=float(value),
            step=float(step),
            format="%.2f",
            key=key,
            help=help_text,
        )
    )


def int_input(label: str, key: str, value: int = 0, min_value: int = 0, max_value: int = 52, help_text: str | None = None) -> int:
    return int(
        st.number_input(
            label,
            min_value=min_value,
            max_value=max_value,
            value=int(value),
            step=1,
            key=key,
            help=help_text,
        )
    )


def pct_input(label: str, key: str, value: float = 0.0, help_text: str | None = None) -> float:
    return float(
        st.number_input(
            label,
            min_value=0.0,
            max_value=300.0,
            value=float(value),
            step=1.0,
            format="%.1f",
            key=key,
            help=help_text,
        )
    )


def render_person_block(person_key: str, title: str) -> None:
    p = st.session_state[person_key]

    with st.container():
        st.subheader(title)

        # Row 1: core income
        c1, c2, c3 = st.columns([1.3, 1.0, 1.0])
        with c1:
            p["name"] = st.text_input("Label", value=p.get("name", title), key=f"{person_key}_name")
            p["base_salary_annual"] = money_input(
                "Base salary (annual, $)",
                key=f"{person_key}_base_salary",
                value=p.get("base_salary_annual", 0.0),
                step=2000.0,
            )
        with c2:
            p["weeks_away"] = int_input(
                "Weeks working away (0–52)",
                key=f"{person_key}_weeks_away",
                value=p.get("weeks_away", 0),
                min_value=0,
                max_value=52,
                help_text="Used for remote allowance calculation.",
            )
            p["uplift_pct"] = pct_input(
                "Remote allowance uplift (%)",
                key=f"{person_key}_uplift_pct",
                value=p.get("uplift_pct", 0.0),
                help_text="Percent uplift applied to base salary for weeks away.",
            )
        with c3:
            uplift_annual = calc_uplift_annual(p["base_salary_annual"], p["uplift_pct"], p["weeks_away"])
            st.metric("Derived uplift (annual)", f"${uplift_annual:,.0f}")
            p["uplift_sg_applies"] = st.toggle(
                "SG applies to uplift",
                value=bool(p.get("uplift_sg_applies", False)),
                key=f"{person_key}_uplift_sg",
                help="If ON, uplift is treated as OTE for SG purposes.",
            )

        # Row 2: super + div293 supporting inputs
        st.markdown("**Super & Div 293 supporting inputs**")
        c4, c5, c6 = st.columns([1.0, 1.0, 1.0])
        with c4:
            sg_annual = calc_sg_annual(
                base_salary_annual=p["base_salary_annual"],
                salary_includes_sg=bool(p.get("salary_includes_sg", False)),
                uplift_annual=uplift_annual,
                uplift_sg_applies=bool(p.get("uplift_sg_applies", False)),
            )
            st.metric("Super Guarantee (annual, 12%)", f"${sg_annual:,.0f}")
        with c5:
            p["extra_concessional_annual"] = money_input(
                "Extra concessional contributions (annual, $)",
                key=f"{person_key}_extra_concessional",
                value=p.get("extra_concessional_annual", 0.0),
                step=500.0,
                help_text="Salary sacrifice / personal deductible concessional contributions (in addition to SG).",
            )
        with c6:
            p["reportable_fringe_benefits_annual"] = money_input(
                "Reportable fringe benefits (annual, $)",
                key=f"{person_key}_rfb",
                value=p.get("reportable_fringe_benefits_annual", 0.0),
                step=500.0,
                help_text="Used for Div 293 income definition (if applicable).",
            )

        # Advanced (kept minimal, hidden by default)
        with st.expander("Advanced (rarely needed)", expanded=False):
            c7, c8 = st.columns([1.0, 1.0])
            with c7:
                p["resident_for_tax"] = st.toggle(
                    "Australian resident for tax purposes",
                    value=bool(p.get("resident_for_tax", True)),
                    key=f"{person_key}_resident",
                )
            with c8:
                p["salary_includes_sg"] = st.toggle(
                    "Salary figure includes SG (total package)",
                    value=bool(p.get("salary_includes_sg", False)),
                    key=f"{person_key}_includes_sg",
                    help="If ON, SG is backed out from the base salary to estimate OTE for SG.",
                )

        # Save back
        st.session_state[person_key] = p


# -----------------------------
# App
# -----------------------------
st.set_page_config(page_title="Income Calculator (AU) — Inputs", layout="wide")
_ensure_state()

# Sidebar: scenario management
with st.sidebar:
    st.title("Scenarios")

    scenario_name = st.text_input("Scenario name", value="Baseline", key="scenario_name")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if st.button("Save", use_container_width=True):
            st.session_state.scenarios[scenario_name] = _snapshot()
            st.success("Saved")

    with col_s2:
        scenario_keys = sorted(st.session_state.scenarios.keys())
        sel = st.selectbox("Load", options=["(select)"] + scenario_keys, index=0, key="scenario_load_sel")
        if st.button("Load selected", use_container_width=True, disabled=(sel == "(select)")):
            _load_snapshot(st.session_state.scenarios[sel])
            st.success("Loaded")
            st.rerun()

    if st.session_state.scenarios:
        del_sel = st.selectbox(
            "Delete",
            options=["(select)"] + sorted(st.session_state.scenarios.keys()),
            index=0,
            key="scenario_delete_sel",
        )
        if st.button("Delete selected", use_container_width=True, disabled=(del_sel == "(select)")):
            del st.session_state.scenarios[del_sel]
            st.warning("Deleted")
            st.rerun()

    st.divider()
    st.caption("Inputs only. Tax rates/thresholds will be sourced from official ATO material in backend logic.")


st.title("Inputs")
st.caption("Clean, minimal inputs required to calculate your key metrics (individual + household).")

# Household section
with st.expander("Household", expanded=True):
    c1, c2, c3, c4 = st.columns([1.0, 1.0, 1.0, 1.2])

    with c1:
        year_opts = ["2025–26", "2026–27", "2027–28", "2028–29", "2029–30"]
        current = st.session_state.household.get("tax_year_label", "2025–26")
        if current not in year_opts:
            current = "2025–26"
        st.session_state.household["tax_year_label"] = st.selectbox(
            "Tax year (FY)",
            options=year_opts,
            index=year_opts.index(current),
        )

    with c2:
        st.session_state.household["is_couple"] = st.toggle(
            "Couple mode (A + B)",
            value=bool(st.session_state.household.get("is_couple", True)),
        )

    with c3:
        st.session_state.household["dependant_children"] = int_input(
            "Dependent children",
            key="dependant_children",
            value=int(st.session_state.household.get("dependant_children", 0)),
            min_value=0,
            max_value=10,
        )

    with c4:
        # Optional MLS inputs (kept compact). If you decide later not to model MLS, we can remove these.
        st.markdown("**Private hospital cover (MLS)**")
        cc1, cc2 = st.columns(2)
        with cc1:
            st.session_state.household["has_private_hospital_cover_a"] = st.checkbox(
                "A covered",
                value=bool(st.session_state.household.get("has_private_hospital_cover_a", False)),
            )
        with cc2:
            st.session_state.household["has_private_hospital_cover_b"] = st.checkbox(
                "B covered",
                value=bool(st.session_state.household.get("has_private_hospital_cover_b", False)),
                disabled=not bool(st.session_state.household.get("is_couple", True)),
            )

is_couple = bool(st.session_state.household.get("is_couple", True))

st.divider()

# People section
st.header("People")
col_left, col_right = st.columns(2, gap="large")

with col_left:
    render_person_block("person_a", "Person A")

with col_right:
    if is_couple:
        render_person_block("person_b", "Person B")
    else:
        st.subheader("Person B")
        st.info("Couple mode is OFF — Person B inputs hidden.")

st.divider()

# Investments section
with st.expander("Investments", expanded=True):
    # Add investment row
    add1, add2, add3 = st.columns([1.2, 1.6, 1.0])
    with add1:
        new_type = st.selectbox(
            "Type",
            ["Investment property", "Shares/ETFs", "Cash/Term deposit", "Other"],
            key="new_inv_type",
        )
    with add2:
        new_name = st.text_input("Name", value="", placeholder="e.g., IP - Parramatta", key="new_inv_name")
    with add3:
        if st.button("Add", use_container_width=True):
            inv_id = str(uuid.uuid4())[:8]
            inv = {
                "id": inv_id,  # stored internally; not displayed
                "type": new_type,
                "name": new_name.strip() if new_name.strip() else f"{new_type}",
                "ownership_a_pct": 50.0 if is_couple else 100.0,
                "gross_income_annual": 0.0,
                "interest_deductible_annual": 0.0,
                "other_deductible_annual": 0.0,
                # property-specific
                "rent_per_week": 0.0,
                "vacancy_weeks": 0,
            }
            st.session_state.investments.append(inv)
            st.success("Added investment")
            st.rerun()

    if not st.session_state.investments:
        st.caption("No investments added.")
    else:
        for idx, inv in enumerate(list(st.session_state.investments)):
            with st.container():
                st.markdown("---")
                top1, top2, top3, top4 = st.columns([1.8, 1.2, 1.0, 0.7])

                with top1:
                    inv["name"] = st.text_input("Name", value=inv.get("name", ""), key=f"inv_{inv['id']}_name")

                with top2:
                    inv["type"] = st.selectbox(
                        "Type",
                        ["Investment property", "Shares/ETFs", "Cash/Term deposit", "Other"],
                        index=["Investment property", "Shares/ETFs", "Cash/Term deposit", "Other"].index(inv.get("type", "Other")),
                        key=f"inv_{inv['id']}_type",
                    )

                with top3:
                    if is_couple:
                        inv["ownership_a_pct"] = float(
                            st.number_input(
                                "A ownership (%)",
                                min_value=0.0,
                                max_value=100.0,
                                value=float(inv.get("ownership_a_pct", 50.0)),
                                step=1.0,
                                format="%.0f",
                                key=f"inv_{inv['id']}_own_a",
                            )
                        )
                    else:
                        inv["ownership_a_pct"] = 100.0
                        st.metric("Ownership", "100% A")

                with top4:
                    if st.button("Remove", key=f"inv_{inv['id']}_remove", use_container_width=True):
                        st.session_state.investments = [x for x in st.session_state.investments if x.get("id") != inv.get("id")]
                        st.rerun()

                # Inputs aligned by type
                if inv["type"] == "Investment property":
                    c1, c2, c3, c4 = st.columns([1.0, 1.0, 1.0, 1.0])
                    with c1:
                        inv["rent_per_week"] = money_input(
                            "Rent ($/week)",
                            key=f"inv_{inv['id']}_rent",
                            value=float(inv.get("rent_per_week", 0.0)),
                            step=10.0,
                        )
                    with c2:
                        inv["vacancy_weeks"] = int_input(
                            "Vacancy (weeks)",
                            key=f"inv_{inv['id']}_vac",
                            value=int(inv.get("vacancy_weeks", 0)),
                            min_value=0,
                            max_value=52,
                        )
                    with c3:
                        inv["interest_deductible_annual"] = money_input(
                            "Interest (annual, $)",
                            key=f"inv_{inv['id']}_int",
                            value=float(inv.get("interest_deductible_annual", 0.0)),
                            step=200.0,
                        )
                    with c4:
                        inv["other_deductible_annual"] = money_input(
                            "Other deductible (annual, $)",
                            key=f"inv_{inv['id']}_other_ded",
                            value=float(inv.get("other_deductible_annual", 0.0)),
                            step=200.0,
                        )

                    # derive gross income annual (inputs-only)
                    weeks_rented = max(0, 52 - int(inv["vacancy_weeks"]))
                    inv["gross_income_annual"] = float(inv["rent_per_week"]) * float(weeks_rented)

                elif inv["type"] == "Shares/ETFs":
                    c1, c2, c3 = st.columns([1.2, 1.0, 1.0])
                    with c1:
                        inv["gross_income_annual"] = money_input(
                            "Gross income (annual, $)",
                            key=f"inv_{inv['id']}_gross",
                            value=float(inv.get("gross_income_annual", 0.0)),
                            step=200.0,
                            help_text="Dividends/distributions/interest. (Franking credits & CGT can be added later if needed.)",
                        )
                    with c2:
                        inv["interest_deductible_annual"] = money_input(
                            "Deductible interest (annual, $)",
                            key=f"inv_{inv['id']}_sh_int",
                            value=float(inv.get("interest_deductible_annual", 0.0)),
                            step=200.0,
                        )
                    with c3:
                        inv["other_deductible_annual"] = money_input(
                            "Other deductible (annual, $)",
                            key=f"inv_{inv['id']}_sh_other",
                            value=float(inv.get("other_deductible_annual", 0.0)),
                            step=200.0,
                        )

                elif inv["type"] == "Cash/Term deposit":
                    c1, c2 = st.columns([1.2, 1.2])
                    with c1:
                        inv["gross_income_annual"] = money_input(
                            "Interest income (annual, $)",
                            key=f"inv_{inv['id']}_cash_int",
                            value=float(inv.get("gross_income_annual", 0.0)),
                            step=100.0,
                        )
                    with c2:
                        st.caption("No deductions captured for cash (by default).")
                        inv["interest_deductible_annual"] = 0.0
                        inv["other_deductible_annual"] = 0.0

                else:
                    c1, c2, c3 = st.columns([1.2, 1.0, 1.0])
                    with c1:
                        inv["gross_income_annual"] = money_input(
                            "Gross income (annual, $)",
                            key=f"inv_{inv['id']}_o_gross",
                            value=float(inv.get("gross_income_annual", 0.0)),
                            step=200.0,
                        )
                    with c2:
                        inv["interest_deductible_annual"] = money_input(
                            "Deductible interest (annual, $)",
                            key=f"inv_{inv['id']}_o_int",
                            value=float(inv.get("interest_deductible_annual", 0.0)),
                            step=200.0,
                        )
                    with c3:
                        inv["other_deductible_annual"] = money_input(
                            "Other deductible (annual, $)",
                            key=f"inv_{inv['id']}_o_other",
                            value=float(inv.get("other_deductible_annual", 0.0)),
                            step=200.0,
                        )

                st.session_state.investments[idx] = inv

# Optional debug (kept hidden)
with st.expander("Debug (optional)", expanded=False):
    st.json(_snapshot())
