"""
Golden dataset builder and exporter.

Handles dataset versioning and Parquet export.
"""

import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from .models import GoldenDataset, ProcessedDocument, QAPair, Chunk, Document


class GoldenDatasetBuilder:
    """Build and export golden datasets."""

    def build(self, 
              name: str, 
              qa_pairs: list[QAPair], 
              documents: list[ProcessedDocument],
              raw_docs: list[Document]) -> GoldenDataset:
        """
        Assemble a golden dataset from components.
        """
        # Collect all chunks from processed documents
        all_chunks = []
        for doc in documents:
            all_chunks.extend(doc.chunks)

        version = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        return GoldenDataset(
            name=name,
            version=version,
            qa_pairs=qa_pairs,
            chunks=all_chunks,
            documents=raw_docs,
            metadata={
                "created_by": "dataset.golden",
                "schema_version": "1.0"
            }
        )

    def export(self, dataset: GoldenDataset, output_dir: str) -> None:
        """
        Export dataset to directory in WeKnora compatible format.
        
        Files created:
        - queries.parquet: id, text
        - corpus.parquet: id, text
        - qrels.parquet: qid, pid
        - answers.parquet: id, text
        - qas.parquet: qid, aid
        - metadata.json: Dataset info
        """
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        # 1. Queries (Questions)
        queries_df = pd.DataFrame([
            {"id": qa.id, "text": qa.question} 
            for qa in dataset.qa_pairs
        ])
        
        # 2. Corpus (Chunks/Documents acting as passages)
        # Using chunks as valid retrieval targets
        corpus_df = pd.DataFrame([
            {"id": chunk.id, "text": chunk.text, "doc_id": chunk.doc_id}
            for chunk in dataset.chunks
        ])
        
        # 3. Qrels (Relevance Judgments)
        qrels_data = []
        for qa in dataset.qa_pairs:
            for chunk_id in qa.context_chunk_ids:
                qrels_data.append({
                    "qid": qa.id,
                    "pid": chunk_id,
                    "relevance": 1  # Binary relevance for now
                })
        qrels_df = pd.DataFrame(qrels_data)
        
        # 4. Answers (Reference answers)
        # Creating IDs for answers (qa_id + suffix)
        answers_data = []
        qa_map_data = []
        
        for qa in dataset.qa_pairs:
            aid = f"ans_{qa.id}"
            answers_data.append({
                "id": aid, 
                "text": qa.answer
            })
            qa_map_data.append({
                "qid": qa.id,
                "aid": aid
            })
            
        answers_df = pd.DataFrame(answers_data)
        qas_df = pd.DataFrame(qa_map_data)
        
        # Save Parquet files
        queries_df.to_parquet(out_path / "queries.parquet")
        corpus_df.to_parquet(out_path / "corpus.parquet")
        qrels_df.to_parquet(out_path / "qrels.parquet")
        answers_df.to_parquet(out_path / "answers.parquet")
        qas_df.to_parquet(out_path / "qas.parquet")
        
        # Save Metadata
        full_metadata = dataset.stats
        full_metadata.update({
            "name": dataset.name,
            "version": dataset.version,
            "hash": dataset.hash,
            "exported_at": datetime.now().isoformat()
        })
        
        with open(out_path / "metadata.json", "w") as f:
            json.dump(full_metadata, f, indent=2)
            
        print(f"Dataset exported to {output_dir}")
        print(f"Stats: {dataset.stats}")
