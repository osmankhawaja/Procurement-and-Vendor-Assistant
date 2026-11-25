"""Load Markdown procurement policies, chunk them, and index them in Qdrant."""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.config import get_settings
from app.rag.retriever import _get_embeddings, _get_vector_store


POLICY_DIRECTORY = Path(__file__).resolve().parents[2] / "data" / "policies"
_MARKDOWN_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3"), ("####", "h4")]
_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 150


@dataclass(frozen=True)
class IngestionSummary:
    """Summary of a completed policy-index operation."""

    collection_name: str
    files_indexed: int
    chunks_indexed: int
    empty_files: tuple[str, ...]


def _load_policy_documents(
    policy_directory: Path,
) -> tuple[list[Document], list[str], int]:
    if not policy_directory.is_dir():
        raise FileNotFoundError(f"Policy directory not found: {policy_directory}")

    markdown_files = sorted(policy_directory.glob("*.md"))
    if not markdown_files:
        raise FileNotFoundError(
            f"No Markdown (*.md) policy documents found in {policy_directory}."
        )

    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_MARKDOWN_HEADERS,
        strip_headers=True,
    )
    chunk_splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
        add_start_index=True,
    )
    documents: list[Document] = []
    empty_files: list[str] = []
    files_indexed = 0

    for path in markdown_files:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            empty_files.append(path.name)
            continue

        files_indexed += 1
        sections = header_splitter.split_text(text)
        if not sections:
            sections = [Document(page_content=text)]

        for section_index, section in enumerate(sections):
            section_text = section.page_content.strip()
            if not section_text:
                continue
            section_name = " > ".join(
                str(section.metadata[key])
                for key in ("h1", "h2", "h3", "h4")
                if section.metadata.get(key)
            )
            parent_metadata = {
                "doc_title": path.stem.replace("_", " "),
                "source": path.name,
                "section": section_name,
                "section_index": section_index,
            }
            section_document = Document(
                page_content=section_text,
                metadata={**section.metadata, **parent_metadata},
            )
            documents.extend(chunk_splitter.split_documents([section_document]))

    return documents, empty_files, files_indexed


def _document_id(document: Document, index: int) -> str:
    source = str(document.metadata["source"])
    section = str(document.metadata.get("section", ""))
    chunk_preview = document.page_content[:120]
    identity = f"{source}\0{section}\0{index}\0{chunk_preview}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return str(uuid.UUID(hex=digest[:32]))


def ingest_policies(
    policy_directory: Path | None = None,
    *,
    force_recreate: bool = False,
) -> IngestionSummary:
    """Index the local Markdown policy corpus in the configured Qdrant collection.

    Repeated ingestion uses deterministic UUIDs to update existing points. Set
    ``force_recreate`` to replace the configured collection with the current corpus.
    """
    settings = get_settings()
    directory = Path(policy_directory) if policy_directory is not None else POLICY_DIRECTORY
    documents, empty_files, files_indexed = _load_policy_documents(directory)
    if not documents:
        empty_list = ", ".join(empty_files)
        raise ValueError(
            "No non-empty policy text was found to index."
            + (f" Empty files: {empty_list}." if empty_list else "")
        )

    ids = [_document_id(document, index) for index, document in enumerate(documents)]
    embeddings = _get_embeddings()

    QdrantVectorStore.from_documents(
        documents,
        embedding=embeddings,
        ids=ids,
        collection_name=settings.qdrant_collection,
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        force_recreate=force_recreate,
    )
    _get_vector_store.cache_clear()

    return IngestionSummary(
        collection_name=settings.qdrant_collection,
        files_indexed=files_indexed,
        chunks_indexed=len(documents),
        empty_files=tuple(empty_files),
    )


def main() -> None:
    """Index the configured policy directory and print a concise summary."""
    summary = ingest_policies()
    print(json.dumps(asdict(summary), indent=2))


if __name__ == "__main__":
    main()