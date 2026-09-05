from app.solver.metrics import demand_covered, measure, weekly_totals


def test_total_tonnage_is_conserved_across_weeks(problem):
    chosen = tuple(problem.by_plot[ref][0] for ref in problem.plot_refs)
    expected = sum(c.tonnes_mid for c in chosen)

    assert sum(weekly_totals(chosen, problem, worst=False)) == round(expected, 6)


def test_worst_case_never_undercuts_the_expected_peak(problem):
    chosen = tuple(problem.by_plot[ref][0] for ref in problem.plot_refs)

    expected = max(weekly_totals(chosen, problem, worst=False))
    worst = max(weekly_totals(chosen, problem, worst=True))

    assert worst >= expected


def test_gross_value_is_null_when_any_chosen_candidate_lacks_a_price(problem):
    """Nilai sebagian terbaca sebagai nilai total. Kontrak melarangnya."""
    chosen = list(problem.by_plot[problem.plot_refs[0]][:1])
    chosen.append(problem.by_plot[problem.plot_refs[1]][0].model_copy(
        update={"price_per_kg": None}
    ))

    assert measure(tuple(chosen), problem, worst=False).gross_value is None


def test_gross_value_is_a_number_when_every_candidate_is_priced(problem):
    chosen = tuple(problem.by_plot[ref][0] for ref in problem.plot_refs)

    assert measure(chosen, problem, worst=False).gross_value > 0


def test_supply_beyond_demand_is_not_counted_as_coverage(problem):
    chosen = tuple(problem.by_plot[ref][0] for ref in problem.plot_refs)
    total_demand = sum(problem.demand_kg.values())

    assert demand_covered(chosen, problem) <= total_demand


def test_an_empty_plan_measures_as_nothing(problem):
    empty = measure((), problem, worst=False)

    assert (empty.peak, empty.total_tonnes, empty.coverage_kg) == (0.0, 0.0, 0)
