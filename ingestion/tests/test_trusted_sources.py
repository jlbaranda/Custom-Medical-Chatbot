from ingestion.medlineplus.trusted_sources import evaluate_trusted_source


def test_trusted_domains_and_subdomains():
    assert evaluate_trusted_source("https://medlineplus.gov/diabetes.html").allowed
    assert evaluate_trusted_source("https://www.niddk.nih.gov/health-information/diabetes").allowed
    assert evaluate_trusted_source("https://www.cdc.gov/diabetes/").allowed
    assert evaluate_trusted_source("https://www.cancer.gov/about-cancer").allowed


def test_lookalike_domain_is_rejected():
    decision = evaluate_trusted_source("https://nih.gov.example.com/article")
    assert not decision.allowed
    assert decision.reason == "domain_not_allowlisted"
