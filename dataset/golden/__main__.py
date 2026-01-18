"""
CLI entry point for golden dataset tools.
"""

import argparse
import sys
from pathlib import Path

from .collector import PDFCollector, SECCollector, TechDocCollector
from .processor import DocumentProcessor
from .qa_generator import QAGenerator
from .dataset_builder import GoldenDatasetBuilder
from .benchmark import BenchmarkRunner


def collect_command(args):
    """Run data collection."""
    print(f"Starting data collection to {args.output_dir}...")
    
    docs = []
    
    # 1. SEC Filings
    if not args.skip_sec:
        print("Collecting SEC filings...")
        sec_collector = SECCollector(years=[2023, 2024])
        docs.extend(sec_collector.collect(args.output_dir, limit=args.limit))
        
    # 2. Tech Docs
    if not args.skip_docs:
        print("Collecting technical documentation...")
        tech_collector = TechDocCollector()
        docs.extend(tech_collector.collect(args.output_dir, limit=args.limit))
        
    # 3. PDF Docs
    if not args.skip_pdf:
        print("Collecting PDF documents...")
        pdf_collector = PDFCollector()
        docs.extend(pdf_collector.collect(args.output_dir, limit=args.limit))
        
    print(f"Collected total {len(docs)} documents.")


def process_command(args):
    """Process collected documents."""
    print(f"Processing documents from {args.input_dir}...")
    input_path = Path(args.input_dir)
    
    # Reload documents (simplified for now as just text files)
    # In reality, would load from metadata or specialized format
    pass 
    # Skipping implementation for now to focus on main pipeline structure
    # This step is implicitly handled during generation in current flow
    print("Processing step integrated into generation.")


def generate_command(args):
    """Generate golden dataset."""
    print(f"Generating dataset from {args.input_dir}...")
    
    # Load raw documents
    input_path = Path(args.input_dir)
    raw_docs = []
    
    # Simple loader for demo purposes
    # In production, use proper serialization
    from .models import Document, DocumentType
    
    for f in input_path.glob("*.txt"):
        content = f.read_text(encoding="utf-8")
        raw_docs.append(Document(
            id=f.stem,
            source=str(f),
            doc_type=DocumentType.TECHNICAL_DOC, # simplified
            content=content
        ))
        if len(raw_docs) >= 10: # Limit for safety
            break
            
    if not raw_docs:
        print("No documents found in input directory!")
        return

    # Process documents
    processor = DocumentProcessor()
    processed_docs = [processor.process(d) for d in raw_docs]
    
    # Collect all chunks
    all_chunks = []
    for d in processed_docs:
        all_chunks.extend(d.chunks)
        
    print(f"Created {len(all_chunks)} chunks from {len(raw_docs)} documents.")
    
    # Generate QA pairs
    generator = QAGenerator(ollama_url=args.ollama_url, model=args.model)
    qa_pairs = generator.generate(all_chunks, num_pairs=args.num_pairs)
    
    # Build and export
    builder = GoldenDatasetBuilder()
    dataset = builder.build("golden_v1", qa_pairs, processed_docs, raw_docs)
    builder.export(dataset, args.output_dir)


def benchmark_command(args):
    """Run benchmark."""
    runner = BenchmarkRunner(args.weknora_url, args.api_key)
    result = runner.run(args.dataset_dir)
    runner.export_report(result, args.output_dir)


def main():
    parser = argparse.ArgumentParser(description="Golden Dataset Tools")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Collect
    collect_parser = subparsers.add_parser("collect", help="Collect raw documents")
    collect_parser.add_argument("--output-dir", required=True)
    collect_parser.add_argument("--limit", type=int, default=5)
    collect_parser.add_argument("--skip-sec", action="store_true")
    collect_parser.add_argument("--skip-docs", action="store_true")
    collect_parser.add_argument("--skip-pdf", action="store_true")
    collect_parser.set_defaults(func=collect_command)
    
    # Process
    process_parser = subparsers.add_parser("process", help="Process documents")
    process_parser.add_argument("--input-dir", required=True)
    process_parser.add_argument("--output-dir", required=True)
    process_parser.set_defaults(func=process_command)
    
    # Generate
    gen_parser = subparsers.add_parser("generate", help="Generate golden dataset")
    gen_parser.add_argument("--input-dir", required=True)
    gen_parser.add_argument("--output-dir", required=True)
    gen_parser.add_argument("--num-pairs", type=int, default=50)
    gen_parser.add_argument("--ollama-url", default="http://localhost:11434")
    gen_parser.add_argument("--model", default="qwen2.5:14b")
    gen_parser.set_defaults(func=generate_command)
    
    # Benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Run benchmark")
    bench_parser.add_argument("--dataset-dir", required=True)
    bench_parser.add_argument("--output-dir", required=True)
    bench_parser.add_argument("--weknora-url", default="http://localhost:8080")
    bench_parser.add_argument("--api-key", default="")
    bench_parser.set_defaults(func=benchmark_command)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
