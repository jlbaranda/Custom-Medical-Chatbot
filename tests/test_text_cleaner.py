from ingestion.cleaners.text_cleaner import clean_text, repair_text_encoding


def test_repairs_common_mojibake():
    broken = "diabetesâ€™ management plan â€” 8.5â€³ x 11â€³"
    fixed = repair_text_encoding(broken)
    assert "diabetes’ management plan" in fixed
    assert "—" in fixed
    assert "″" in fixed
    assert "â" not in fixed


def test_clean_text_preserves_paragraph_boundaries():
    text = "Heading\n\nFirst   paragraph.\n\nSecond paragraph."
    cleaned = clean_text(text)
    assert "Heading\n\nFirst paragraph.\n\nSecond paragraph." == cleaned
