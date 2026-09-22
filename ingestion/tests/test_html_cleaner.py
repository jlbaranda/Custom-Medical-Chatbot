from ingestion.cleaners.html_cleaner import extract_article_text


def test_extracts_main_content_and_removes_nav():
    html = """
    <html lang="en">
      <head><title>Example</title></head>
      <body>
        <nav>Navigation junk</nav>
        <main><h1>Diabetes</h1><p>This is useful medical information.</p></main>
        <footer>Footer junk</footer>
      </body>
    </html>
    """
    title, text = extract_article_text(html)
    assert title == "Diabetes"
    assert "useful medical information" in text
    assert "Navigation junk" not in text
    assert "Footer junk" not in text
