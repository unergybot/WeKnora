"""
Benchmark evaluation runner.

Evaluates WeKnora RAG performance against golden dataset.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from .models import BenchmarkResult, GoldenDataset


class WeKnoraClient:
    """Client for interacting with WeKnora API."""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        })

    def query(self, text: str) -> dict:
        """Send query to WeKnora."""
        try:
            start_time = time.time()
            resp = self.session.post(
                f"{self.base_url}/api/chat",
                json={
                    "messages": [{"role": "user", "content": text}],
                    "stream": False,
                    # Request debug info / retrieval context if API supports it
                    "include_context": True 
                },
                timeout=60
            )
            latency = (time.time() - start_time) * 1000
            
            if resp.status_code != 200:
                return {
                    "error": f"API Error: {resp.status_code}",
                    "latency_ms": latency
                }
                
            data = resp.json()
            return {
                "answer": data.get("content", ""),
                "context": data.get("context", []),  # Adjusted based on actual API
                "latency_ms": latency,
                "success": True
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "latency_ms": 0,
                "success": False
            }


class BenchmarkRunner:
    """Runs evaluation benchmark."""

    def __init__(self, weknora_url: str, api_key: str):
        self.client = WeKnoraClient(weknora_url, api_key)

    def run(self, dataset_path: str) -> BenchmarkResult:
        """
        Run benchmark against dataset.
        
        Args:
            dataset_path: Path to dataset directory (containing parquet files)
        """
        print(f"Loading dataset from {dataset_path}...")
        queries = pd.read_parquet(f"{dataset_path}/queries.parquet")
        answers = pd.read_parquet(f"{dataset_path}/answers.parquet")
        qas = pd.read_parquet(f"{dataset_path}/qas.parquet")
        
        # Load metadata if available
        meta_path = Path(dataset_path) / "metadata.json"
        metadata = {}
        if meta_path.exists():
            with open(meta_path) as f:
                metadata = json.load(f)
                
        results = []
        latencies = []
        
        print(f"Starting benchmark on {len(queries)} queries...")
        
        for _, row in queries.iterrows():
            qid = row["id"]
            question = row["text"]
            
            # Get ground truth
            aid = qas[qas["qid"] == qid]["aid"].values[0]
            ground_truth = answers[answers["id"] == aid]["text"].values[0]
            
            # Query system
            response = self.client.query(question)
            
            if response.get("success"):
                latencies.append(response["latency_ms"])
                
                # Basic exact match/similarity check (placeholder for RAGAS)
                # In full implementation, RAGAS would compute scores here
                
                results.append({
                    "qid": qid,
                    "question": question,
                    "generated_answer": response["answer"],
                    "ground_truth": ground_truth,
                    "latency_ms": response["latency_ms"],
                    "error": None
                })
                print(f"Processed: {qid} ({response['latency_ms']:.1f}ms)")
            else:
                results.append({
                    "qid": qid,
                    "question": question,
                    "generated_answer": "",
                    "ground_truth": ground_truth,
                    "latency_ms": 0,
                    "error": response.get("error")
                })
                print(f"Failed: {qid} - {response.get('error')}")

        # Compute aggregate metrics
        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.5)] if latencies else 0
        p95 = latencies[int(len(latencies) * 0.95)] if latencies else 0
        p99 = latencies[int(len(latencies) * 0.99)] if latencies else 0
        
        return BenchmarkResult(
            dataset_name=metadata.get("name", "unknown"),
            dataset_hash=metadata.get("hash", "unknown"),
            timestamp=datetime.now(),
            retrieval_metrics={},
            generation_metrics={},  # Populate with RAGAS results
            performance_metrics={
                "latency_p50": p50,
                "latency_p95": p95,
                "latency_p99": p99,
                "success_rate": len(latencies) / len(queries) if queries is not None else 0
            },
            per_query_results=results
        )

    def export_report(self, result: BenchmarkResult, output_dir: str):
        """Generate markdown report."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        
        report = f"""# Benchmark Report: {result.dataset_name}

**Date:** {result.timestamp}
**Dataset Hash:** {result.dataset_hash}

## Performance Metrics
- **P50 Latency:** {result.performance_metrics['latency_p50']:.1f}ms
- **P95 Latency:** {result.performance_metrics['latency_p95']:.1f}ms
- **P99 Latency:** {result.performance_metrics['latency_p99']:.1f}ms
- **Success Rate:** {result.performance_metrics['success_rate'] * 100:.1f}%

## Query Results (Sample)

| Query | Latency | Status |
|-------|---------|--------|
"""
        
        for res in result.per_query_results[:10]:
            status = "✅" if not res["error"] else "❌"
            report += f"| {res['question'][:50]}... | {res['latency_ms']:.1f}ms | {status} |\n"

        (out_path / "report.md").write_text(report)
        
        # Save full results JSON
        with open(out_path / "results.json", "w") as f:
            json.dump(result.to_dict(), f, indent=2)
            
        print(f"Report saved to {output_dir}/report.md")
