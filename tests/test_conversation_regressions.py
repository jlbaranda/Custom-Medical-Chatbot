"""Regression tests for independent questions, anaphoric follow-ups and safety."""

import pytest

from guardrails.conversation import is_follow_up
from guardrails.normalize import normalize
from guardrails.pipeline import GuardedChatbot
from guardrails.policy import GuardrailPolicy
from guardrails.types import Action, Classification, INTENTS, Intent, Trace


@pytest.mark.parametrize("question", [
    "What causes asthma attacks?",
    "How is asthma diagnosed?",
    "What are the differences between asthma and pneumonia?",
    "What is pneumonia?",
    "What are the symptoms of asthma?",
    "Are asthma attacks dangerous?",
])
def test_independent_questions_do_not_inherit_previous_query(question):
    assert not is_follow_up(normalize(question))


@pytest.mark.parametrize("question", [
    "What about for kids?",
    "How is it diagnosed?",
    "Can I take that?",
    "And what about pneumonia?",
    "Same for children?",
    "More?",
    "Symptoms?",
    "What if those symptoms get worse?",
])
def test_context_dependent_followups_are_still_detected(question):
    assert is_follow_up(normalize(question))


class FakeClassifier:
    name = "fake-info"

    def classify(self, text):
        probabilities = {intent: (1.0 if intent is Intent.INFO else 0.0) for intent in INTENTS}
        return Classification(probabilities, 0.0, 0.0, self.name)


class NotUsed:
    name = "not-used"

    def search(self, query, k):
        raise AssertionError("screen() must not retrieve")

    def generate(self, query, passages):
        raise AssertionError("screen() must not generate")


def fake_bot():
    return GuardedChatbot(FakeClassifier(), NotUsed(), NotUsed(), GuardrailPolicy.from_file())


def test_independent_question_is_not_combined_with_old_topic():
    history = [{"role": "user", "content": "What are the differences between asthma and pneumonia?"}]
    trace = Trace("independent")
    decision, query = fake_bot().screen("How is asthma diagnosed?", trace=trace, history=history)
    assert decision.action is Action.ANSWER
    assert query == "How is asthma diagnosed?"
    assert trace.conversation["follow_up"] is False


def test_anaphoric_followup_still_combines_retrieval_context():
    history = [{"role": "user", "content": "What are the symptoms of asthma?"}]
    trace = Trace("followup")
    decision, query = fake_bot().screen("What about for kids?", trace=trace, history=history)
    assert decision.action is Action.ANSWER
    assert query == "What are the symptoms of asthma? What about for kids?"
    assert trace.conversation["follow_up"] is True


def test_emergency_history_still_overrides_independent_question():
    history = [{"role": "user", "content": "I want to kill myself"}]
    decision, _ = fake_bot().screen("What is pneumonia?", history=history)
    assert decision.action is Action.EMERGENCY
