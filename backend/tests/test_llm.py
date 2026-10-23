from types import SimpleNamespace

import pytest

from app.analysis import llm

STATS = {
    "a": {"symbol": "600667", "market": "CN", "name": "太极实业"},
    "b": {"symbol": "GOOGL", "market": "US", "name": "谷歌A类股"},
    "correlation": {"pearson": 0.0456},
    "computed_at": "x",
}
NEWS = [{"id": "N1", "symbol": "600667", "market": "CN", "name": "太极实业",
         "title": "t", "content": "c", "published_at": "2026-10-22", "source": "s", "url": "u"}]
GOOD = {"logic_chains": [{"claim": "c", "evidence_ids": ["N1"], "confidence": "low"}],
        "summary": "s", "caveats": []}


def response(input_=None, stop_reason="tool_use"):
    content = [SimpleNamespace(type="tool_use", name=llm.TOOL_NAME, input=input_)] if input_ is not None else [
        SimpleNamespace(type="text", text="hi")]
    return SimpleNamespace(content=content, stop_reason=stop_reason, model="m", _request_id="r")


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def model_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-model")


def test_validate_rejects_unknown_evidence():
    bad = {**GOOD, "logic_chains": [{"claim": "c", "evidence_ids": ["N9"], "confidence": "low"}]}
    with pytest.raises(ValueError, match="N9"):
        llm.validate_analysis(bad, {"N1"})


def test_validate_rejects_chain_without_evidence():
    bad = {**GOOD, "logic_chains": [{"claim": "c", "evidence_ids": [], "confidence": "low"}]}
    with pytest.raises(ValueError):
        llm.validate_analysis(bad, {"N1"})


def test_validate_rejects_bad_confidence():
    bad = {**GOOD, "logic_chains": [{"claim": "c", "evidence_ids": ["N1"], "confidence": "sure"}]}
    with pytest.raises(ValueError):
        llm.validate_analysis(bad, {"N1"})


def test_analyze_success_uses_tool_and_env_model():
    client = FakeClient([response(GOOD)])
    assert llm.analyze(STATS, NEWS, [], client=client) == GOOD
    call = client.calls[0]
    assert call["model"] == "test-model"
    assert call["tools"][0]["name"] == "submit_analysis" and call["tools"][0]["strict"] is True
    assert call["tool_choice"] == {"type": "auto"}


def test_analyze_retries_once_then_succeeds():
    client = FakeClient([response(None, stop_reason="end_turn"), response(GOOD)])
    assert llm.analyze(STATS, NEWS, [], client=client) == GOOD
    assert len(client.calls) == 2


def test_analyze_fails_after_retry():
    bad = {"summary": "s"}
    client = FakeClient([response(bad), response(bad)])
    with pytest.raises(llm.LLMError):
        llm.analyze(STATS, NEWS, [], client=client)
    assert len(client.calls) == 2


def test_prompt_contains_news_ids_and_note():
    prompt = llm.build_user_prompt(STATS, NEWS, ["美股新闻源未接入"])
    assert "[N1]" in prompt and "美股新闻源未接入" in prompt
    assert "computed_at" not in prompt
