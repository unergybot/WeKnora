"""
QA pair generation using local LLM (Ollama).

Generates synthetic questions and answers based on document chunks.
"""

import json
import random
import time
import uuid
from typing import List, Optional

import requests

from .models import Chunk, QAPair, QueryType


class QAGenerator:
    """Generate QA pairs from document chunks using LLM."""

    # Prompt templates for different query types
    PROMPTS = {
        QueryType.FACT_RETRIEVAL: """
            Context: {context}
            
            Generate a factual question that can be answered solely using the information above. 
            The question should ask for specific details like numbers, dates, or named entities.
            Also provide the answer.
            
            Format: JSON with keys "question", "answer"
        """,
        QueryType.CONCEPT_EXPLANATION: """
            Context: {context}
            
            Generate a question that asks for an explanation of a concept, process, or strategy mentioned in the text.
            The answer should synthesize information from the context.
            
            Format: JSON with keys "question", "answer"
        """,
        QueryType.MULTI_HOP_REASONING: """
            Context: {context}
            
            Generate a complex question that requires connecting multiple pieces of information from the context.
            For example, "How did X affect Y?" or "What are the causes of Z?"
            
            Format: JSON with keys "question", "answer"
        """,
        QueryType.TEMPORAL_COMPARISON: """
            Context: {context}
            
            Generate a question that asks about time-related changes, trends, or comparisons (e.g., year-over-year).
            If no temporal info exists, generate a standard factual question instead.
            
            Format: JSON with keys "question", "answer"
        """,
        QueryType.OUT_OF_SCOPE: """
            Context: {context}
            
            Generate a plausible-sounding question that is related to the topic but CANNOT be answered by the context provided.
            The answer should clearly state that the information is not available in the context.
            
            Format: JSON with keys "question", "answer"
        """
    }

    # Default distribution of query types
    DEFAULT_DISTRIBUTION = {
        QueryType.FACT_RETRIEVAL: 0.3,
        QueryType.CONCEPT_EXPLANATION: 0.2,
        QueryType.MULTI_HOP_REASONING: 0.25,
        QueryType.TEMPORAL_COMPARISON: 0.15,
        QueryType.OUT_OF_SCOPE: 0.1
    }

    def __init__(self, ollama_url: str = "http://localhost:11434", model: str = "qwen2.5:14b"):
        """
        Initialize QA generator.

        Args:
            ollama_url: URL of local Ollama instance
            model: Model name to use
        """
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

    def generate(self, chunks: List[Chunk], num_pairs: int = 50, 
                distribution: Optional[dict] = None) -> List[QAPair]:
        """
        Generate QA pairs from provided chunks.

        Args:
            chunks: List of text chunks to generate from
            num_pairs: Total number of pairs to generate
            distribution: Optional override for query type distribution
        """
        qa_pairs = []
        dist = distribution or self.DEFAULT_DISTRIBUTION
        
        # Calculate counts for each type
        counts = {k: int(v * num_pairs) for k, v in dist.items()}
        
        # Adjust to match total exactly
        current_total = sum(counts.values())
        if current_total < num_pairs:
            counts[QueryType.FACT_RETRIEVAL] += (num_pairs - current_total)
            
        print(f"Generating {num_pairs} QA pairs with model {self.model}...")
        
        chunk_pool = chunks.copy()
        random.shuffle(chunk_pool)
        
        chunk_idx = 0
        for q_type, count in counts.items():
            generated = 0
            retries = 0
            max_retries = count * 2
            
            while generated < count and chunk_idx < len(chunks) and retries < max_retries:
                chunk = chunk_pool[chunk_idx % len(chunk_pool)]
                chunk_idx += 1
                
                # Skip very short chunks
                if len(chunk.text) < 100:
                    continue
                    
                qa = self._generate_single_pair(chunk, q_type)
                if qa:
                    qa_pairs.append(qa)
                    generated += 1
                    print(f"Generated {q_type.name} pair ({generated}/{count})")
                else:
                    retries += 1
                    
        return qa_pairs

    def _generate_single_pair(self, chunk: Chunk, q_type: QueryType) -> Optional[QAPair]:
        """Generate a single QA pair for a chunk."""
        prompt_tmpl = self.PROMPTS.get(q_type, self.PROMPTS[QueryType.FACT_RETRIEVAL])
        prompt = prompt_tmpl.format(context=chunk.text)
        
        try:
            resp = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                     "options": {
                        "temperature": 0.7
                    }
                },
                timeout=30
            )
            
            if resp.status_code != 200:
                print(f"Ollama API error: {resp.text}")
                return None
                
            result = resp.json()
            response_text = result.get("response", "")
            
            # Parse JSON response
            try:
                data = json.loads(response_text)
                question = data.get("question")
                answer = data.get("answer")
                
                if not question or not answer:
                    return None
                    
                return QAPair(
                    id=f"qa_{uuid.uuid4().hex[:8]}",
                    question=question,
                    answer=answer,
                    query_type=q_type,
                    context_chunk_ids=[chunk.id],
                    difficulty=self._estimate_difficulty(q_type),
                    source_doc_ids=[chunk.doc_id],
                    metadata={
                        "model": self.model,
                        "chunk_start": chunk.start_idx,
                        "chunk_end": chunk.end_idx
                    }
                )
                
            except json.JSONDecodeError:
                print("Failed to parse LLM JSON response")
                return None
                
        except Exception as e:
            print(f"Generation error: {e}")
            return None

    def _estimate_difficulty(self, q_type: QueryType) -> int:
        """Estimate difficulty 1-5 based on query type."""
        mapping = {
            QueryType.FACT_RETRIEVAL: 1,
            QueryType.CONCEPT_EXPLANATION: 3,
            QueryType.MULTI_HOP_REASONING: 5,
            QueryType.TEMPORAL_COMPARISON: 4,
            QueryType.OUT_OF_SCOPE: 2
        }
        return mapping.get(q_type, 3)
