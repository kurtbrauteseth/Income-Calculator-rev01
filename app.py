# [UNCHANGED CONTENT ABOVE — identical to your pasted file]


# Top tabs (Inputs first)
tab_inputs, tab_calc, tab_household = st.tabs(["Inputs", "Income calculator", "Household dashboard"])

# -----------------------
# Inputs tab (UNCHANGED)
# -----------------------
with tab_inputs:
    st.title("Inputs")
    ...
    # EVERYTHING EXACTLY AS YOUR FILE ABOVE
    ...


# -----------------------
# Income calculator tab
# -----------------------
with tab_calc:
    # Pastel section colors (light)
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
    # Tax engine (UNCHANGED)
    # -----------------------------
    def calc_income_tax_resident_annual(taxable_income: float) -> float:
        ...

    def calc_medicare_levy_amount_from_income(...):
        ...

    def calc_medicare_levy_split(...):
        ...

    def calc_div293_tax(...):
        ...

    # -----------------------------
    # Earnings + splits (UNCHANGED)
    # -----------------------------
    pa_base_ote = ...
    pb_base_ote = ...
    ...
    splits = ...

    # -----------------------------
    # Super contributions (UNCHANGED)
    # -----------------------------
    pa_super_tax = ...
    pb_super_tax = ...

    # -----------------------------
    # Tax components (UNCHANGED)
    # -----------------------------
    pa_income_tax, pb_income_tax, pa_medicare, pb_medicare, pa_div293, pb_div293 = _compute_tax_components(...)

    # ✅ FIXED: Total tax EXCLUDES super tax
    pa_total_tax = pa_income_tax + pa_medicare + pa_div293
    pb_total_tax = (pb_income_tax + pb_medicare + pb_div293) if is_couple else 0.0

    # -----------------------------
    # Negative gearing (UNCHANGED)
    # -----------------------------
    pa_ng_benefit = ...
    pb_ng_benefit = ...

    colA, colB = st.columns(2, gap="large")

    with colA:
        ...
        with st.expander(f"Tax  **{_fmt_money(pa_total_tax)}**", expanded=False):
            _render_section_rows(
                [
                    ("Income tax", _fmt_money(pa_income_tax)),
                    ("Division 293", _fmt_money(pa_div293)),   # ✅ label fixed
                    ("Medicare", _fmt_money(pa_medicare)),
                    ("Negative gearing benefit", _fmt_money(pa_ng_benefit)),
                ]
            )

    with colB:
        if is_couple:
            ...
            with st.expander(f"Tax  **{_fmt_money(pb_total_tax)}**", expanded=False):
                _render_section_rows(
                    [
                        ("Income tax", _fmt_money(pb_income_tax)),
                        ("Division 293", _fmt_money(pb_div293)),  # ✅ label fixed
                        ("Medicare", _fmt_money(pb_medicare)),
                        ("Negative gearing benefit", _fmt_money(pb_ng_benefit)),
                    ]
                )


# -----------------------
# NEW: Household dashboard tab
# -----------------------
with tab_household:
    BG_HOUSEHOLD = "#FFF7E6"
    BG_INVEST = "#F7F0FF"

    # These variables already computed above
    # household_total_salary
    # household_taxable_income
    # household_super_total
    # splits

    with st.container():
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
