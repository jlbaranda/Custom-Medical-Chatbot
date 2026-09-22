import json

from ingestion.sources.web import html_downloader


class FakeResponse:
    def __init__(self, *, url, status_code=200, headers=None, content=b""):
        self.url = url
        self.status_code = status_code
        self.headers = headers or {}
        self.content = content
        self.encoding = None
        self.apparent_encoding = "utf-8"


def test_pdf_candidate_is_ingested(monkeypatch, tmp_path):
    url = "https://www.nhlbi.nih.gov/example.pdf"
    response = FakeResponse(
        url=url,
        headers={"Content-Type": "application/pdf"},
        content=b"fake-pdf-bytes",
    )
    monkeypatch.setattr(html_downloader.requests, "get", lambda *args, **kwargs: response)
    monkeypatch.setattr(
        html_downloader,
        "extract_pdf_text",
        lambda data: ("Asthma PDF", " ".join(["asthma"] * 100), 2),
    )

    result = html_downloader.download_source_candidate(
        {
            "url": url,
            "title": "Asthma PDF",
            "parent_topics": ["Asthma"],
            "publisher_hints": ["NHLBI"],
            "categories": ["Treatments and Therapies"],
            "discovered_via": [],
        },
        tmp_path,
    )

    assert result.status == "downloaded"
    assert result.source_format == "pdf"
    record = json.loads((tmp_path / "nih" / f"{result.document_id}.json").read_text(encoding="utf-8"))
    assert record["document_type"] == "linked_source_pdf"
    assert record["source_format"] == "pdf"
    assert record["page_count"] == 2


def test_unsupported_content_type_is_skipped(monkeypatch, tmp_path):
    url = "https://www.cdc.gov/example/data.csv"
    response = FakeResponse(
        url=url,
        headers={"Content-Type": "text/csv"},
        content=b"a,b\n1,2",
    )
    monkeypatch.setattr(html_downloader.requests, "get", lambda *args, **kwargs: response)

    result = html_downloader.download_source_candidate(
        {"url": url, "parent_topics": ["Flu"]},
        tmp_path,
    )
    assert result.status == "skipped"
    assert result.reason == "unsupported_content_type"


def test_html_downloader_uses_raw_bytes_not_wrong_requests_encoding(monkeypatch, tmp_path):
    url = "https://www.cdc.gov/example/article.html"
    body = " ".join(["medical evidence"] * 55)
    content = f"""
    <html lang="en"><head><meta charset="utf-8"><title>Encoding Test</title></head>
    <body><main><h1>Encoding Test</h1><p>It’s important — 8.5″. {body}</p></main></body>
    </html>
    """.encode("utf-8")
    response = FakeResponse(
        url=url,
        headers={"Content-Type": "text/html"},
        content=content,
    )
    # Simulate the kind of wrong guess that previously caused mojibake.
    response.encoding = "windows-1252"
    response.apparent_encoding = "windows-1252"
    monkeypatch.setattr(html_downloader.requests, "get", lambda *args, **kwargs: response)

    result = html_downloader.download_source_candidate(
        {
            "url": url,
            "title": "Encoding Test",
            "parent_topics": ["Flu"],
            "publisher_hints": ["CDC"],
            "categories": ["Overview"],
            "discovered_via": [],
        },
        tmp_path,
    )

    assert result.status == "downloaded"
    record = json.loads((tmp_path / "cdc" / f"{result.document_id}.json").read_text(encoding="utf-8"))
    assert "It’s important — 8.5″." in record["text"]
    assert "â€™" not in record["text"]
