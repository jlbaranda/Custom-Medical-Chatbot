"""Layout is kept only for sentences that pass the original citation/safety gates."""

from guardrails.output_check import check_output, render
from guardrails.types import Passage

SOURCE = Passage(
    "asthma-1",
    "Asthma symptoms include wheezing and coughing. Common triggers include pollen and mold. "
    "Cold air can trigger asthma symptoms. Tobacco smoke can trigger asthma symptoms. "
    "The doctor can diagnose asthma using breathing tests.",
    "Asthma", "MedlinePlus", "https://medlineplus.gov/asthma.html", 12.0,
)

CFG = {"output": {"require_citations": True, "min_support": 0.5, "block_doses_in": ["answer", "redirect"]}}


def test_paragraphs_and_bullets_preserved_with_citations():
    draft = (
        "Asthma symptoms include wheezing and coughing. [1]\n\n"
        "Common triggers include pollen and mold. [1]\n"
        "- **Pollen:** Pollen can trigger asthma symptoms. [1]\n"
        "- **Cold air:** Cold air can trigger asthma symptoms. [1]\n\n"
        "The doctor can diagnose asthma using breathing tests. [1]"
    )
    check = check_output(draft, [SOURCE], CFG, "answer")
    body, sources = render(check, [SOURCE])
    assert check.dropped == {}
    assert check.to_dict()["kept"] == 5
    assert "coughing. [1]\n\nCommon triggers" in body
    assert "\n\n- **Pollen:**" in body
    assert "\n- **Cold air:**" in body
    assert "\n\nThe doctor" in body
    assert sources == [SOURCE]


def test_every_bullet_needs_its_own_citation():
    draft = "- Pollen can trigger asthma symptoms.\n- Cold air can trigger asthma symptoms. [1]"
    check = check_output(draft, [SOURCE], CFG, "answer")
    body, _ = render(check, [SOURCE])
    assert check.dropped == {"uncited": 1}
    assert "Pollen" not in body
    assert body.startswith("Cold air")  # single surviving bullet becomes prose


def test_unsupported_bullet_removed_not_rendered():
    draft = "- Jupiter causes all asthma symptoms. [1]\n- Cold air can trigger asthma symptoms. [1]"
    check = check_output(draft, [SOURCE], CFG, "answer")
    body, _ = render(check, [SOURCE])
    assert check.dropped.get("unsupported") == 1
    assert "Jupiter" not in body
    assert body.startswith("Cold air")  # single surviving bullet becomes prose


def test_uncited_headings_are_not_exempt_from_support_rules():
    draft = "Key asthma facts:\n- Common triggers include pollen and mold. [1]"
    check = check_output(draft, [SOURCE], CFG, "answer")
    body, _ = render(check, [SOURCE])
    assert check.dropped == {"uncited": 1}
    assert "Key asthma facts:" not in body
    assert "Common triggers" in body


def test_whitespace_before_punctuation_is_fixed():
    check = check_output("Asthma symptoms include wheezing and coughing [1].", [SOURCE], CFG, "answer")
    body, _ = render(check, [SOURCE])
    assert "coughing. [1]" in body
    assert "coughing ." not in body


def test_dose_filter_still_blocks_bullet():
    med = Passage("med-1", "Adults take 500 mg of medicine daily.", "Medicine", "NIH", "med-url", 12)
    check = check_output("- Adults take 500 mg of medicine daily. [1]", [med], CFG, "answer")
    assert check.dropped.get("dose") == 1
    assert not check.kept


def test_uncited_fallback_keeps_source_but_no_fake_citation():
    cfg = {"output": {**CFG["output"], "require_citations": False}}
    check = check_output("Asthma symptoms include wheezing and coughing.", [SOURCE], cfg, "answer")
    body, sources = render(check, [SOURCE])
    assert check.dropped == {}
    assert "[1]" not in body
    assert sources == [SOURCE]
