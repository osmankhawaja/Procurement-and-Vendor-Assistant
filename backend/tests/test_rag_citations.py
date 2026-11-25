from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from app.rag import retriever


class FakeVectorStore:
    async def asimilarity_search_with_relevance_scores(
        self,
        query: str,
        *,
        k: int,
    ) -> list[tuple[Document, float]]:
        assert query == "cloud data retention"
        assert k == 3
        return [
            (
                Document(
                    page_content="Retain cloud records for the approved period.",
                    metadata={
                        "doc_title": "Cloud Licensing",
                        "source": "SaaS_Cloud_Licensing_Guidelines.md",
                        "section": "Data Retention",
                    },
                ),
                0.91,
            ),
            (
                Document(
                    page_content="Weakly related text.",
                    metadata={"doc_title": "Other policy"},
                ),
                0.4,
            ),
        ]


@pytest.fixture
def isolated_embeddings_cache() -> Iterator[None]:
    retriever._get_embeddings.cache_clear()
    try:
        yield
    finally:
        retriever._get_embeddings.cache_clear()


def test_embeddings_have_a_bounded_request_timeout(
    monkeypatch: pytest.MonkeyPatch,
    isolated_embeddings_cache: None,
) -> None:
    class FakeEmbeddings:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    monkeypatch.setattr(retriever, "GoogleGenerativeAIEmbeddings", FakeEmbeddings)
    monkeypatch.setattr(
        retriever,
        "get_settings",
        lambda: SimpleNamespace(
            google_api_key="test-key",
            embedding_model="test-embedding-model",
        ),
    )

    embeddings = retriever._get_embeddings()

    assert embeddings.kwargs["request_options"] == {"timeout": 30}


@pytest.mark.asyncio
async def test_policy_retrieval_returns_only_confident_cited_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retriever,
        "get_settings",
        lambda: SimpleNamespace(
            rag_top_k=5,
            rag_min_confidence=0.72,
        ),
    )
    monkeypatch.setattr(retriever, "_get_vector_store", lambda: FakeVectorStore())

    result = await retriever.retrieve_policy_context(
        "cloud data retention",
        top_k=3,
    )

    assert "approved period" in result.context
    assert len(result.citations) == 1
    assert result.citations[0]["section"] == "Data Retention"
    assert result.citations[0]["confidence"] == 0.91


@pytest.mark.asyncio
async def test_policy_retrieval_rejects_blank_query() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        await retriever.retrieve_policy_context("   ")