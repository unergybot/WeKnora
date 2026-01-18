"""
Document processor for text extraction and chunking.

Integrates with WeKnora's docreader where available.
"""

import re
import uuid
from typing import List

from .models import Chunk, Document, DocumentType, ProcessedDocument


class DocumentProcessor:
    """Process raw documents into cleaning text and chunks."""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        """
        Initialize processor.

        Args:
            chunk_size: Target characters per chunk
            chunk_overlap: Overlap characters between chunks
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def process(self, doc: Document) -> ProcessedDocument:
        """
        Process a raw document.

        1. Clean and normalize text
        2. Identify sections (basic heirarchy)
        3. Split into chunks for embedding/retrieval
        """
        # Clean text
        text = self._normalize_text(doc.content)
        
        # Identify sections based on doc type
        sections = self._identify_sections(text, doc.doc_type)
        
        # Create processed doc container
        proc_doc = ProcessedDocument(
            id=f"proc_{doc.id}",
            source_doc_id=doc.id,
            text=text,
            sections=sections,
            metadata=doc.metadata,
        )
        
        # Chunk text
        chunks = self._chunk_text(proc_doc)
        proc_doc.chunks = chunks
        
        return proc_doc

    def _normalize_text(self, text: str) -> str:
        """Clean and normalize text content."""
        if not text:
            return ""
            
        # Replace multiple newlines with double newline (preserve paragraphs)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Replace multiple spaces with single space
        text = re.sub(r' {2,}', ' ', text)
        
        # Remove control characters but keep newlines/tabs
        text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ch >= " ")
        
        return text.strip()

    def _identify_sections(self, text: str, doc_type: DocumentType) -> list[dict]:
        """Identify sections for hierarchical indexing."""
        sections = []
        
        if doc_type == DocumentType.SEC_FILING:
            # Matches "Item 1. Business", "Item 7.", etc.
            pattern = r'(?:^|\n)(Item\s+\d+(?:[A-Z])?[\.\:]?\s*[^\n]+)'
            matches = re.finditer(pattern, text)
            for m in matches:
                sections.append({
                    "title": m.group(1).strip(),
                    "start_idx": m.start(),
                })
                
        elif doc_type in (DocumentType.TECHNICAL_DOC, DocumentType.MARKDOWN):
            # Markdown headers
            pattern = r'(?:^|\n)(#{1,6}\s+[^\n]+)'
            matches = re.finditer(pattern, text)
            for m in matches:
                sections.append({
                    "title": m.group(1).strip(),
                    "start_idx": m.start(),
                })
                
        return sections

    def _chunk_text(self, doc: ProcessedDocument) -> List[Chunk]:
        """Split document text into overlapping chunks."""
        text = doc.text
        chunks = []
        
        if not text:
            return chunks
            
        start = 0
        text_len = len(text)
        
        while start < text_len:
            # Determine end position
            end = min(start + self.chunk_size, text_len)
            
            # If not at end, try to break at newline or space
            if end < text_len:
                # Try finding double newline (paragraph break)
                next_db_nl = text.rfind('\n\n', start, end)
                if next_db_nl != -1 and next_db_nl > start + self.chunk_size * 0.5:
                    end = next_db_nl + 2
                else:
                    # Try newline
                    next_nl = text.rfind('\n', start, end)
                    if next_nl != -1 and next_nl > start + self.chunk_size * 0.5:
                        end = next_nl + 1
                    else:
                        # Try space
                        next_space = text.rfind(' ', start, end)
                        if next_space != -1 and next_space > start + self.chunk_size * 0.5:
                            end = next_space + 1
            
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(Chunk(
                    id=f"chunk_{doc.source_doc_id}_{len(chunks)}",
                    doc_id=doc.source_doc_id,
                    text=chunk_text,
                    start_idx=start,
                    end_idx=end,
                    metadata=doc.metadata.copy()
                ))
            
            # Update start position with overlap
            start = end - self.chunk_overlap
            
            # Ensure we move forward
            if start >= end:
                start = end
                
        return chunks
