"""
data_loader.py
==============
Parses knowledge base files into typed, self-contained chunks ready for
embedding. Two public functions:

    load_yaml_table_schema(path)  ->  List[Chunk]   (1 chunk per file)
    load_markdown_file(path)      ->  List[Chunk]   (split by ## or **Term**)

Each Chunk is a dataclass with:
    id          : stable unique ID for upsert deduplication
    text        : the string that gets embedded
    embed_text  : prefix-augmented version sent to the embedding model
    metadata    : dict stored alongside the vector in Pinecone
"""

from __future__ import annotations

import re
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Chunk dataclass
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    id: str
    text: str           # raw readable text (stored in metadata for display)
    embed_text: str     # prefix-augmented text sent to embedding model
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Embedding prefix map
# Prepended to embed_text to pull chunk types apart in embedding space.
# ---------------------------------------------------------------------------

PREFIX_MAP = {
    "table_schema":    "SQL schema definition for table: ",
    "join_path":       "SQL join pattern: ",
    "query_pattern":   "Business metric SQL query pattern: ",
    "business_metric": "Financial business metric definition with SQL: ",
    "glossary_term":   "Financial term definition: ",
    "sql_guardrail":   "SQL generation rule: ",
    "relationship":    "Database relationship context: ",
}


# ---------------------------------------------------------------------------
# YAML parser  — one chunk per file
# ---------------------------------------------------------------------------

def load_yaml_table_schema(path: str | Path) -> List[Chunk]:
    """
    Parse a single per-table YAML file into exactly one Chunk.

    The chunk text is a human-readable serialization of:
      - table name + description
      - all columns with type / nullable / description / sample_values
      - foreign keys with join hints
      - query_notes
      - sample_queries (intent + sql)

    This keeps the entire table context in one retrievable unit.
    """
    path = Path(path)
    with open(path) as f:
        doc = yaml.safe_load(f)

    db = doc.get("database", {})
    tbl = doc.get("table", {})

    table_name = tbl.get("table_name", path.stem)
    lines: List[str] = []

    # --- header ---
    lines.append(f"Table: {table_name}")
    lines.append(f"Database: {db.get('name', 'unknown')} ({db.get('engine', 'unknown')})")
    if tbl.get("description"):
        lines.append(f"Description: {tbl['description'].strip()}")

    pk = tbl.get("primary_key")
    ck = tbl.get("composite_key")
    if pk:
        lines.append(f"Primary Key: {pk}")
    elif ck:
        lines.append(f"Composite Key: {', '.join(ck)}")

    # --- columns ---
    lines.append("\nColumns:")
    for col_name, col in (tbl.get("columns") or {}).items():
        nullable = "nullable" if col.get("nullable", True) else "NOT NULL"
        line = f"  {col_name} ({col.get('type', 'TEXT')}, {nullable}): {col.get('description', '').strip()}"
        if col.get("sample_values"):
            line += f"  | sample values: {col['sample_values']}"
        lines.append(line)

    # --- foreign keys ---
    fks = tbl.get("foreign_keys") or []
    if fks:
        lines.append("\nForeign Keys:")
        for fk in fks:
            lines.append(
                f"  {fk['column']} -> {fk['references_table']}.{fk['references_column']}"
                f"  | hint: {fk.get('join_hint', '')}"
            )

    # --- query notes ---
    if tbl.get("query_notes"):
        lines.append(f"\nQuery Notes:\n  {tbl['query_notes'].strip()}")

    # --- sample queries ---
    sample_queries = tbl.get("sample_queries") or []
    if sample_queries:
        lines.append("\nSample Queries:")
        for sq in sample_queries:
            lines.append(f"  Intent: {sq.get('intent', '')}")
            sql = sq.get("sql", "").strip()
            lines.append(f"  SQL:\n{_indent(sql, 4)}")

    text = "\n".join(lines)
    chunk_type = "table_schema"

    return [
        Chunk(
            id=f"schema::{table_name}",
            text=text,
            embed_text=PREFIX_MAP[chunk_type] + table_name + "\n" + text,
            metadata={
                "source": str(path.name),
                "type": chunk_type,
                "table_name": table_name,
                "database": db.get("name", ""),
                "engine": db.get("engine", ""),
                # related_tables extracted from FK references — enables
                # secondary fetch: "I got transactions, also pull accounts"
                "related_tables": [
                    fk["references_table"]
                    for fk in fks
                ],
                "has_sample_queries": bool(sample_queries),
            },
        )
    ]


# ---------------------------------------------------------------------------
# Markdown parser  — split strategy depends on file type
# ---------------------------------------------------------------------------

def load_markdown_file(path: str | Path) -> List[Chunk]:
    """
    Route to the correct markdown splitter based on filename.

    query_patterns.md    -> one chunk per ## Pattern block
    business_metrics.md  -> one chunk per ### metric block
    business_glossary.md -> one chunk per **Term** block
    relationships*.md    -> one chunk per ## section
    sql_guardrails.md    -> one chunk per ## section
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    name = path.stem.lower()

    if "query_pattern" in name:
        return _split_query_patterns(text, path)
    elif "business_metric" in name:
        return _split_business_metrics(text, path)
    elif "glossary" in name:
        return _split_glossary(text, path)
    elif "relationship" in name:
        return _split_by_h2(text, path, chunk_type="relationship")
    elif "guardrail" in name:
        return _split_by_h2(text, path, chunk_type="sql_guardrail")
    else:
        # Generic fallback: split by ## headers
        return _split_by_h2(text, path, chunk_type="relationship")


# ---------------------------------------------------------------------------
# Markdown splitters
# ---------------------------------------------------------------------------

def _split_query_patterns(text: str, path: Path) -> List[Chunk]:
    """
    Split query_patterns.md by ## Pattern blocks.
    Each chunk preserves: pattern id, intent, tables, trigger phrases, SQL.
    """
    # Split on ## headers (each pattern starts with ## Pattern NN)
    blocks = re.split(r"\n(?=## Pattern)", text)
    chunks: List[Chunk] = []

    for block in blocks:
        block = block.strip()
        if not block or block.startswith("#") and "Pattern" not in block:
            continue

        # Extract header line
        header_match = re.match(r"## (.+)", block)
        if not header_match:
            continue
        header = header_match.group(1).strip()

        # Extract structured fields
        intent = _extract_field(block, "Intent")
        tables = _extract_field(block, "Tables")
        trigger_phrases = _extract_field(block, "Trigger phrases")

        # Build a rich embed_text that puts trigger phrases up front
        # so semantic search lands on intent rather than SQL syntax
        embed_lines = [
            f"Query pattern: {header}",
            f"Intent: {intent}",
            f"Trigger phrases: {trigger_phrases}",
            f"Tables involved: {tables}",
            "",
            block,  # full block including SQL
        ]
        embed_text = PREFIX_MAP["query_pattern"] + "\n".join(embed_lines)

        # Stable id from header slug
        slug = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")

        chunks.append(
            Chunk(
                id=f"pattern::{slug}",
                text=block,
                embed_text=embed_text,
                metadata={
                    "source": str(path.name),
                    "type": "query_pattern",
                    "pattern_name": header,
                    "intent": intent,
                    "tables_involved": [t.strip() for t in tables.split(",") if t.strip()],
                    "trigger_phrases": [t.strip() for t in trigger_phrases.split(",") if t.strip()],
                    "has_sql": "```sql" in block,
                },
            )
        )

    return chunks



def _split_business_metrics(text: str, path: Path) -> List[Chunk]:
    """
    Split business_metrics.md into one chunk per ### metric block.

    Each metric block contains:
      - metric name (### header)
      - intent / description sentence
      - tables involved
      - canonical SQL

    Splitting at ### (not ##) because ## are domain groupings
    (e.g. "Customer & Advisor Metrics") — too broad to be useful
    retrieval units. The ### metric is the right granularity.
    """
    # Extract domain context from surrounding ## header so each chunk
    # knows which domain it belongs to (Customer, Portfolio, Loan, etc.)
    chunks: List[Chunk] = []
    current_domain = "General"

    # Walk line by line to track ## domain and split on ###
    sections: List[tuple[str, str]] = []   # (domain, block_text)
    current_block_lines: List[str] = []
    in_metric = False

    for line in text.splitlines():
        if line.startswith("## ") and not line.startswith("### "):
            current_domain = line.lstrip("# ").strip()
            in_metric = False
            continue
        if line.startswith("### "):
            if in_metric and current_block_lines:
                sections.append((current_domain, "\n".join(current_block_lines).strip()))
            current_block_lines = [line]
            in_metric = True
        elif in_metric:
            current_block_lines.append(line)

    # Flush last block
    if in_metric and current_block_lines:
        sections.append((current_domain, "\n".join(current_block_lines).strip()))

    for domain, block in sections:
        if not block:
            continue

        header_match = re.match(r"### (.+)", block)
        if not header_match:
            continue
        metric_name = header_match.group(1).strip()

        # Extract tables mentioned in SQL FROM / JOIN clauses
        tables_in_sql = list(dict.fromkeys(
            re.findall(r"(?:FROM|JOIN)\s+(\w+)", block, re.IGNORECASE)
        ))

        slug = re.sub(r"[^a-z0-9]+", "_", metric_name.lower()).strip("_")

        # embed_text: prepend domain + metric name so semantic search
        # on "what is AUM" lands on the AUM metric, not a schema column
        embed_text = (
            PREFIX_MAP["business_metric"]
            + f"Domain: {domain} | Metric: {metric_name}\n\n"
            + block
        )

        chunks.append(
            Chunk(
                id=f"metric::{slug}",
                text=block,
                embed_text=embed_text,
                metadata={
                    "source": str(path.name),
                    "type": "business_metric",
                    "metric_name": metric_name,
                    "domain": domain,
                    "tables_involved": tables_in_sql,
                    "has_sql": "```sql" in block,
                },
            )
        )

    return chunks

def _split_glossary(text: str, path: Path) -> List[Chunk]:
    """
    Split business_glossary.md by **Term** blocks.
    Special case: the Ambiguous Terms table is kept as one chunk.
    """
    chunks: List[Chunk] = []

    # Separate the ambiguous terms section — always retrieved unconditionally
    ambiguous_split = re.split(r"\n## Ambiguous", text, maxsplit=1)
    main_text = ambiguous_split[0]
    ambiguous_block = ("## Ambiguous" + ambiguous_split[1]) if len(ambiguous_split) > 1 else ""

    # Split main glossary on bolded terms at line start
    # Pattern: line starting with **TERM**
    entries = re.split(r"\n(?=\*\*[A-Z])", main_text)

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        # Skip section headers (## A, ## B, etc.)
        if re.match(r"^#+\s+\w$", entry):
            continue

        term_match = re.match(r"\*\*(.+?)\*\*", entry)
        if not term_match:
            continue

        term = term_match.group(1).strip()

        # Extract maps_to columns if present
        maps_to = re.findall(r"`(\w+\.\w+)`", entry)

        slug = re.sub(r"[^a-z0-9]+", "_", term.lower()).strip("_")

        chunks.append(
            Chunk(
                id=f"glossary::{slug}",
                text=entry,
                embed_text=PREFIX_MAP["glossary_term"] + term + "\n" + entry,
                metadata={
                    "source": str(path.name),
                    "type": "glossary_term",
                    "term": term,
                    "maps_to_columns": maps_to,
                },
            )
        )

    # Ambiguous terms table — single chunk, flagged for always-on injection
    if ambiguous_block.strip():
        chunks.append(
            Chunk(
                id="glossary::ambiguous_terms",
                text=ambiguous_block.strip(),
                embed_text=PREFIX_MAP["glossary_term"]
                + "ambiguous terms disambiguation table\n"
                + ambiguous_block.strip(),
                metadata={
                    "source": str(path.name),
                    "type": "glossary_term",
                    "term": "ambiguous_terms",
                    "always_inject": True,   # flag for retriever to always include
                    "maps_to_columns": [],
                },
            )
        )

    return chunks


def _split_by_h2(text: str, path: Path, chunk_type: str) -> List[Chunk]:
    """
    Generic splitter for ## header-delimited files
    (relationships_context.md, sql_guardrails.md).
    """
    blocks = re.split(r"\n(?=## )", text)
    chunks: List[Chunk] = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        header_match = re.match(r"## (.+)", block)
        header = header_match.group(1).strip() if header_match else "intro"
        slug = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")
        source_stem = path.stem.lower().replace(" ", "_")

        chunks.append(
            Chunk(
                id=f"{source_stem}::{slug}",
                text=block,
                embed_text=PREFIX_MAP.get(chunk_type, "") + block,
                metadata={
                    "source": str(path.name),
                    "type": chunk_type,
                    "section": header,
                },
            )
        )

    return chunks


# ---------------------------------------------------------------------------
# Convenience: load an entire directory
# ---------------------------------------------------------------------------

def load_knowledge_base(kb_dir: str | Path) -> List[Chunk]:
    """
    Load all .yaml and .md files from kb_dir.
    Returns a flat list of all chunks across all files.
    """
    kb_dir = Path(kb_dir)
    all_chunks: List[Chunk] = []

    for yaml_path in sorted(kb_dir.glob("*.yaml")):
        chunks = load_yaml_table_schema(yaml_path)
        all_chunks.extend(chunks)
        print(f"  [yaml] {yaml_path.name} -> {len(chunks)} chunk(s)")

    for md_path in sorted(kb_dir.glob("*.md")):
        chunks = load_markdown_file(md_path)
        all_chunks.extend(chunks)
        print(f"  [md]   {md_path.name} -> {len(chunks)} chunk(s)")

    return all_chunks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_field(text: str, label: str) -> str:
    """Extract the value after a bold **Label:** line."""
    match = re.search(rf"\*\*{label}:\*\*\s*(.+)", text)
    return match.group(1).strip() if match else ""


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in text.splitlines())


# ---------------------------------------------------------------------------
# Main — test runner
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
def _print_chunk(
    num: int,
    chunk: "Chunk",
    show_embed: bool = False,
    full: bool = False,
) -> None:
    SEP2 = "-" * 70
    print(f"\n{SEP2}")
    print(f"Chunk #{num}  |  ID: {chunk.id}")
    print(SEP2)
    print(f"  type            : {chunk.metadata.get('type')}")
    print(f"  source          : {chunk.metadata.get('source')}")

    # Type-specific metadata fields
    if chunk.metadata.get("type") == "table_schema":
        print(f"  table_name      : {chunk.metadata.get('table_name')}")
        print(f"  related_tables  : {chunk.metadata.get('related_tables')}")
        print(f"  has_sample_qs   : {chunk.metadata.get('has_sample_queries')}")
    elif chunk.metadata.get("type") == "business_metric":
        print(f"  metric_name     : {chunk.metadata.get('metric_name')}")
        print(f"  domain          : {chunk.metadata.get('domain')}")
        print(f"  tables_involved : {chunk.metadata.get('tables_involved')}")
        print(f"  has_sql         : {chunk.metadata.get('has_sql')}")
    elif chunk.metadata.get("type") == "query_pattern":
        print(f"  pattern_name    : {chunk.metadata.get('pattern_name')}")
        print(f"  intent          : {chunk.metadata.get('intent')}")
        print(f"  tables_involved : {chunk.metadata.get('tables_involved')}")
        print(f"  trigger_phrases : {chunk.metadata.get('trigger_phrases')}")
    elif chunk.metadata.get("type") == "glossary_term":
        print(f"  term            : {chunk.metadata.get('term')}")
        print(f"  maps_to_columns : {chunk.metadata.get('maps_to_columns')}")
        print(f"  always_inject   : {chunk.metadata.get('always_inject', False)}")

    display_text = chunk.embed_text if show_embed else chunk.text
    label = "embed_text" if show_embed else "text"
    max_chars = None if full else 400

    print(f"\n  [{label}]")
    preview = display_text if (full or max_chars is None) else display_text[:max_chars]
    for line in preview.splitlines():
        print(f"    {line}")
    if not full and max_chars and len(display_text) > max_chars:
        remaining = len(display_text) - max_chars
        print(f"    ... [{remaining} more chars — use --chunk-id {chunk.id} to see full]")

if __name__ == "__main__":
    import argparse
    import sys
    from collections import Counter

    parser = argparse.ArgumentParser(description="Test data_loader parsing.")
    parser.add_argument("--kb-dir", default="../table-schemas", help="Path to KB directory.")
    parser.add_argument("--file", default=None, help="Test a single file instead of full KB.")
    parser.add_argument("--chunk-id", default=None, help="Print full content of a specific chunk ID.")
    parser.add_argument("--type", default=None, help="Filter printed chunks by type.")
    parser.add_argument("--show-embed", action="store_true", help="Show embed_text instead of text.")
    args = parser.parse_args()

    SEP = "=" * 70

    # -----------------------------------------------------------------------
    # Single file mode
    # -----------------------------------------------------------------------
    if args.file:
        path = Path(args.file)
        print(f"\n{SEP}")
        print(f"Single file test: {path.name}")
        print(SEP)

        if path.suffix == ".yaml":
            chunks = load_yaml_table_schema(path)
        elif path.suffix == ".md":
            chunks = load_markdown_file(path)
        else:
            print(f"Unsupported file type: {path.suffix}")
            sys.exit(1)

        print(f"Chunks produced: {len(chunks)}")
        print(f"Chunk IDs: {[c.id for c in chunks]}\n")

        # If --chunk-id given, print just that chunk in full
        if args.chunk_id:
            match = next((c for c in chunks if c.id == args.chunk_id), None)
            if match:
                _print_chunk(1, match, show_embed=args.show_embed, full=True)
            else:
                print(f"[error] Chunk ID '{args.chunk_id}' not found in {path.name}.")
                print(f"Available IDs: {[c.id for c in chunks]}")
                sys.exit(1)
        else:
            for i, chunk in enumerate(chunks, 1):
                _print_chunk(i, chunk, show_embed=args.show_embed)
        sys.exit(0)

    # -----------------------------------------------------------------------
    # Full KB mode
    # -----------------------------------------------------------------------
    kb_dir = Path(args.kb_dir)
    print(f"\n{SEP}")
    print(f"Loading full knowledge base from: {kb_dir.resolve()}")
    print(SEP)

    all_chunks = load_knowledge_base(kb_dir)

    # -----------------------------------------------------------------------
    # Summary table
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("CHUNK SUMMARY")
    print(SEP)
    type_counts = Counter(c.metadata.get("type", "unknown") for c in all_chunks)
    for chunk_type, count in sorted(type_counts.items()):
        print(f"  {chunk_type:<22} {count:>3} chunk(s)")
    print(f"  {'─'*28}")
    print(f"  {'TOTAL':<22} {len(all_chunks):>3}")

    # -----------------------------------------------------------------------
    # ID list — every chunk
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("ALL CHUNK IDs")
    print(SEP)
    for chunk in all_chunks:
        type_tag = chunk.metadata.get("type", "unknown")
        print(f"  [{type_tag:<18}]  {chunk.id}")

    # -----------------------------------------------------------------------
    # Specific chunk lookup
    # -----------------------------------------------------------------------
    if args.chunk_id:
        match = next((c for c in all_chunks if c.id == args.chunk_id), None)
        if match:
            print(f"\n{SEP}")
            print(f"CHUNK DETAIL: {args.chunk_id}")
            print(SEP)
            _print_chunk(1, match, show_embed=args.show_embed, full=True)
        else:
            print(f"\n[warn] Chunk ID '{args.chunk_id}' not found.")
            print("Valid IDs listed above.")
        sys.exit(0)

    # -----------------------------------------------------------------------
    # Per-type sample: print first chunk of each type
    # -----------------------------------------------------------------------
    type_filter = args.type
    print(f"\n{SEP}")
    title = f"SAMPLE CHUNK PER TYPE" if not type_filter else f"CHUNKS OF TYPE: {type_filter}"
    print(title)
    print(SEP)

    if type_filter:
        target_chunks = [c for c in all_chunks if c.metadata.get("type") == type_filter]
        if not target_chunks:
            print(f"No chunks found with type='{type_filter}'")
            print(f"Available types: {sorted(type_counts.keys())}")
        for i, chunk in enumerate(target_chunks, 1):
            _print_chunk(i, chunk, show_embed=args.show_embed)
    else:
        seen_types: set = set()
        sample_num = 1
        for chunk in all_chunks:
            chunk_type = chunk.metadata.get("type", "unknown")
            if chunk_type not in seen_types:
                seen_types.add(chunk_type)
                _print_chunk(sample_num, chunk, show_embed=args.show_embed)
                sample_num += 1

    # -----------------------------------------------------------------------
    # Validation checks
    # -----------------------------------------------------------------------
    print(f"\n{SEP}")
    print("VALIDATION CHECKS")
    print(SEP)

    errors = 0

    # 1. No duplicate IDs
    all_ids = [c.id for c in all_chunks]
    dupes = [id_ for id_ in all_ids if all_ids.count(id_) > 1]
    if dupes:
        print(f"  [FAIL] Duplicate chunk IDs found: {set(dupes)}")
        errors += 1
    else:
        print(f"  [PASS] No duplicate IDs ({len(all_ids)} unique)")

    # 2. Every chunk has non-empty text
    empty_text = [c.id for c in all_chunks if not c.text.strip()]
    if empty_text:
        print(f"  [FAIL] Chunks with empty text: {empty_text}")
        errors += 1
    else:
        print(f"  [PASS] All chunks have non-empty text")

    # 3. Every chunk has non-empty embed_text
    empty_embed = [c.id for c in all_chunks if not c.embed_text.strip()]
    if empty_embed:
        print(f"  [FAIL] Chunks with empty embed_text: {empty_embed}")
        errors += 1
    else:
        print(f"  [PASS] All chunks have non-empty embed_text")

    # 4. Every chunk has required metadata keys
    required_meta = {"source", "type"}
    missing_meta = [c.id for c in all_chunks if not required_meta.issubset(c.metadata)]
    if missing_meta:
        print(f"  [FAIL] Chunks missing required metadata keys: {missing_meta}")
        errors += 1
    else:
        print(f"  [PASS] All chunks have required metadata keys (source, type)")

    # 5. All table_schema chunks have table_name in metadata
    schema_missing_table = [
        c.id for c in all_chunks
        if c.metadata.get("type") == "table_schema" and not c.metadata.get("table_name")
    ]
    if schema_missing_table:
        print(f"  [FAIL] table_schema chunks missing table_name: {schema_missing_table}")
        errors += 1
    else:
        print(f"  [PASS] All table_schema chunks have table_name metadata")

    # 6. All business_metric and query_pattern chunks have SQL
    sql_types = {"business_metric", "query_pattern"}
    missing_sql = [
        c.id for c in all_chunks
        if c.metadata.get("type") in sql_types and not c.metadata.get("has_sql")
    ]
    if missing_sql:
        print(f"  [FAIL] metric/pattern chunks missing SQL: {missing_sql}")
        errors += 1
    else:
        print(f"  [PASS] All metric and pattern chunks contain SQL")

    # 7. embed_text starts with expected prefix for each type
    prefix_checks = {
        "table_schema":    "SQL schema definition",
        "business_metric": "Financial business metric",
        "query_pattern":   "Business metric SQL",
        "glossary_term":   "Financial term",
    }
    prefix_failures = []
    for chunk in all_chunks:
        expected_start = prefix_checks.get(chunk.metadata.get("type", ""))
        if expected_start and not chunk.embed_text.startswith(expected_start):
            prefix_failures.append(chunk.id)
    if prefix_failures:
        print(f"  [FAIL] embed_text missing expected prefix: {prefix_failures}")
        errors += 1
    else:
        print(f"  [PASS] embed_text prefixes correct for all typed chunks")

    # 8. Token length estimate (rough: 1 token ≈ 4 chars)
    oversized = [
        (c.id, len(c.embed_text) // 4)
        for c in all_chunks
        if len(c.embed_text) // 4 > 1500
    ]
    if oversized:
        print(f"  [WARN] Chunks exceeding ~1500 tokens (may degrade embedding quality):")
        for cid, tok in oversized:
            print(f"         {cid}: ~{tok} tokens")
    else:
        print(f"  [PASS] All chunks within recommended token budget (<1500 tokens)")

    print(f"\n{'─'*40}")
    if errors == 0:
        print(f"  Result: ALL CHECKS PASSED")
    else:
        print(f"  Result: {errors} check(s) FAILED — review above")
    print()


# ---------------------------------------------------------------------------
# Print helper (used by main only)
# ---------------------------------------------------------------------------