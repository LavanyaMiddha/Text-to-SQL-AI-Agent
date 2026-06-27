"""
ingestor.py
===========
Ingests the Text-to-SQL knowledge base into a Pinecone hybrid index using
Pinecone Inference for both dense and sparse embeddings — no OpenAI required.

Models used:
  Dense  : llama-text-embed-v2        (1024 dims, dotproduct)
  Sparse : pinecone-sparse-english-v0 (BM25-style, free tier)

Environment variables (.env):
    PINECONE_API_KEY
    PINECONE_INDEX_NAME   (default: financial-agent-kb)
    PINECONE_CLOUD        (default: aws)
    PINECONE_REGION       (default: us-east-1)

Usage:
    python ingestor.py                       # ingest default kb/ directory
    python ingestor.py --kb-dir path/to/kb   # custom directory
    python ingestor.py --dry-run             # parse + preview, no upsert
"""

from __future__ import annotations

import argparse
import os
import time
from collections import Counter
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

from data_loader import Chunk, load_knowledge_base

load_dotenv()

DENSE_MODEL      = "llama-text-embed-v2"
SPARSE_MODEL     = "pinecone-sparse-english-v0"
DENSE_DIMENSIONS = 1024          # llama-text-embed-v2 native dim
UPSERT_BATCH     = 32            # vectors per upsert call (Pinecone max: 100)
EMBED_BATCH      = 16            # texts per inference call (keep < 96 for safety)
SPARSE_MAX_TOKENS = 512          # pinecone-sparse-english-v0 sequence limit



class Ingestor:
    def __init__(self):
        self.pc         = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index_name = os.getenv("PINECONE_INDEX_NAME", "financial-agent-kb")
        self._create_index()
        self.index      = self.pc.Index(self.index_name)


    def _create_index(self) -> None:
        existing = [idx.name for idx in self.pc.list_indexes()]
        if self.index_name in existing:
            print(f"  Index '{self.index_name}' already exists — skipping creation.")
            return

        print(f"  Creating index '{self.index_name}' ...")
        self.pc.create_index(
            name=self.index_name,
            dimension=DENSE_DIMENSIONS,
            metric="dotproduct",      # required for hybrid (dense + sparse)
            spec=ServerlessSpec(
                cloud=os.getenv("PINECONE_CLOUD", "aws"),
                region=os.getenv("PINECONE_REGION", "us-east-1"),
            ),
        )
        while not self.pc.describe_index(self.index_name).status["ready"]:
            print("  Waiting for index to become ready ...")
            time.sleep(5)
        print(f"  Index '{self.index_name}' ready.")


    def _embed_dense_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Dense embeddings via llama-text-embed-v2.
        input_type="passage" for documents being indexed
        (use "query" at retrieval time for asymmetric search).
        """
        response = self.pc.inference.embed(
            model=DENSE_MODEL,
            inputs=texts,
            parameters={
                "input_type": "passage",
                "truncate":   "END",
                "dimension":  DENSE_DIMENSIONS,
            },
        )
        return [item["values"] for item in response]

    def _embed_sparse_batch(self, texts: List[str]) -> List[dict]:
        """
        Sparse embeddings via pinecone-sparse-english-v0.
        Returns list of {"indices": [...], "values": [...]} dicts.
        """
        response = self.pc.inference.embed(
            model=SPARSE_MODEL,
            inputs=texts,
            parameters={
                "input_type":             "passage",
                "truncate":               "END",
                "max_tokens_per_sequence": SPARSE_MAX_TOKENS,
            },
        )
        return [
            {
                "indices": item["sparse_indices"],
                "values":  item["sparse_values"],
            }
            for item in response
        ]

    def _embed_all(self, chunks: List[Chunk]) -> tuple[List[List[float]], List[dict]]:
        """
        Embed all chunks in batches.
        Returns (dense_embeddings, sparse_embeddings) aligned with input chunks.
        """
        texts = [chunk.embed_text for chunk in chunks]
        total = len(texts)

        all_dense:  List[List[float]] = []
        all_sparse: List[dict]        = []

        for i in range(0, total, EMBED_BATCH):
            batch = texts[i : i + EMBED_BATCH]
            batch_end = min(i + EMBED_BATCH, total)
            print(f"    Embedding batch {i+1}–{batch_end} / {total} ...")

            all_dense.extend(self._embed_dense_batch(batch))
            all_sparse.extend(self._embed_sparse_batch(batch))

        return all_dense, all_sparse


    def _build_vectors(
        self,
        chunks:      List[Chunk],
        dense_embs:  List[List[float]],
        sparse_embs: List[dict],
    ) -> List[dict]:
        """
        Assemble Pinecone upsert records.
        Metadata values must be str / int / float / bool / list[str].
        chunk.text (readable) stored in metadata; embed_text is not stored.
        """
        vectors = []
        for chunk, dense, sparse in zip(chunks, dense_embs, sparse_embs):
            metadata = {
                **chunk.metadata,
                "text": chunk.text[:8000],   # cap at 8k chars; Pinecone limit is 40KB
            }
            # Coerce list values to list[str] (Pinecone requirement)
            for key, val in metadata.items():
                if isinstance(val, list):
                    metadata[key] = [str(v) for v in val]

            vectors.append({
                "id":            chunk.id,
                "values":        dense,
                "sparse_values": sparse,
                "metadata":      metadata,
            })

        return vectors


    def _upsert(self, vectors: List[dict]) -> None:
        total = len(vectors)
        for i in range(0, total, UPSERT_BATCH):
            batch = vectors[i : i + UPSERT_BATCH]
            self.index.upsert(vectors=batch)
            print(f"    Upserted {min(i + UPSERT_BATCH, total)}/{total} vectors.")


    def ingest(self, kb_dir: str | Path, dry_run: bool = False) -> None:
        kb_dir = Path(kb_dir)

        print(f"\n{'='*60}")
        print(f"  Text-to-SQL RAG Ingestor")
        print(f"{'='*60}")
        print(f"  KB directory  : {kb_dir.resolve()}")
        print(f"  Index         : {self.index_name}")
        print(f"  Dense model   : {DENSE_MODEL} ({DENSE_DIMENSIONS}d)")
        print(f"  Sparse model  : {SPARSE_MODEL}")
        print(f"  Dry run       : {dry_run}")
        print()

        # Step 1 — Parse all KB files into chunks
        print("[1/4] Loading and parsing knowledge base ...")
        chunks = load_knowledge_base(kb_dir)
        print(f"\n  Total chunks parsed: {len(chunks)}")
        self._print_summary(chunks)

        if dry_run:
            print("\n[DRY RUN] Stopping before embedding. Preview below.\n")
            for i, chunk in enumerate(chunks, 1):
                print(f"  {i:>2}. [{chunk.metadata.get('type', '?'):<18}] {chunk.id}")
                print(f"       embed_text preview: {chunk.embed_text[:120].strip()} ...")
                print()
            return

        # Step 2 — Generate dense + sparse embeddings via Pinecone Inference
        print("\n[2/4] Generating embeddings via Pinecone Inference ...")
        dense_embs, sparse_embs = self._embed_all(chunks)
        print(f"  Dense  : {len(dense_embs)} vectors x {len(dense_embs[0])} dims")
        print(f"  Sparse : {len(sparse_embs)} vectors")

        # Step 3 — Assemble vectors
        print("\n[3/4] Assembling Pinecone records ...")
        vectors = self._build_vectors(chunks, dense_embs, sparse_embs)
        print(f"  Records ready: {len(vectors)}")

        # Step 4 — Upsert
        print(f"\n[4/4] Upserting to index '{self.index_name}' ...")
        self._upsert(vectors)

        # Final stats
        time.sleep(2)
        stats = self.index.describe_index_stats()
        print(f"\n{'='*60}")
        print(f"  Ingest complete.")
        print(f"  Total vectors in index: {stats.total_vector_count}")
        print(f"{'='*60}\n")


    @staticmethod
    def _print_summary(chunks: List[Chunk]) -> None:
        counts = Counter(c.metadata.get("type", "unknown") for c in chunks)
        for chunk_type, count in sorted(counts.items()):
            print(f"    {chunk_type:<22} {count:>3} chunk(s)")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest KB into Pinecone hybrid index.")
    parser.add_argument(
        "--kb-dir",
        default="kb",
        help="Path to knowledge base directory (.yaml and .md files).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and preview chunks without embedding or upserting.",
    )
    args = parser.parse_args()

    ingestor = Ingestor()
    ingestor.ingest(kb_dir=args.kb_dir, dry_run=args.dry_run)