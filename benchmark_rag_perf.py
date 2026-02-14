#!/usr/bin/env python3
"""
Benchmark script to measure RAG similarity search performance improvement.
Tests the vectorized numpy implementation vs the old loop-based approach.
"""

import time
import numpy as np
from src.ml.embeddings import bytes_to_embedding, embedding_to_bytes, cosine_similarity

def benchmark_old_approach(query_embedding, embeddings_list, threshold=0.35):
    """Original O(n*m) loop implementation - similarity computation only."""
    results = []
    for i, stored_vec in enumerate(embeddings_list):
        raw_score = cosine_similarity(query_embedding, stored_vec)
        if raw_score >= threshold:
            results.append((i, raw_score))
    return results

def benchmark_new_approach(query_embedding, embeddings_matrix, threshold=0.35):
    """Vectorized numpy implementation - similarity computation only."""
    # Vectorized cosine similarity
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    emb_norms = embeddings_matrix / np.linalg.norm(embeddings_matrix, axis=1, keepdims=True)
    similarities = np.dot(emb_norms, query_norm)

    # Filter and return
    results = [
        (i, float(similarities[i]))
        for i in range(len(similarities))
        if similarities[i] >= threshold
    ]
    return results

def run_benchmark(num_chunks=1000):
    """Run performance comparison."""
    # Generate test data
    embedding_dim = 384

    print(f"Generating {num_chunks} test embeddings (dim={embedding_dim})...")

    # Create query embedding (NOT pre-normalized to match real-world usage)
    query_embedding = np.random.randn(embedding_dim).astype(np.float32)

    # Create test embeddings (NOT pre-normalized to match real-world storage)
    embeddings_list = []
    for i in range(num_chunks):
        emb = np.random.randn(embedding_dim).astype(np.float32)
        embeddings_list.append(emb)

    # Pre-convert to matrix for vectorized approach
    embeddings_matrix = np.array(embeddings_list)

    print(f"\nBenchmarking similarity computation with {num_chunks} embeddings...")

    # Benchmark old approach (loop-based cosine similarity)
    iterations = 100  # More iterations since this is faster
    old_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        old_results = benchmark_old_approach(query_embedding, embeddings_list)
        old_times.append((time.perf_counter() - start) * 1000)  # Convert to ms

    old_avg = sum(old_times) / len(old_times)

    # Benchmark new approach (vectorized)
    new_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        new_results = benchmark_new_approach(query_embedding, embeddings_matrix)
        new_times.append((time.perf_counter() - start) * 1000)  # Convert to ms

    new_avg = sum(new_times) / len(new_times)

    # Verify results are equivalent
    old_ids = sorted([r[0] for r in old_results])
    new_ids = sorted([r[0] for r in new_results])

    print("\n" + "="*60)
    print("PERFORMANCE COMPARISON (Similarity Computation)")
    print("="*60)
    print(f"Old approach (loop):        {old_avg:.3f}ms (avg of {iterations} runs)")
    print(f"New approach (vectorized):  {new_avg:.3f}ms (avg of {iterations} runs)")
    print(f"Speedup:                    {old_avg/new_avg:.1f}x faster")
    print(f"Time saved per query:       {old_avg - new_avg:.3f}ms")
    print(f"\nResults match:              {old_ids == new_ids}")
    print(f"Number of results:          {len(old_results)}")

    # Calculate what this means at 50-200ms baseline
    print(f"\nReal-world impact:")
    print(f"  Old baseline: 50-200ms per query")
    print(f"  Expected new: {50/old_avg*new_avg:.1f}-{200/old_avg*new_avg:.1f}ms per query")
    print("="*60)

    if old_avg / new_avg >= 10:
        print("✓ PERF-001: Achieved 10-50x speedup target!")
    elif old_avg / new_avg >= 5:
        print(f"✓ Good speedup: {old_avg/new_avg:.1f}x (approaching target)")
    else:
        print(f"⚠ Speedup is {old_avg/new_avg:.1f}x (target: 10-50x)")

    return old_avg / new_avg

if __name__ == "__main__":
    print("\nPERF-001: RAG Similarity Search Optimization Benchmark")
    print("Testing vectorized numpy vs loop-based approach\n")

    for size in [100, 500, 1000, 2000]:
        print(f"\n{'='*60}")
        print(f"Dataset size: {size} chunks")
        print('='*60)
        speedup = run_benchmark(size)
