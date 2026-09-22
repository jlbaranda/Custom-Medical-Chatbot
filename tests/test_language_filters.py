from ingestion.common.language_filters import (
    html_declares_spanish,
    is_obviously_spanish_url,
    is_english_language,
)


def test_language_normalization():
    assert is_english_language("English")
    assert is_english_language("en-US")
    assert not is_english_language("Spanish")


def test_spanish_urls():
    assert is_obviously_spanish_url("https://example.gov/spanish/diabetes")
    assert is_obviously_spanish_url("https://example.gov/article?lang=es")
    assert is_obviously_spanish_url("https://example.gov/es/diabetes")
    assert not is_obviously_spanish_url("https://example.gov/diabetes")


def test_html_language():
    assert html_declares_spanish('<html lang="es"><body>Hola</body></html>')
    assert not html_declares_spanish('<html lang="en"><body>Hello</body></html>')
