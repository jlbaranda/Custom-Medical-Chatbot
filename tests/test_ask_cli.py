"""CLI wiring tests: no Ollama connection or model downloads required."""
from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts import ask


def test_rag_wires_existing_guardrails(monkeypatch):
    import guardrails.generation as generation
    import retrieval.pubmedbert as pubmedbert

    retriever = object()
    generator = object()
    make_retriever = Mock(return_value=retriever)
    make_generator = Mock(return_value=generator)
    make_guarded_bot = Mock(return_value=object())
    monkeypatch.setattr(pubmedbert, "PubMedBERTRetriever", make_retriever)
    monkeypatch.setattr(generation, "OllamaGenerator", make_generator)
    monkeypatch.setattr(ask.GuardedChatbot, "from_config", make_guarded_bot)

    bot = ask.build_chatbot(model="some-cloud-ready-local-model", timeout=90)

    assert bot is make_guarded_bot.return_value
    make_retriever.assert_called_once_with()
    make_generator.assert_called_once_with(model="some-cloud-ready-local-model", timeout=90)
    make_guarded_bot.assert_called_once_with(retriever=retriever, generator=generator)


def test_baseline_still_uses_existing_defaults(monkeypatch):
    make_guarded_bot = Mock(return_value=object())
    monkeypatch.setattr(ask.GuardedChatbot, "from_config", make_guarded_bot)

    result = ask.build_chatbot(baseline=True)

    assert result is make_guarded_bot.return_value
    make_guarded_bot.assert_called_once_with()


def test_missing_index_gives_actionable_error(monkeypatch):
    import retrieval.pubmedbert as pubmedbert
    monkeypatch.setattr(
        pubmedbert,
        "PubMedBERTRetriever",
        Mock(side_effect=FileNotFoundError("embeddings.npy")),
    )
    with pytest.raises(FileNotFoundError, match="build_rag_index.py"):
        ask.build_chatbot()


def test_chat_reuses_bot_and_passes_history(monkeypatch, capsys):
    def response(text):
        return SimpleNamespace(
            action=SimpleNamespace(value="answer"),
            text=text,
            debug={},
            trace=SimpleNamespace(to_dict=lambda: {"latency_ms": {"generation": 10}}),
        )

    bot = SimpleNamespace(ask=Mock(side_effect=[response("Asthma answer [1]"), response("Followup [1]")]))
    make_bot = Mock(return_value=bot)
    monkeypatch.setattr(ask, "build_chatbot", make_bot)
    monkeypatch.setattr(sys, "argv", ["ask.py", "--chat", "--trace"])
    prompts = iter(["What is asthma?", "And its symptoms?", ""])
    monkeypatch.setattr("builtins.input", lambda prompt: next(prompts))

    ask.main()

    make_bot.assert_called_once()
    assert bot.ask.call_count == 2
    assert bot.ask.call_args_list[0].kwargs == {
        "history": [],
    }
    assert bot.ask.call_args_list[0].args == ("What is asthma?",)
    assert bot.ask.call_args_list[1].args == ("And its symptoms?",)
    assert bot.ask.call_args_list[1].kwargs["history"] == [
        {"role": "user", "content": "What is asthma?"},
        {"role": "assistant", "content": "Asthma answer [1]"},
    ]
    output = capsys.readouterr().out
    assert "Asthma answer [1]" in output
    assert "Followup [1]" in output
    assert "latency_ms" in output


def test_single_question_debug_is_preserved(monkeypatch, capsys):
    bot = SimpleNamespace(ask=Mock(return_value=SimpleNamespace(
        action=SimpleNamespace(value="no_support"),
        text="No trusted source.",
        debug={"blocked_by": "retrieval gate"},
        trace=SimpleNamespace(to_dict=lambda: {}),
    )))
    monkeypatch.setattr(ask, "build_chatbot", Mock(return_value=bot))
    monkeypatch.setattr(sys, "argv", ["ask.py", "--debug", "Unsupported question?"])

    ask.main()

    bot.ask.assert_called_once_with("Unsupported question?", history=[])
    output = capsys.readouterr().out
    assert "[no_support]" in output
    assert "retrieval gate" in output
