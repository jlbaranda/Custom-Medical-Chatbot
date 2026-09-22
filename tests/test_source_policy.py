from ingestion.common.source_policy import evaluate_trusted_source


def test_trusted_domains_and_subdomains():
    assert evaluate_trusted_source("https://medlineplus.gov/diabetes.html").allowed
    decision = evaluate_trusted_source("https://www.niddk.nih.gov/health-information/diabetes")
    assert decision.allowed
    assert decision.source_group == "nih"
    assert evaluate_trusted_source("https://www.cdc.gov/diabetes/").source_group == "cdc"
    assert evaluate_trusted_source("https://www.cancer.gov/about-cancer").source_group == "nci"


def test_lookalike_domain_is_rejected():
    decision = evaluate_trusted_source("https://nih.gov.example.com/article")
    assert not decision.allowed
    assert decision.reason == "domain_not_allowlisted"
