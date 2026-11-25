"""Policy embedding and retrieval from the configured Qdrant collection."""

import logging
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore

from app.config import get_settings

logger = logging.getLogger(__name__)

_EMBEDDING_REQUEST_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class PolicyRetrievalResult:
    """Retrieved policy context and source-grounded citations."""

    context: str
    citations: list[dict[str, Any]]


@lru_cache(maxsize=1)
def _get_embeddings() -> GoogleGenerativeAIEmbeddings:
    settings = get_settings()
    if not settings.google_api_key:
        raise RuntimeError("GOOGLE_API_KEY is required for policy embeddings.")
    return GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=settings.google_api_key,
        request_options={"timeout": _EMBEDDING_REQUEST_TIMEOUT_SECONDS},
    )


@lru_cache(maxsize=1)
def _get_vector_store() -> QdrantVectorStore:
    settings = get_settings()
    if not settings.qdrant_url:
        raise ValueError("QDRANT_URL must be configured for policy retrieval.")
    return QdrantVectorStore.from_existing_collection(
        collection_name=settings.qdrant_collection,
        embedding=_get_embeddings(),
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )


async def retrieve_policy_context(
    query: str,
    *,
    top_k: int | None = None,
) -> PolicyRetrievalResult:
    """Retrieve relevant policy chunks and citations for a non-empty query."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("Policy retrieval requires a non-empty query.")

    settings = get_settings()
    result_limit = settings.rag_top_k if top_k is None else top_k
    if result_limit <= 0:
        raise ValueError("top_k must be greater than zero.")

    try:
        vector_store = _get_vector_store()
        matches = await vector_store.asimilarity_search_with_relevance_scores(
            normalized_query,
            k=result_limit,
        )
    except Exception as exc:
        _get_vector_store.cache_clear()
        logger.warning(
            "Policy retrieval unavailable; continuing without RAG context: %s",
            exc,
        )
        return PolicyRetrievalResult(context="", citations=[])

    context_sections: list[str] = []
    citations: list[dict[str, Any]] = []
    for document, score in matches:
        if not math.isfinite(score) or score < settings.rag_min_confidence:
            continue

        citation = _citation_for(document, score)
        citations.append(citation)
        heading = citation["section"] or citation["doc_title"]
        context_sections.append(
            f"[{citation['doc_title']} — {heading}]\n{document.page_content}"
        )

    return PolicyRetrievalResult(
        context="\n\n".join(context_sections),
        citations=citations,
    )


def _citation_for(document: Document, score: float) -> dict[str, Any]:
    metadata = document.metadata
    return {
        "doc_title": metadata.get("doc_title", "Procurement policy"),
        "source": metadata.get("source", ""),
        "section": metadata.get("section", ""),
        "snippet": document.page_content[:500],
        "confidence": round(score, 4),
    }