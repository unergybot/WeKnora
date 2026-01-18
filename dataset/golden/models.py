"""
Data models for the golden dataset generation pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib
import json


class DocumentType(Enum):
    """Types of source documents."""
    SEC_FILING = "sec_filing"
    TECHNICAL_DOC = "technical_doc"
    INVESTOR_RELATIONS = "investor_relations"
    PDF = "pdf"
    MARKDOWN = "markdown"


class QueryType(Enum):
    """Types of generated queries by difficulty."""
    FACT_RETRIEVAL = "fact_retrieval"  # 30% - Low complexity
    CONCEPT_EXPLANATION = "concept_explanation"  # 20% - Medium
    MULTI_HOP_REASONING = "multi_hop_reasoning"  # 25% - High
    TEMPORAL_COMPARISON = "temporal_comparison"  # 15% - High  
    OUT_OF_SCOPE = "out_of_scope"  # 10% - Should refuse


@dataclass
class Document:
    """Raw document collected from a source."""
    id: str
    source: str
    doc_type: DocumentType
    content: str
    metadata: dict = field(default_factory=dict)
    collected_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "doc_type": self.doc_type.value,
            "content": self.content,
            "metadata": self.metadata,
            "collected_at": self.collected_at.isoformat(),
        }


@dataclass
class Chunk:
    """A text chunk from a processed document."""
    id: str
    doc_id: str
    text: str
    start_idx: int
    end_idx: int
    metadata: dict = field(default_factory=dict)


@dataclass
class ProcessedDocument:
    """Document after text extraction and normalization."""
    id: str
    source_doc_id: str
    text: str
    sections: list[dict] = field(default_factory=list)
    tables: list[dict] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class QAPair:
    """A question-answer pair for the golden dataset."""
    id: str
    question: str
    answer: str
    query_type: QueryType
    context_chunk_ids: list[str]
    difficulty: int  # 1-5 scale
    source_doc_ids: list[str]
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "query_type": self.query_type.value,
            "context_chunk_ids": self.context_chunk_ids,
            "difficulty": self.difficulty,
            "source_doc_ids": self.source_doc_ids,
            "metadata": self.metadata,
        }


@dataclass
class GoldenDataset:
    """Complete golden dataset with versioning."""
    name: str
    version: str
    qa_pairs: list[QAPair]
    chunks: list[Chunk]
    documents: list[Document]
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)

    @property
    def hash(self) -> str:
        """Generate unique hash for dataset versioning."""
        data = json.dumps(
            [qa.to_dict() for qa in self.qa_pairs],
            sort_keys=True
        )
        return hashlib.sha256(data.encode()).hexdigest()[:12]

    @property
    def stats(self) -> dict:
        """Dataset statistics."""
        type_counts = {}
        for qa in self.qa_pairs:
            t = qa.query_type.value
            type_counts[t] = type_counts.get(t, 0) + 1

        difficulty_counts = {}
        for qa in self.qa_pairs:
            d = qa.difficulty
            difficulty_counts[d] = difficulty_counts.get(d, 0) + 1

        return {
            "total_qa_pairs": len(self.qa_pairs),
            "total_chunks": len(self.chunks),
            "total_documents": len(self.documents),
            "query_type_distribution": type_counts,
            "difficulty_distribution": difficulty_counts,
        }


@dataclass
class BenchmarkResult:
    """Results from running a benchmark evaluation."""
    dataset_name: str
    dataset_hash: str
    timestamp: datetime
    retrieval_metrics: dict  # context_recall, context_precision, nDCG@10
    generation_metrics: dict  # faithfulness, answer_relevancy
    performance_metrics: dict  # latency_p50, p95, p99
    per_query_results: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dataset_name": self.dataset_name,
            "dataset_hash": self.dataset_hash,
            "timestamp": self.timestamp.isoformat(),
            "retrieval_metrics": self.retrieval_metrics,
            "generation_metrics": self.generation_metrics,
            "performance_metrics": self.performance_metrics,
            "per_query_results": self.per_query_results,
        }
