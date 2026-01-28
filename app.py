# app.py
# Inputs page ONLY — clean minimal inputs for FY2025–26 onwards.
# Tax brackets / Medicare / MLS / Div 293 rules will be implemented in backend later
# using official ATO material (no user-entered tax settings UI).

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


def calc_sg_annual(
    base_salary_annual: float,
    salary_includes_sg: bool,
    uplift_annual: float,
    uplift_sg_applies: bool,
) -> float:
    """
    Inputs-only SG estimate:
    - OTE assumed = base salary (and optionally uplift).
    - If salary includes SG (package), we back out OTE: OTE ≈ package / (1 + SG_RATE).
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

        # Row 1: Salary + includes SG toggle
        r1c1, r1c2 = st.columns([1.3, 1.0])
        with r1c1:
            p["base_salary_annual"] = money_input(
                "Base salary (annual, $)",
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

        # Row 2: uplift % on right, weeks next to it, uplift metric on left
        uplift_annual = calc_uplift_annual(p["base_salary_annual"], p["uplift_pct"], p["weeks_away"])
        r2c1, r2c2, r2c3 = st.columns([1.2, 1.0, 1.0])
        with r2c1:
            st.metric("Uplift (annual)", f"${uplift_annual:,.0f}")
        with r2c2:
            p["weeks_away"] = int_input(
                "Weeks working away",
                key=f"{person_key}_weeks_away",
                value=int(p.get("weeks_away", 0)),
                min_value=0,
                max_value=52,
            )
        with r2c3:
            p["uplift_pct"] = pct_input(
                "Remote uplift (%)",
                key=f"{person_key}_uplift_pct",
                value=float(p.get("uplift_pct", 0.0)),
                max_value=200.0,
            )

        # Row 3: SG + toggle
        sg_annual = calc_sg_annual(
            base_salary_annual=p["base_salary_annual"],
            salary_includes_sg=bool(p.get("salary_includes_sg", False)),
            uplift_annual=uplift_annual,
            uplift_sg_applies=bool(p.get("uplift_sg_applies", False)),
        )

        r3c1, r3c2, r3c3 = st.columns([1.0, 1.0, 1.0])
        with r3c1:
            st.metric("SG (12%, annual)", f"${sg_annual:,.0f}")
        with r3c2:
            p["uplift_sg_applies"] = st.toggle(
                "SG applies to uplift",
                value=bool(p.get("uplift_sg_applies", False)),
                key=f"{person_key}_uplift_sg",
            )
        with r3c3:
            st.write("")

        # Row 4: Concessional + RFB
        r4c1, r4c2 = st.columns([1.0, 1.0])
        with r4c1:
            p["extra_concessional_annual"] = money_input(
                "Extra concessional contributions (annual, $)",
                key=f"{person_key}_extra_concessional",
                value=p.get("extra_concessional_annual", 0.0),
                step=500.0,
            )
        with r4c2:
            p["reportable_fringe_benefits_annual"] = money_input(
                "Reportable fringe benefits (annual, $)",
                key=f"{person_key}_rfb",
                value=p.get("reportable_fringe_benefits_annual", 0.0),
                step=500.0,
            )

    st.session_state[person_key] = p


# -----------------------------
# App
# -----------------------------
st.set_page_config(page_title="Income Calculator (AU) — Inputs", layout="wide")
_ensure_state()

# Sidebar: scenarios (highlight active, delete with x)
with st.sidebar:
    st.subheader("Scenarios")

    # Use a form so we can clear the input cleanly (avoids Streamlit session_state widget mutation errors)
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
                    st.rerun()

        st.divider()
        if st.session_state.active_scenario:
            if st.button("Save current over active scenario", use_container_width=True):
                st.session_state.scenarios[st.session_state.active_scenario] = _snapshot()
                st.success("Saved")

# Main page
st.title("Inputs")

# Household
with st.expander("Household", expanded=True):
    c1, c2, c3 = st.columns([1.0, 1.1, 1.2])

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
        st.session_state.household["dependant_children"] = int_input(
            "Dependent children",
            key="dependant_children",
            value=int(st.session_state.household.get("dependant_children", 0)),
            min_value=0,
            max_value=10,
        )

    with c3:
        st.session_state.household["is_couple"] = st.toggle(
            "Couple",
            value=bool(st.session_state.household.get("is_couple", True)),
            key="household_is_couple",
        )
        if bool(st.session_state.household["is_couple"]):
            st.session_state.household["private_hospital_cover_couple"] = st.toggle(
                "Private hospital cover (couple)",
                value=bool(st.session_state.household.get("private_hospital_cover_couple", False)),
                key="private_hospital_cover_couple",
            )
        else:
            st.session_state.household["private_hospital_cover_couple"] = False

is_couple = bool(st.session_state.household.get("is_couple", True))

# Income (collapsible)
with st.expander("Income", expanded=True):
    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        render_person_block("person_a", "Person A")

    with col_right:
        if is_couple:
            render_person_block("person_b", "Person B")
        else:
            st.info("Couple is OFF — Person B hidden.")

# Investments
with st.expander("Investments", expanded=True):
    # Use a form so the investment name clears cleanly without mutating widget session state post-creation
    with st.form("add_investment_form", clear_on_submit=True):
        add1, add2, add3 = st.columns([1.2, 1.8, 0.8])
        with add1:
            new_type = st.selectbox(
                "Type",
                ["Investment property", "Shares/ETFs", "Cash/Term deposit", "Other"],
                key="new_inv_type",
            )
        with add2:
            new_inv_name = st.text_input("Name", value="", placeholder="e.g., IP - Parramatta", key="new_inv_name")
        with add3:
            add_submitted = st.form_submit_button("Add", use_container_width=True)

        if add_submitted:
            inv_id = str(uuid.uuid4())[:8]
            inv = {
                "id": inv_id,  # internal only
                "type": new_type,
                "name": (new_inv_name or "").strip() if (new_inv_name or "").strip() else f"{new_type}",
                "ownership_a_pct": 50.0 if is_couple else 100.0,
                "gross_income_annual": 0.0,
                "interest_deductible_annual": 0.0,
                "other_deductible_annual": 0.0,
                "rent_per_week": 0.0,
                "vacancy_weeks": 0,
            }
            st.session_state.investments.append(inv)
            st.rerun()

    if not st.session_state.investments:
        st.caption("No investments added.")
    else:
        for idx, inv in enumerate(list(st.session_state.investments)):
            inv_key = f"inv_{inv['id']}"

            with st.container(border=True):
                top1, top2, top3, top4 = st.columns([1.8, 1.2, 1.0, 0.7])
                with top1:
                    inv["name"] = st.text_input("Name", value=inv.get("name", ""), key=f"{inv_key}_name")
                with top2:
                    types = ["Investment property", "Shares/ETFs", "Cash/Term deposit", "Other"]
                    inv["type"] = st.selectbox(
                        "Type",
                        types,
                        index=types.index(inv.get("type", "Other")),
                        key=f"{inv_key}_type",
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
                                key=f"{inv_key}_own",
                            )
                        )
                    else:
                        inv["ownership_a_pct"] = 100.0
                        st.metric("Ownership", "100% A")
                with top4:
                    if st.button("Remove", key=f"{inv_key}_remove", use_container_width=True):
                        st.session_state.investments = [
                            x for x in st.session_state.investments if x.get("id") != inv.get("id")
                        ]
                        st.rerun()

                if inv["type"] == "Investment property":
                    r1, r2, r3, r4 = st.columns([1.0, 1.0, 1.0, 1.0])
                    with r1:
                        inv["rent_per_week"] = money_input(
                            "Rent ($/week)",
                            key=f"{inv_key}_rent",
                            value=float(inv.get("rent_per_week", 0.0)),
                            step=10.0,
                        )
                    with r2:
                        inv["vacancy_weeks"] = int_input(
                            "Vacancy (weeks)",
                            key=f"{inv_key}_vac",
                            value=int(inv.get("vacancy_weeks", 0)),
                            min_value=0,
                            max_value=52,
                        )
                    with r3:
                        inv["interest_deductible_annual"] = money_input(
                            "Interest (annual, $)",
                            key=f"{inv_key}_int",
                            value=float(inv.get("interest_deductible_annual", 0.0)),
                            step=200.0,
                        )
                    with r4:
                        inv["other_deductible_annual"] = money_input(
                            "Other deductible (annual, $)",
                            key=f"{inv_key}_other",
                            value=float(inv.get("other_deductible_annual", 0.0)),
                            step=200.0,
                        )

                    weeks_rented = max(0, 52 - int(inv["vacancy_weeks"]))
                    inv["gross_income_annual"] = float(inv["rent_per_week"]) * float(weeks_rented)

                elif inv["type"] == "Cash/Term deposit":
                    r1, r2 = st.columns([1.0, 1.0])
                    with r1:
                        inv["gross_income_annual"] = money_input(
                            "Interest income (annual, $)",
                            key=f"{inv_key}_gross",
                            value=float(inv.get("gross_income_annual", 0.0)),
                            step=100.0,
                        )
                    with r2:
                        inv["interest_deductible_annual"] = 0.0
                        inv["other_deductible_annual"] = 0.0
                        st.write("")

                else:
                    r1, r2, r3 = st.columns([1.2, 1.0, 1.0])
                    with r1:
                        inv["gross_income_annual"] = money_input(
                            "Gross income (annual, $)",
                            key=f"{inv_key}_gross",
                            value=float(inv.get("gross_income_annual", 0.0)),
                            step=200.0,
                        )
                    with r2:
                        inv["interest_deductible_annual"] = money_input(
                            "Deductible interest (annual, $)",
                            key=f"{inv_key}_int2",
                            value=float(inv.get("interest_deductible_annual", 0.0)),
                            step=200.0,
                        )
                    with r3:
                        inv["other_deductible_annual"] = money_input(
                            "Other deductible (annual, $)",
                            key=f"{inv_key}_other2",
                            value=float(inv.get("other_deductible_annual", 0.0)),
                            step=200.0,
                        )

            st.session_state.investments[idx] = inv


with st.expander("Export / troubleshooting", expanded=False):
    st.write("Shows the current inputs payload (useful for troubleshooting or sharing exact inputs).")
    st.json(_snapshot())
