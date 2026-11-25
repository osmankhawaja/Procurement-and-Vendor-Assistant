from pathlib import Path
from types import SimpleNamespace

import pytest

from app.rag import ingest


def test_ingestion_chunks_markdown_and_reports_empty_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = tmp_path / "policy.md"
    policy_path.write_text(
        "# Procurement\n## Approved vendors\nOnly approved suppliers may be used.",
        encoding="utf-8",
    )
    empty_path = tmp_path / "empty.md"
    empty_path.write_text("", encoding="utf-8")
    indexed: dict[str, object] = {}

    class FakeVectorStore:
        @staticmethod
        def from_documents(documents: list[object], **kwargs: object) -> None:
            indexed["documents"] = documents
            indexed.update(kwargs)

    monkeypatch.setattr(ingest, "QdrantVectorStore", FakeVectorStore)
    monkeypatch.setattr(ingest, "_get_embeddings", lambda: object())
    monkeypatch.setattr(
        ingest,
        "get_settings",
        lambda: SimpleNamespace(
            qdrant_collection="policies",
            qdrant_url="http://qdrant.test",
            qdrant_api_key="",
        ),
    )

    result = ingest.ingest_policies(tmp_path)

    assert result.files_indexed == 1
    assert result.chunks_indexed == 1
    assert result.empty_files == ("empty.md",)
    documents = indexed["documents"]
    assert isinstance(documents, list) and len(documents) == 1
    assert documents[0].metadata["section"] == "Procurement > Approved vendors"
    assert indexed["ids"]


def test_ingestion_fails_when_all_policy_files_are_empty(
    tmp_path: Path,
) -> None:
    (tmp_path / "empty.md").write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="No non-empty policy text"):
        ingest.ingest_policies(tmp_path)