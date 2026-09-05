import pytest

from app.agent.facts import Facts, format_number
from app.agent.guard import numbers_are_grounded, rejection_reason, ungrounded_numbers
from app.agent.providers import template_narrative

FACTS = Facts(
    objective="aman", plots=5, varieties=3,
    first_harvest_week="2027-01-04", last_harvest_week="2027-02-15",
    harvest_weeks=7, peak_p50=9.1, peak_p90=11.8, capacity=12.5,
    total_tonnes=31.4, demand_covered_kg=12000, seed=1,
)


def test_prose_without_numbers_passes():
    assert numbers_are_grounded("Rencana ini menyebar panen ke beberapa minggu.", frozenset())


def test_a_computed_number_passes():
    assert numbers_are_grounded(
        f"Puncaknya {format_number(11.8)} ton.", FACTS.allowed_numbers()
    )


def test_a_rounded_number_is_rejected():
    """Kasus yang paling mungkin: model membulatkan ulang angka yang benar."""
    assert not numbers_are_grounded("Puncaknya sekitar 12 ton.", FACTS.allowed_numbers())


def test_a_number_the_model_added_up_itself_is_rejected():
    assert ungrounded_numbers("Totalnya 43,2 ton.", FACTS.allowed_numbers()) == ["43,2"]


def test_one_bad_number_condemns_the_whole_text():
    text = f"Puncak {format_number(11.8)} ton, kapasitas 99 ton."

    assert not numbers_are_grounded(text, FACTS.allowed_numbers())


@pytest.mark.parametrize("objective", ["aman", "pendapatan", "pasar"])
def test_the_template_narrative_always_passes_its_own_guard(objective):
    facts = Facts(**{**FACTS.__dict__, "objective": objective})
    text = template_narrative(facts)

    assert numbers_are_grounded(text, facts.allowed_numbers()), (
        f"templat memuat angka tak terhitung: {ungrounded_numbers(text, facts.allowed_numbers())}"
    )


def test_dates_in_the_block_are_allowed(golden_request):
    assert "2027" in FACTS.allowed_numbers()
    assert "04" in FACTS.allowed_numbers()


def test_an_empty_answer_is_rejected():
    """Justru karena teks kosong TIDAK memuat angka liar, ia harus dijegal lebih dulu."""
    assert numbers_are_grounded("", FACTS.allowed_numbers())
    assert rejection_reason("", FACTS.allowed_numbers()) == "narrative_too_short"


def test_whitespace_only_is_rejected():
    assert rejection_reason("   \n\t  ", FACTS.allowed_numbers()) == "narrative_too_short"


def test_a_truncated_answer_is_rejected_before_its_numbers_are_read():
    text = template_narrative(FACTS)

    assert rejection_reason(text, FACTS.allowed_numbers()) is None
    assert rejection_reason(text, FACTS.allowed_numbers(), truncated=True) == "truncated"


def test_a_good_answer_has_no_reason_to_be_rejected():
    assert rejection_reason(template_narrative(FACTS), FACTS.allowed_numbers()) is None


def test_an_ungrounded_number_still_names_itself():
    text = template_narrative(FACTS) + " Naik 173 persen."

    assert rejection_reason(text, FACTS.allowed_numbers()) == "ungrounded_numbers"
