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


def test_falls_back_to_body_when_main_container_is_too_small():
    repeated = " ".join(["medical"] * 100)
    html = f"""
    <html lang="en">
      <head><title>ODS Fact Sheet</title></head>
      <body>
        <main><p>Short shell.</p></main>
        <div id="fact-sheet-content">
          <h1>Iron Fact Sheet</h1>
          <p>{repeated}</p>
        </div>
      </body>
    </html>
    """
    title, text = extract_article_text(html)
    assert title == "Iron Fact Sheet"
    assert len(text.split()) >= 100
    assert "medical medical medical" in text


def test_removes_common_social_and_page_furniture_lines():
    html = """
    <html><body><main>
      <h1>Useful Page</h1>
      <p>Useful medical evidence stays here.</p>
      <div>Print</div><div>Share</div><div>Facebook</div>
      <div>LinkedIn</div><div>Twitter</div><div>Syndicate</div>
      <div>About This Page</div>
    </main></body></html>
    """
    _, text = extract_article_text(html)
    assert "Useful medical evidence" in text
    for junk in ["Print", "Share", "Facebook", "LinkedIn", "Twitter", "Syndicate", "About This Page"]:
        assert junk not in text


def test_raw_utf8_bytes_preserve_unicode_punctuation():
    paragraph = " ".join(["medical evidence"] * 50)
    html = f"""
    <html lang="en"><head><meta charset="utf-8"><title>Unicode</title></head>
    <body><main><h1>Unicode Test</h1>
    <p>It’s important — use an 8.5″ example. {paragraph}</p>
    </main></body></html>
    """.encode("utf-8")
    _, text = extract_article_text(html)
    assert "It’s important — use an 8.5″ example." in text
    assert "â€™" not in text
    assert "â€”" not in text
    assert "â€³" not in text


def test_removes_link_heavy_related_card_block():
    evidence = " ".join(["useful medical evidence"] * 40)
    html = f"""
    <html><body><main>
      <h1>Useful Page</h1>
      <p>{evidence}</p>
      <section class="related-cards">
        <a href="/a">Keep Reading Asthma Guide</a>
        <a href="/b">Related Vaccine Resource</a>
        <a href="/c">Download Patient Handout</a>
      </section>
    </main></body></html>
    """
    _, text = extract_article_text(html)
    assert "useful medical evidence" in text
    assert "Keep Reading Asthma Guide" not in text
    assert "Related Vaccine Resource" not in text


def test_keeps_inline_link_text_inside_paragraph_sentence():
    evidence = " ".join(["additional medical evidence"] * 30)
    html = f"""
    <html><body><main>
      <h1>Flu</h1>
      <p>Having flu increases your risk of getting <a href="/pneumo">pneumococcal disease</a>.</p>
      <p>Vaccination is important because people can be at <a href="/risk">higher risk</a> of complications.</p>
      <p>{evidence}</p>
    </main></body></html>
    """
    _, text = extract_article_text(html)
    assert "Having flu increases your risk of getting pneumococcal disease." in text
    assert "at higher risk of complications." in text
    assert "getting\n\npneumococcal disease" not in text
    assert "at\n\nhigher risk" not in text


def test_removes_trailing_resource_card_section_but_keeps_article_prose():
    body = " ".join(["medical guidance"] * 65)
    html = f"""
    <html><body><main>
      <h1>Useful Article</h1>
      <h2>Treatment</h2>
      <p>{body}</p>
      <h2>Resources</h2>
      <h3><a href="/a">Managing Sick Days</a></h3>
      <p>Learn more about planning for illness.</p>
      <h3><a href="/b">Vaccination Guide</a></h3>
      <p>Information about adult vaccines.</p>
      <h3><a href="/c">Other Resource</a></h3>
      <p>Learn more about this topic.</p>
    </main></body></html>
    """
    _, text = extract_article_text(html)
    assert "Treatment" in text
    assert "medical guidance" in text
    assert "Managing Sick Days" not in text
    assert "Vaccination Guide" not in text


def test_trims_trailing_publication_metadata():
    body = " ".join(["useful medical evidence"] * 55)
    html = f"""
    <html><body><main>
      <h1>Article</h1>
      <p>{body}</p>
      <p>Published:</p>
      <p>October 1, 2024</p>
      <p>Updated:</p>
      <p>September 1, 2026</p>
      <p>Reviewed:</p>
      <p>June 9, 2026</p>
    </main></body></html>
    """
    _, text = extract_article_text(html)
    assert "useful medical evidence" in text
    assert "Published:" not in text
    assert "October 1, 2024" not in text
    assert "Reviewed:" not in text


def test_trims_cdc_maintenance_sentences_after_resources_heading():
    body = " ".join(["useful medical evidence"] * 70)
    html = f"""
    <html><body><main>
      <h1>Flu</h1>
      <h2>Treatment</h2>
      <p>{body}</p>
      <h2>Resources</h2>
      <p>This page was last updated on this date. Updates may include minor edits, image changes, or other modifications to page content.</p>
      <p>The information on this page was last reviewed by subject matter experts to ensure accuracy.</p>
    </main></body></html>
    """
    _, text = extract_article_text(html)
    assert "Treatment" in text
    assert "useful medical evidence" in text
    assert "Resources" not in text
    assert "This page was last updated on this date" not in text
    assert "The information on this page was last reviewed" not in text


def test_does_not_remove_medical_text_that_mentions_updates_earlier_in_article():
    intro = " ".join(["medical context"] * 35)
    tail = " ".join(["more clinical guidance"] * 35)
    html = f"""
    <html><body><main>
      <h1>Article</h1>
      <p>{intro}</p>
      <p>Patients should update their medication list when their treatment changes.</p>
      <p>{tail}</p>
    </main></body></html>
    """
    _, text = extract_article_text(html)
    assert "Patients should update their medication list" in text
    assert "more clinical guidance" in text
