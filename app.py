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
    """
    Returns an estimated OTE base salary (exclusive of SG) from the base input.
    If the base salary value is a "package" (includes SG), we back out OTE:
      OTE ≈ package / (1 + SG_RATE)
    """
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
    """
    Inputs-only SG estimate:
    - OTE assumed = base salary (and optionally uplift).
    - If salary includes SG (package), we back out OTE: OTE ≈ package / (1 + SG_RATE).
    """
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
    """
    Returns key aggregates needed for displaying key metrics on the Income calculator tab.
    Note: This is NOT tax logic; it just aggregates input values.
    """
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

        # For property, gross is derived from rent & vacancy (kept consistent with Inputs page)
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

        # Row 1: Salary + includes SG toggle (consistent unit labels)
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

        # Row 2: uplift inputs on the left, calculated uplift on the right
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

        # Row 2.5: show total salary (base + uplift)
        total_salary = float(p["base_salary_annual"]) + float(uplift_annual)
        st.metric("Total salary ($/year)", f"${total_salary:,.0f}")

        # Row 3: SG + toggle
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
        with r3c3:
            st.write("")

        # Row 4: Concessional + RFB (consistent unit labels)
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

# Sidebar: scenarios (highlight active, delete with x) — DO NOT CHANGE
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
                    st.rerun()

        st.divider()
        if st.session_state.active_scenario:
            if st.button("Save current over active scenario", use_container_width=True):
                st.session_state.scenarios[st.session_state.active_scenario] = _snapshot()
                st.success("Saved")

# Top tabs (Inputs first)
tab_inputs, tab_calc = st.tabs(["Inputs", "Income calculator"])

with tab_inputs:
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
                                "Interest ($/year)",
                                key=f"{inv_key}_int",
                                value=float(inv.get("interest_deductible_annual", 0.0)),
                                step=200.0,
                            )
                        with r4:
                            inv["other_deductible_annual"] = money_input(
                                "Other deductible ($/year)",
                                key=f"{inv_key}_other",
                                value=float(inv.get("other_deductible_annual", 0.0)),
                                step=200.0,
                            )

                        inv["gross_income_annual"] = calc_property_gross_income_annual(
                            rent_per_week=_safe_float(inv.get("rent_per_week", 0.0)),
                            vacancy_weeks=int(inv.get("vacancy_weeks", 0)),
                        )

                    elif inv["type"] == "Cash/Term deposit":
                        r1, r2 = st.columns([1.0, 1.0])
                        with r1:
                            inv["gross_income_annual"] = money_input(
                                "Interest income ($/year)",
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
                                "Gross income ($/year)",
                                key=f"{inv_key}_gross",
                                value=float(inv.get("gross_income_annual", 0.0)),
                                step=200.0,
                            )
                        with r2:
                            inv["interest_deductible_annual"] = money_input(
                                "Deductible interest ($/year)",
                                key=f"{inv_key}_int2",
                                value=float(inv.get("interest_deductible_annual", 0.0)),
                                step=200.0,
                            )
                        with r3:
                            inv["other_deductible_annual"] = money_input(
                                "Other deductible ($/year)",
                                key=f"{inv_key}_other2",
                                value=float(inv.get("other_deductible_annual", 0.0)),
                                step=200.0,
                            )

                st.session_state.investments[idx] = inv

    with st.expander("Export / troubleshooting", expanded=False):
        st.write("Shows the current inputs payload (useful for troubleshooting or sharing exact inputs).")
        st.json(_snapshot())

with tab_calc:
    # Pastel section colors (light)
    BG_INDIVIDUAL = "#F2F9F1"
    BG_HOUSEHOLD = "#FFF7E6"
    BG_INVEST = "#F7F0FF"

    st.markdown("## Income calculator")

    hh = st.session_state.household
    is_couple = bool(hh.get("is_couple", True))

    pa = st.session_state.person_a
    pb = st.session_state.person_b

    # Earned income (taxable approximation): OTE base (ex SG) + uplift
    pa_base_ote = calc_base_ote_annual(
        _safe_float(pa.get("base_salary_annual", 0.0)),
        bool(pa.get("salary_includes_sg", False)),
    )
    pb_base_ote = (
        calc_base_ote_annual(
            _safe_float(pb.get("base_salary_annual", 0.0)),
            bool(pb.get("salary_includes_sg", False)),
        )
        if is_couple
        else 0.0
    )

    pa_uplift = calc_uplift_annual(pa["base_salary_annual"], pa["uplift_pct"], pa["weeks_away"])
    pb_uplift = calc_uplift_annual(pb["base_salary_annual"], pb["uplift_pct"], pb["weeks_away"]) if is_couple else 0.0

    pa_earned_income = pa_base_ote + pa_uplift
    pb_earned_income = (pb_base_ote + pb_uplift) if is_couple else 0.0

    splits = _household_investment_splits(st.session_state.investments, is_couple=is_couple)

    # Build "taxable income" from currently available inputs only:
    # taxable_income ~= earned_income (OTE + uplift) + net_taxable_investment_allocated
    pa_taxable_income = pa_earned_income + splits["a_net_taxable"]
    pb_taxable_income = pb_earned_income + splits["b_net_taxable"]

    # Placeholder tax/super tax values (to be computed once tax engine is added)
    ZERO = 0.0

    colA, colB = st.columns(2, gap="large")

    with colA:
        with st.container(border=True):
            st.markdown("### Person A")

            with st.expander(f"Taxable income  \u00a0\u00a0 **{_fmt_money(pa_taxable_income)}**", expanded=True):
                rows = []
                if bool(pa.get("salary_includes_sg", False)):
                    rows.append(("Salary package (incl SG)", _fmt_money(_safe_float(pa.get("base_salary_annual", 0.0)))))
                    rows.append(("Base salary (OTE)", _fmt_money(pa_base_ote)))
                else:
                    rows.append(("Base salary (OTE)", _fmt_money(pa_base_ote)))

                rows.extend(
                    [
                        ("Uplift", _fmt_money(pa_uplift)),
                        ("Earned income (OTE + uplift)", _fmt_money(pa_earned_income)),
                        ("Investment income", _fmt_money(splits["a_gross"])),
                        ("Net investment income", _fmt_money(splits["a_net_taxable"])),
                    ]
                )
                _render_section_rows(rows)

            pa_sg = calc_sg_annual(
                pa["base_salary_annual"],
                bool(pa["salary_includes_sg"]),
                pa_uplift,
                bool(pa["uplift_sg_applies"]),
            )
            pa_super_total = pa_sg + _safe_float(pa.get("extra_concessional_annual", 0.0))

            with st.expander(f"Superannuation  \u00a0\u00a0 **{_fmt_money(pa_super_total)}**", expanded=False):
                _render_section_rows(
                    [
                        ("Super Guarantee", _fmt_money(pa_sg)),
                        ("Tax (taken from super)", _fmt_money(ZERO)),
                        ("Concessional", _fmt_money(_safe_float(pa.get("extra_concessional_annual", 0.0)))),
                        ("Non-concessional", _fmt_money(ZERO)),
                    ]
                )

            with st.expander(f"Tax  \u00a0\u00a0 **{_fmt_money(ZERO)}**", expanded=False):
                _render_section_rows(
                    [
                        ("Income tax", _fmt_money(ZERO)),
                        ("Division 293 (additional tax on super)", _fmt_money(ZERO)),
                        ("Medicare", _fmt_money(ZERO)),
                    ]
                )

    with colB:
        if is_couple:
            with st.container(border=True):
                st.markdown("### Person B")

                with st.expander(f"Taxable income  \u00a0\u00a0 **{_fmt_money(pb_taxable_income)}**", expanded=True):
                    rows = []
                    if bool(pb.get("salary_includes_sg", False)):
                        rows.append(("Salary package (incl SG)", _fmt_money(_safe_float(pb.get("base_salary_annual", 0.0)))))
                        rows.append(("Base salary (OTE)", _fmt_money(pb_base_ote)))
                    else:
                        rows.append(("Base salary (OTE)", _fmt_money(pb_base_ote)))

                    rows.extend(
                        [
                            ("Uplift", _fmt_money(pb_uplift)),
                            ("Earned income (OTE + uplift)", _fmt_money(pb_earned_income)),
                            ("Investment income", _fmt_money(splits["b_gross"])),
                            ("Net investment income", _fmt_money(splits["b_net_taxable"])),
                        ]
                    )
                    _render_section_rows(rows)

                pb_sg = calc_sg_annual(
                    pb["base_salary_annual"],
                    bool(pb["salary_includes_sg"]),
                    pb_uplift,
                    bool(pb["uplift_sg_applies"]),
                )
                pb_super_total = pb_sg + _safe_float(pb.get("extra_concessional_annual", 0.0))

                with st.expander(f"Superannuation  \u00a0\u00a0 **{_fmt_money(pb_super_total)}**", expanded=False):
                    _render_section_rows(
                        [
                            ("Super Guarantee", _fmt_money(pb_sg)),
                            ("Tax (taken from super)", _fmt_money(ZERO)),
                            ("Concessional", _fmt_money(_safe_float(pb.get("extra_concessional_annual", 0.0)))),
                            ("Non-concessional", _fmt_money(ZERO)),
                        ]
                    )

                with st.expander(f"Tax  \u00a0\u00a0 **{_fmt_money(ZERO)}**", expanded=False):
                    _render_section_rows(
                        [
                            ("Income tax", _fmt_money(ZERO)),
                            ("Division 293 (additional tax on super)", _fmt_money(ZERO)),
                            ("Medicare", _fmt_money(ZERO)),
                        ]
                    )
        else:
            with st.container(border=True):
                st.markdown("### Person B")
                st.write("Not enabled (single mode).")

    # Household key metrics (inputs-only, consistent with taxable income definitions above)
    household_earned_income = pa_earned_income + (pb_earned_income if is_couple else 0.0)
    household_taxable_income = pa_taxable_income + (pb_taxable_income if is_couple else 0.0)
    household_super_total = pa_super_total + (pb_super_total if is_couple else 0.0)

    with st.container():
        _render_metric_card(
            "Household",
            [
                ("Earned income (OTE + uplift)", _fmt_money(household_earned_income)),
                ("Gross investment income ($/year)", _fmt_money(splits["gross_total"])),
                ("Net investment income ($/year)", _fmt_money(splits["net_taxable_total"])),
                ("Total taxable income (approx)", _fmt_money(household_taxable_income)),
                ("Total super contributions", _fmt_money(household_super_total)),
            ],
            BG_HOUSEHOLD,
        )

    # Keep definitions
    _render_metric_card(
        "Definitions used in this app",
        [
            ("Earned income", "OTE base salary (ex SG) + remote uplift"),
            ("Taxable income (approx)", "Earned income plus net taxable investment position by owner allocation"),
            ("Earned income after tax (before expenses)", "Not calculated yet (tax engine pending)"),
            ("Negative gearing benefit", "Not calculated yet (tax engine pending)"),
            ("Investment losses visibility", "Shows investment income and net taxable investment position by owner allocation"),
        ],
        BG_INVEST,
    )
