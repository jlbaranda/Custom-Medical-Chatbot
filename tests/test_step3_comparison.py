"""Regression tests: explicit comparisons require verified sources for each side."""
from guardrails.comparison import detect_comparison
from guardrails.retrieval import retrieval_gate
from guardrails.types import Passage

CONFIG = {"retrieval": {
    "top_k": 4, "candidates": 8, "min_rerank_score": 9.5,
    "min_rerank_score_redirect": 8.0, "rerank_keep_margin": 2.0,
}}


def mk(topic, number):
    return Passage(
        f"{topic}-{number}", f"{topic.title()} is a medical condition with symptoms.",
        f"{topic.title()} overview", "MedlinePlus", f"https://example.org/{topic}/{number}", 0.0,
    )


class FakeRetriever:
    def __init__(self, have_asthma=True, have_pneumonia=True):
        self.have_asthma = have_asthma
        self.have_pneumonia = have_pneumonia
        self.queries = []

    def search(self, query, k):
        self.queries.append(query)
        if 'asthma' in query.lower() and 'pneumonia' not in query.lower():
            return [mk('asthma', 1), mk('asthma', 2)] if self.have_asthma else []
        if 'pneumonia' in query.lower() and 'asthma' not in query.lower():
            return [mk('pneumonia', 1), mk('pneumonia', 2)] if self.have_pneumonia else []
        # Simulate the pre-Step-3 bug: a combined search only finds asthma.
        return [mk('asthma', 1)]


class FakeReranker:
    def rerank(self, query, passages):
        return [Passage(p.chunk_id, p.text, p.title, p.publisher,
                        p.source_url, 15.0 - i) for i, p in enumerate(passages)]


def test_explicit_comparison_recognized_in_either_order():
    assert detect_comparison('What are the differences between asthma and pneumonia?') == ('asthma', 'pneumonia')
    assert detect_comparison('Pneumonia vs. asthma') == ('pneumonia', 'asthma')
    assert detect_comparison('How do influenza and asthma differ?') == ('flu', 'asthma')


def test_independent_question_not_treated_as_comparison():
    assert detect_comparison('What are symptoms of asthma and pneumonia?') is None
    assert detect_comparison('How is asthma diagnosed?') is None
    assert detect_comparison('Compare asthma and a common cold') is None
    assert detect_comparison('Compare asthma, flu and pneumonia') is None


def test_comparison_retrieves_and_keeps_both_medical_topics():
    r = FakeRetriever()
    g = retrieval_gate(r, 'What are the differences between asthma and pneumonia?', CONFIG,
                       reranker=FakeReranker())
    assert g.passed
    assert r.queries == ['What is asthma?', 'What is pneumonia?']
    assert len(g.passages) == 4
    assert {p.title.split()[0] for p in g.passages} == {'Asthma', 'Pneumonia'}
    assert g.to_dict()['topic_source_count'] == {'asthma': 2, 'pneumonia': 2}


def test_comparison_blocks_when_second_topic_has_no_evidence():
    g = retrieval_gate(FakeRetriever(have_pneumonia=False),
                       'Compare asthma and pneumonia', CONFIG, reranker=FakeReranker())
    assert not g.passed
    assert g.passages == []
    assert 'pneumonia' in g.reason


def test_symptom_comparison_uses_symptoms_for_both_topics():
    r = FakeRetriever()
    g = retrieval_gate(r, 'Compare the symptoms of asthma and pneumonia', CONFIG,
                       reranker=FakeReranker())
    assert g.passed
    assert r.queries == ['What are the symptoms of asthma?', 'What are the symptoms of pneumonia?']


def test_normal_question_uses_original_retrieval_path():
    r = FakeRetriever()
    g = retrieval_gate(r, 'What is asthma?', CONFIG, reranker=FakeReranker())
    assert g.passed
    assert r.queries == ['What is asthma?']
    assert not hasattr(g, 'comparison_topics')


def test_comparison_fails_when_topic_title_mismatches_even_if_score_is_high():
    class WrongDocs(FakeRetriever):
        def search(self, query, k):
            if query == 'What is pneumonia?':
                return [mk('asthma', 9)]
            return super().search(query, k)
    g = retrieval_gate(WrongDocs(), 'Compare asthma vs pneumonia', CONFIG, reranker=FakeReranker())
    assert not g.passed
    assert 'topic-specific' in g.reason
