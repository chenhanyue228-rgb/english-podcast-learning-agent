from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.enrichment.llm_provider import (
    OpenAIVocabularyEnrichmentProvider,
    VocabularyEnrichmentProviderError,
)


@dataclass
class FakeResponse:
    status_code: int
    payload: dict
    text: str = "{}"

    def json(self):
        return self.payload


class FakeHttpxClient:
    def __init__(self, response: FakeResponse):
        self.response = response
        self.post_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, headers=None, json=None):
        self.post_calls.append({"url": url, "headers": headers, "json": json})
        return self.response


def test_openai_vocabulary_enrichment_provider_parses_json(monkeypatch) -> None:
    response = FakeResponse(
        200,
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"word":"conversation","original_context":"The conversation also shows how to negotiate with investors.","meaning":"discussion about a business decision in context","chinese_meaning":"对话","part_of_speech":"noun","professional_category":"Negotiation","usage_example":"The conversation helped clarify the plan with stakeholders.","common_collocations":["have a difficult conversation","conversation with stakeholders"]}'
                        )
                    }
                }
            ]
        },
    )
    fake_client = FakeHttpxClient(response)
    monkeypatch.setattr("src.enrichment.llm_provider.httpx.Client", lambda timeout=None: fake_client)

    provider = OpenAIVocabularyEnrichmentProvider(api_key="secret", model="gpt-4.1-mini")
    enriched = provider.enrich("conversation", "The conversation also shows how to negotiate with investors.")

    assert enriched["word"] == "conversation"
    assert enriched["original_context"] == "The conversation also shows how to negotiate with investors."
    assert enriched["meaning"] == "discussion about a business decision in context"
    assert enriched["chinese_meaning"] == "对话"
    assert enriched["part_of_speech"] == "noun"
    assert enriched["professional_category"] == "Negotiation"
    assert enriched["usage_example"] == "The conversation helped clarify the plan with stakeholders."
    assert enriched["common_collocations"] == [
        "have a difficult conversation",
        "conversation with stakeholders",
    ]
    assert fake_client.post_calls[0]["url"].endswith("/chat/completions")


def test_openai_vocabulary_enrichment_provider_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAIVocabularyEnrichmentProvider(api_key="")

    with pytest.raises(VocabularyEnrichmentProviderError, match="OPENAI_API_KEY"):
        provider.enrich("conversation", "context")
