# app.py
# Inputs page ONLY (no tax calculations). Minimal inputs to later compute:
# - Individual taxable income (before/after negative gearing)
# - Super (SG + contributions tax + optional extra concessional)
# - Income tax + Medicare levy (family-aware) + Div 293 (given user-supplied FY26+ parameters)
# - Household totals, gross investment income, negative gearing benefit (tax effect)

import copy
import uuid
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st


# -----------------------------
# Helpers
# -----------------------------
def _money_input(label: str, key: str, value: float = 0.0, help_: Optional[str] = None) -> float:
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


def _pct_input(label: str, key: str, value: float = 50.0, help_: Optional[str] = None) -> float:
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


def _ensure_state() -> None:
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
        st.session_state.investments = []

    if "tax_params" not in st.session_state:
        # User-supplied FY26+ parameters; NO guessing/hardcoding.
        st.session_state.tax_params = {
            "income_tax_brackets": [
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
                "contributions_tax_rate": 0.15,  # user-editable
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
        return pd.DataFrame(
            columns=[
                "Type",
                "Name",
                "Gross income (annual)",
                "Deductible interest (annual)",
                "Other deductions (annual)",
                "Net taxable (annual)",
                "Allocated to A (gross)",
                "Allocated to B (gross)",
                "Allocated to A (net taxable)",
                "Allocated to B (net taxable)",
                "A ownership %",
            ]
        )

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
            st.success("Saved scenario: {}".format(scenario_name))

    with mid:
        scenario_choices = sorted(list(st.session_state.scenarios.keys()))
        selected = st.selectbox("Load scenario", options=["(select)"] + scenario_choices, index=0)
        if st.button("Load selected", use_container_width=True, disabled=(selected == "(select)")):
            _load_snapshot(st.session_state.scenarios[selected])
            st.success("Loaded scenario: {}".format(selected))
            st.rerun()

    with right:
        delete_sel = st.selectbox(
            "Delete scenario",
            options=["(select)"] + scenario_choices,
            index=0,
            key="delete_scenario_sel",
        )
        if st.button("Delete", use_container_width=True, disabled=(delete_sel == "(select)")):
            del st.session_state.scenarios[delete_sel]
            st.warning("Deleted scenario: {}".format(delete_sel))
            st.rerun()

st.divider()

# -----------------------------
# Household / Year
# -----------------------------
with st.expander("Household", expanded=True):
    col1, col2, col3 = st.columns([1.2, 1.2, 1.2])

    with col1:
        year_opts = ["2025–26", "2026–27", "2027–28", "2028–29", "2029–30"]
        current = st.session_state.household.get("tax_year_label", "2025–26")
        if current not in year_opts:
            current = "2025–26"
        st.session_state.household["tax_year_label"] = st.selectbox(
            "Tax year label (FY)",
            options=year_opts,
            index=year_opts.index(current),
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
def render_person_inputs(person_key: str, title: str) -> None:
    p = st.session_state[person_key]

    with st.expander(title, expanded=True):
        c1, c2, c3 = st.columns([1.2, 1.2, 1.2])

        with c1:
            p["name"] = st.text_input("Label", value=p.get("name", title), key="{}_name".format(person_key))
            p["resident_for_tax"] = st.toggle(
                "Australian resident for tax purposes",
                value=bool(p.get("resident_for_tax", True)),
                key="{}_resident".format(person_key),
            )

        with c2:
            p["base_salary_annual"] = float(
                st.number_input(
                    "Base salary (annual, $)",
                    min_value=0.0,
                    value=float(p.get("base_salary_annual", 0.0)),
                    step=1000.0,
                    format="%.2f",
                    key="{}_base_salary".format(person_key),
                    help="Annual gross base salary. If you want weekly/fortnightly later, we can add that.",
                )
            )
            p["salary_includes_sg"] = st.toggle(
                "Salary figure includes SG",
                value=bool(p.get("salary_includes_sg", False)),
                key="{}_salary_includes_sg".format(person_key),
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
                    key="{}_remote_uplift".format(person_key),
                    help="For v1 inputs: enter the final taxable annual amount. If you want rule-based calculation, we'll add inputs once you provide the formula.",
                )
            )
            p["remote_uplift_sg_applies"] = st.toggle(
                "SG applies to uplift",
                value=bool(p.get("remote_uplift_sg_applies", False)),
                key="{}_remote_uplift_sg".format(person_key),
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
                    key="{}_extra_concessional".format(person_key),
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
                    key="{}_rfb".format(person_key),
                    help="Only needed if your Div 293 income definition includes it. Set to 0 if none.",
                )
            )

        with c6:
            p["reportable_employer_super_annual"] = float(
                st.number_input(
                    "Reportable employer super (RESC) excluding SG (annual $)",
                    min_value=0.0,
                    value=float(p.get("reportable_employer_super_annual", 0.0)),
                    step=500.0,
                    format="%.2f",
                    key="{}_resc".format(person_key),
                    help="Only needed if your Div 293 definition includes it. Set to 0 if none.",
                )
            )

    st.session_state[person_key] = p


colA, colB = st.columns(2)
with colA:
    render_person_inputs("person_a", "Person A — income & super inputs")

with colB:
    if is_couple:
        render_person_inputs("person_b", "Person B — income & super inputs")
    else:
        st.info("Couple mode is OFF — Person B inputs hidden. Investments will allocate 100% to Person A.")

st.divider()

# -----------------------------
# Investments
# -----------------------------
with st.expander("Investments (for investment income + negative gearing)", expanded=True):
    st.caption(
        "Minimal fields per investment: gross income + deductible interest + other deductions + ownership split. "
        "This is enough to later compute taxable income before/after negative gearing, and gross investment income."
    )

    add_col1, add_col2, add_col3 = st.columns([1.3, 1.3, 1.4])
    with add_col1:
        new_type = st.selectbox(
            "Add investment type",
            ["Investment property", "Shares/ETFs", "Cash/Term deposit", "Other"],
            key="new_inv_type",
        )
    with add_col2:
        new_name = st.text_input("Name", value="", placeholder="e.g., IP - Parramatta", key="new_inv_name")
    with add_col3:
        if st.button("Add investment", use_container_width=True):
            inv_id = str(uuid.uuid4())[:8]
            base = {
                "id": inv_id,
                "type": new_type,
                "name": new_name.strip() if new_name.strip() else "{} ({})".format(new_type, inv_id),
                "gross_income_annual": 0.0,
                "interest_deductible_annual": 0.0,
                "other_deductible_annual": 0.0,
                "ownership_a_pct": 50.0 if is_couple else 100.0,
            }

            if new_type == "Investment property":
                base.update({"rent_per_week": 0.0, "vacancy_weeks": 0, "other_income_annual": 0.0})
            elif new_type == "Shares/ETFs":
                base.update({"dividends_annual": 0.0, "other_income_annual": 0.0})
            elif new_type == "Cash/Term deposit":
                base.update({"interest_income_annual": 0.0})

            st.session_state.investments.append(base)
            st.success("Added: {}".format(base["name"]))
            st.rerun()

    if len(st.session_state.investments) == 0:
        st.warning("No investments added yet.")
    else:
        for idx, inv in enumerate(list(st.session_state.investments)):
            inv_key = "inv_{}".format(inv["id"])

            with st.container():
                st.markdown("---")
                top1, top2, top3, top4 = st.columns([2.2, 1.2, 1.1, 1.1])

                with top1:
                    inv["name"] = st.text_input(
                        "Investment name",
                        value=inv.get("name", ""),
                        key="{}_name".format(inv_key),
                    )
                    st.caption("Type: **{}**  |  ID: `{}`".format(inv.get("type", "Other"), inv.get("id", "")))

                with top2:
                    if is_couple:
                        inv["ownership_a_pct"] = _pct_input(
                            "Person A ownership %",
                            key="{}_own_a".format(inv_key),
                            value=float(inv.get("ownership_a_pct", 50.0)),
                            help_="Person B ownership is the remainder (100% - A%).",
                        )
                    else:
                        inv["ownership_a_pct"] = 100.0
                        st.metric("Ownership", "100% to Person A")

                with top3:
                    if st.button("Remove", key="{}_remove".format(inv_key), use_container_width=True):
                        st.session_state.investments = [
                            x for x in st.session_state.investments if x.get("id") != inv.get("id")
                        ]
                        st.warning("Removed: {}".format(inv.get("name", "(investment)")))
                        st.rerun()

                with top4:
                    if is_couple:
                        a = float(inv.get("ownership_a_pct", 50.0))
                        if a < 0.0 or a > 100.0:
                            st.error("Ownership % must be 0–100")
                        else:
                            st.metric("Person B ownership %", "{:.0f}%".format(100.0 - a))

                inv_type = inv.get("type", "Other")

                if inv_type == "Investment property":
                    c1, c2, c3 = st.columns([1.2, 1.0, 1.2])
                    with c1:
                        inv["rent_per_week"] = float(
                            st.number_input(
                                "Rent ($/week)",
                                min_value=0.0,
                                value=float(inv.get("rent_per_week", 0.0)),
                                step=10.0,
                                format="%.2f",
                                key="{}_rent_w".format(inv_key),
                            )
                        )
                    with c2:
                        inv["vacancy_weeks"] = int(
                            st.number_input(
                                "Vacancy (weeks/year)",
                                min_value=0,
                                max_value=52,
                                value=int(inv.get("vacancy_weeks", 0)),
                                step=1,
                                key="{}_vac_w".format(inv_key),
                            )
                        )
                    with c3:
                        inv["other_income_annual"] = float(
                            st.number_input(
                                "Other property income (annual $)",
                                min_value=0.0,
                                value=float(inv.get("other_income_annual", 0.0)),
                                step=100.0,
                                format="%.2f",
                                key="{}_other_income".format(inv_key),
                                help="Optional: e.g., laundry, parking, insurance recovery. Set 0 if none.",
                            )
                        )

                    d1, d2 = st.columns(2)
                    with d1:
                        inv["interest_deductible_annual"] = float(
                            st.number_input(
                                "Interest (annual $)",
                                min_value=0.0,
                                value=float(inv.get("interest_deductible_annual", 0.0)),
                                step=100.0,
                                format="%.2f",
                                key="{}_int".format(inv_key),
                            )
                        )
                    with d2:
                        inv["other_deductible_annual"] = float(
                            st.number_input(
                                "Other deductible expenses (annual $)",
                                min_value=0.0,
                                value=float(inv.get("other_deductible_annual", 0.0)),
                                step=100.0,
                                format="%.2f",
                                key="{}_other_ded".format(inv_key),
                                help="All other deductible holding costs excluding interest. Depreciation is not included unless you later ask for it.",
                            )
                        )

                    gross_rent = inv["rent_per_week"] * float(max(0, 52 - inv["vacancy_weeks"]))
                    inv["gross_income_annual"] = float(gross_rent + float(inv.get("other_income_annual", 0.0)))
                    st.caption("Derived gross property income (annual): ${:,.2f}".format(inv["gross_income_annual"]))

                elif inv_type == "Shares/ETFs":
                    c1, c2 = st.columns(2)
                    with c1:
                        inv["dividends_annual"] = _money_input(
                            "Dividends (annual $)",
                            key="{}_div".format(inv_key),
                            value=float(inv.get("dividends_annual", 0.0)),
                        )
                    with c2:
                        inv["other_income_annual"] = _money_input(
                            "Other taxable income (annual $)",
                            key="{}_oth_inc".format(inv_key),
                            value=float(inv.get("other_income_annual", 0.0)),
                            help_="Optional: distributions, interest, etc. Franking credits not modelled in v1 inputs unless you ask.",
                        )

                    d1, d2 = st.columns(2)
                    with d1:
                        inv["interest_deductible_annual"] = _money_input(
                            "Deductible interest (annual $)",
                            key="{}_sh_int".format(inv_key),
                            value=float(inv.get("interest_deductible_annual", 0.0)),
                            help_="E.g., margin loan interest. Set 0 if none.",
                        )
                    with d2:
                        inv["other_deductible_annual"] = _money_input(
                            "Other deductible costs (annual $)",
                            key="{}_sh_oth_ded".format(inv_key),
                            value=float(inv.get("other_deductible_annual", 0.0)),
                            help_="E.g., investment expenses. CGT not modelled in v1 inputs unless you ask.",
                        )

                    inv["gross_income_annual"] = float(inv.get("dividends_annual", 0.0) + inv.get("other_income_annual", 0.0))

                elif inv_type == "Cash/Term deposit":
                    inv["interest_income_annual"] = _money_input(
                        "Interest income (annual $)",
                        key="{}_cash_int".format(inv_key),
                        value=float(inv.get("interest_income_annual", 0.0)),
                    )
                    inv["gross_income_annual"] = float(inv.get("interest_income_annual", 0.0))
                    inv["interest_deductible_annual"] = 0.0
                    inv["other_deductible_annual"] = 0.0

                else:
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        inv["gross_income_annual"] = _money_input(
                            "Gross taxable investment income (annual $)",
                            key="{}_gross".format(inv_key),
                            value=float(inv.get("gross_income_annual", 0.0)),
                            help_="Enter the taxable gross income for this investment.",
                        )
                    with c2:
                        inv["interest_deductible_annual"] = _money_input(
                            "Deductible interest (annual $)",
                            key="{}_o_int".format(inv_key),
                            value=float(inv.get("interest_deductible_annual", 0.0)),
                        )
                    with c3:
                        inv["other_deductible_annual"] = _money_input(
                            "Other deductible expenses (annual $)",
                            key="{}_o_ded".format(inv_key),
                            value=float(inv.get("other_deductible_annual", 0.0)),
                        )

                st.session_state.investments[idx] = inv

        st.subheader("Investment summary (input-derived)")
        df = _investment_allocations(is_couple=is_couple)
        st.dataframe(df, use_container_width=True, hide_index=True)

        gross_household = float(df["Gross income (annual)"].sum()) if not df.empty else 0.0
        net_taxable_household = float(df["Net taxable (annual)"].sum()) if not df.empty else 0.0
        st.metric("Household gross investment income (annual)", "${:,.2f}".format(gross_household))
        st.metric("Household net taxable investment amount (annual)", "${:,.2f}".format(net_taxable_household))

st.divider()

# -----------------------------
# Tax settings (must be user supplied)
# -----------------------------
with st.expander("Tax settings (FY2025–26 onwards) — REQUIRED for accuracy", expanded=False):
    st.warning("No FY26+ tax rates/thresholds are assumed. Enter the exact values you want used for the selected tax year.")

    tp = st.session_state.tax_params

    st.markdown("### Income tax (resident) brackets")
    st.caption(
        "Enter resident tax brackets for the selected year. "
        "Use **from/to** thresholds and the marginal **rate**. "
        "Base tax can be entered explicitly (recommended for accuracy) or left 0 for now."
    )

    brackets_df = pd.DataFrame(tp.get("income_tax_brackets", []))
    if brackets_df.empty:
        brackets_df = pd.DataFrame([{"from": 0.0, "to": 0.0, "rate": 0.0, "base_tax": 0.0}])

    edited = st.data_editor(
        brackets_df,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "from": st.column_config.NumberColumn("From ($)", min_value=0.0, format="%.2f", step=1000.0),
            "to": st.column_config.NumberColumn("To ($)", min_value=0.0, format="%.2f", step=1000.0),
            "rate": st.column_config.NumberColumn("Rate (e.g., 0.30)", min_value=0.0, max_value=1.0, format="%.4f", step=0.01),
            "base_tax": st.column_config.NumberColumn("Base tax at 'From' ($)", min_value=0.0, format="%.2f", step=100.0),
        },
        hide_index=True,
    )
    tp["income_tax_brackets"] = edited.to_dict(orient="records")

    st.markdown("### Medicare levy thresholds (family-aware)")
    m = tp["medicare"]
    c1, c2, c3 = st.columns(3)
    with c1:
        m["single_lower"] = _money_input("Single lower threshold ($)", "med_single_lower", m.get("single_lower", 0.0))
        m["single_upper"] = _money_input("Single upper threshold ($)", "med_single_upper", m.get("single_upper", 0.0))
    with c2:
        m["family_lower_base"] = _money_input("Family lower base ($)", "med_family_lower", m.get("family_lower_base", 0.0))
        m["family_upper_base"] = _money_input("Family upper base ($)", "med_family_upper", m.get("family_upper_base", 0.0))
    with c3:
        m["family_lower_per_child"] = _money_input("Family lower per child ($)", "med_family_lower_child", m.get("family_lower_per_child", 0.0))
        m["family_upper_per_child"] = _money_input("Family upper per child ($)", "med_family_upper_child", m.get("family_upper_per_child", 0.0))
    tp["medicare"] = m

    st.markdown("### Super settings")
    s = tp["super"]
    c1, c2, c3 = st.columns(3)
    with c1:
        s["sg_rate"] = float(
            st.number_input(
                "SG rate (e.g., 0.12)",
                min_value=0.0,
                max_value=0.30,
                value=float(s.get("sg_rate", 0.0)),
                step=0.005,
                format="%.4f",
                key="sg_rate",
            )
        )
    with c2:
        s["concessional_cap"] = _money_input("Concessional contributions cap ($)", "concessional_cap", s.get("concessional_cap", 0.0))
    with c3:
        s["contributions_tax_rate"] = float(
            st.number_input(
                "Contributions tax rate in fund (e.g., 0.15)",
                min_value=0.0,
                max_value=0.30,
                value=float(s.get("contributions_tax_rate", 0.15)),
                step=0.01,
                format="%.4f",
                key="contrib_tax_rate",
            )
        )
    tp["super"] = s

    st.markdown("### Division 293 settings")
    d = tp["div293"]
    c1, c2, c3 = st.columns(3)
    with c1:
        d["enabled"] = st.toggle("Enable Div 293", value=bool(d.get("enabled", True)), key="div293_enabled")
    with c2:
        d["threshold"] = _money_input("Div 293 threshold ($)", "div293_threshold", d.get("threshold", 0.0))
    with c3:
        d["rate"] = float(
            st.number_input(
                "Div 293 rate (e.g., 0.15)",
                min_value=0.0,
                max_value=0.30,
                value=float(d.get("rate", 0.0)),
                step=0.01,
                format="%.4f",
                key="div293_rate",
            )
        )

    st.markdown("**Div 293 income definition components (choose what you want included)**")
    comp = d["income_definition_components"]
    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        comp["include_taxable_income"] = st.checkbox("Include taxable income", value=bool(comp.get("include_taxable_income", True)))
        comp["include_net_investment_losses"] = st.checkbox("Include net investment losses", value=bool(comp.get("include_net_investment_losses", True)))
    with cc2:
        comp["include_concessional_contributions"] = st.checkbox("Include concessional contributions", value=bool(comp.get("include_concessional_contributions", True)))
        comp["include_reportable_employer_super"] = st.checkbox("Include reportable employer super (RESC)", value=bool(comp.get("include_reportable_employer_super", True)))
    with cc3:
        comp["include_reportable_fringe_benefits"] = st.checkbox("Include reportable fringe benefits", value=bool(comp.get("include_reportable_fringe_benefits", True)))

    d["income_definition_components"] = comp
    tp["div293"] = d
    st.session_state.tax_params = tp

    st.info(
        "If you want Medicare Levy Surcharge (MLS), HELP/HECS, offsets (e.g., LITO), franking credits, CGT, depreciation, "
        "or trust/company ownership — tell me and we’ll add only the necessary inputs."
    )

st.divider()

with st.expander("Readiness checklist (inputs captured for your key metrics)", expanded=True):
    st.write("✅ **Per individual:** base salary, remote uplift, investment allocations, extra concessional, RFB/RESC (Div293 support)")
    st.write("✅ **Per individual taxes later:** income tax brackets + Medicare thresholds + Div293 parameters supplied by you")
    st.write("✅ **Household:** couple toggle + children + gross investment income + ownership splits")
    st.write("✅ **Negative gearing:** deductible interest + other deductions per investment + ownership splits")
    st.caption("Next: once you review this Inputs page, we’ll lock assumptions/logic and then implement the Results page + calculations.")

with st.expander("Debug: current input payload (optional)", expanded=False):
    st.json(_snapshot_current_inputs())
