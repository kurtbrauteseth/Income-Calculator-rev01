# (Your imports and all code above remain EXACTLY the same)
# Nothing changed until the tabs declaration.

# Top tabs (Inputs first)
tab_inputs, tab_calc, tab_household = st.tabs(["Inputs", "Income calculator", "Household dashboard"])

with tab_inputs:
    st.title("Inputs")
    # ... ENTIRE INPUTS SECTION UNCHANGED ...


with tab_calc:
    # EVERYTHING inside this tab remains identical EXCEPT for:
    # - total tax formula
    # - Division 293 label
    # - Household cards removed

    # --- unchanged code above ---

    # Total tax (UPDATED: excludes super tax now)
    pa_total_tax = pa_income_tax + pa_medicare + pa_div293
    pb_total_tax = (pb_income_tax + pb_medicare + pb_div293) if is_couple else 0.0

    # --- unchanged code continues ---

            with st.expander(f"Tax  \u00a0\u00a0 **{_fmt_money(pa_total_tax)}**", expanded=False):
                _render_section_rows(
                    [
                        ("Income tax", _fmt_money(pa_income_tax)),
                        ("Division 293", _fmt_money(pa_div293)),
                        ("Medicare", _fmt_money(pa_medicare)),
                        ("Negative gearing benefit", _fmt_money(pa_ng_benefit)),
                    ]
                )

    # same change for Person B

# -----------------------------
# NEW TAB (Household dashboard)
# -----------------------------
with tab_household:
    BG_HOUSEHOLD = "#FFF7E6"
    BG_INVEST = "#F7F0FF"

    hh = st.session_state.household
    is_couple = bool(hh.get("is_couple", True))

    pa = st.session_state.person_a
    pb = st.session_state.person_b

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

    pa_total_salary = pa_base_ote + pa_uplift
    pb_total_salary = (pb_base_ote + pb_uplift) if is_couple else 0.0

    splits = _household_investment_splits(st.session_state.investments, is_couple=is_couple)

    household_total_salary = pa_total_salary + (pb_total_salary if is_couple else 0.0)
    household_taxable_income = (
        pa_total_salary + splits["a_net_taxable"]
        + (pb_total_salary + splits["b_net_taxable"] if is_couple else 0.0)
    )
    household_super_total = (
        _safe_float(pa.get("extra_concessional_annual", 0.0))
        + _safe_float(pb.get("extra_concessional_annual", 0.0))
    )

    _render_metric_card(
        "Household",
        [
            ("Total salary", _fmt_money(household_total_salary)),
            ("Gross investment income ($/year)", _fmt_money(splits["gross_total"])),
            ("Net investment income ($/year)", _fmt_money(splits["net_taxable_total"])),
            ("Total taxable income (approx)", _fmt_money(household_taxable_income)),
            ("Total super contributions", _fmt_money(household_super_total)),
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
