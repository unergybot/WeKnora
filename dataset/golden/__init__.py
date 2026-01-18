# Golden Dataset Generation Module
"""
Tools for generating golden datasets from open enterprise materials
for benchmarking WeKnora's RAG capabilities.

Usage:
    python -m dataset.golden collect --output-dir ./dataset/golden/raw
    python -m dataset.golden generate --input-dir ./dataset/golden/raw --num-pairs 200
    python -m dataset.golden benchmark --dataset-dir ./dataset/golden/dataset
"""

from .models import Document, ProcessedDocument, Chunk, QAPair, GoldenDataset
from .collector import SECCollector, TechDocCollector
from .processor import DocumentProcessor
from .qa_generator import QAGenerator
from .dataset_builder import GoldenDatasetBuilder

__all__ = [
    "Document",
    "ProcessedDocument", 
    "Chunk",
    "QAPair",
    "GoldenDataset",
    "SECCollector",
    "TechDocCollector",
    "DocumentProcessor",
    "QAGenerator",
    "GoldenDatasetBuilder",
]
