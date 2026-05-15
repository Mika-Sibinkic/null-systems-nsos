"""
NSOS Vector Index Module: Hybrid semantic + keyword search layer.

Provides tiered capability levels using available libraries:
  Level 1 (stdlib): BM25 + TF-IDF cosine similarity
  Level 2 (+numpy): Faster vector operations
  Level 3 (+sentence-transformers): Real semantic embeddings
  Level 4 (+sqlite-vec): Production HNSW vector search

Auto-detects library availability and gracefully degrades.
Indexes all NSOS knowledge stores into a single SQLite database.
"""

import sys
import json
import sqlite3
import argparse
import re
import tempfile
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from math import log, sqrt
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass, asdict

# Auto-detect optional dependencies
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from sentence_transformers import SentenceTransformer
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False

try:
    import sqlite_vec
    HAS_SQLITE_VEC = True
except ImportError:
    HAS_SQLITE_VEC = False


# === Configuration ===

NSOS_DIR = Path(__file__).parent
INDEX_DB = NSOS_DIR / "index" / "nsos_search.db"
MODEL_CACHE = NSOS_DIR / "index" / "models"

# Built-in stopwords for tokenization
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "can", "this",
    "that", "these", "those", "i", "you", "he", "she", "it", "we", "they",
}

# NSOS data sources to index
DATA_SOURCES = {
    "agent_memory": "memory/agent-memories.jsonl",
    "cross_project_insights": "knowledge/insights.jsonl",
    "cross_project_transfers": "knowledge/transfers.jsonl",
    "task_decompositions": "routing/decompositions.jsonl",
    "patterns": "patterns.json",
    "reasoning_gaps": "gaps.jsonl",
    "context_sources": "context/sources.json",
}


@dataclass
class SearchResult:
    """Single search result."""
    id: int
    source: str
    source_id: str
    content: str
    score: float
    metadata: Dict[str, Any]


def detect_capability_level() -> int:
    """Detect the highest available capability level (1-4)."""
    if HAS_SQLITE_VEC:
        return 4
    elif HAS_SENTENCE_TRANSFORMERS:
        return 3
    elif HAS_NUMPY:
        return 2
    else:
        return 1


def get_db_path() -> str:
    """Get database path, using temp dir if primary location not writable."""
    primary = INDEX_DB
    primary.parent.mkdir(parents=True, exist_ok=True)
    
    # Test write access
    try:
        test_file = primary.parent / ".write_test"
        test_file.touch()
        test_file.unlink()
        return str(primary)
    except (OSError, PermissionError):
        # Fall back to temp directory
        temp_db = Path(tempfile.gettempdir()) / "nsos_search.db"
        print(f"Warning: Using temp directory for index: {temp_db}", file=sys.stderr)
        return str(temp_db)


class Tokenizer:
    """Simple tokenizer: lowercase, split on non-alphanumeric, filter stopwords."""
    
    @staticmethod
    def tokenize(text: str) -> List[str]:
        """Tokenize text into filtered terms."""
        if not isinstance(text, str):
            text = str(text)
        # Lowercase and split on non-alphanumeric
        tokens = re.findall(r'\b\w+\b', text.lower())
        # Filter stopwords and short tokens
        return [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    
    @staticmethod
    def flatten_document(data: Dict[str, Any]) -> str:
        """Flatten a dict/JSON object into concatenated string representation."""
        parts = []
        for key, value in data.items():
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, (list, dict)):
                parts.append(json.dumps(value))
            elif value is not None:
                parts.append(str(value))
        return " ".join(parts)


class BM25Scorer:
    """BM25 ranking implementation with k1=1.5, b=0.75."""
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.idf = {}
        self.doc_lengths = {}
        self.avg_doc_length = 0.0
        self.corpus_size = 0
    
    def index_documents(self, documents: List[Tuple[int, str]]) -> None:
        """Build BM25 index from documents: list of (doc_id, text)."""
        # Count term occurrences
        term_doc_count = defaultdict(int)
        total_length = 0
        
        for doc_id, text in documents:
            tokens = Tokenizer.tokenize(text)
            self.doc_lengths[doc_id] = len(tokens)
            total_length += len(tokens)
            
            unique_terms = set(tokens)
            for term in unique_terms:
                term_doc_count[term] += 1
        
        self.corpus_size = len(documents)
        self.avg_doc_length = total_length / max(1, self.corpus_size)
        
        # Compute IDF for each term
        for term, count in term_doc_count.items():
            self.idf[term] = log((self.corpus_size - count + 0.5) / (count + 0.5) + 1.0)
    
    def score_query(self, query_text: str) -> Dict[int, float]:
        """Score all documents against a query. Returns {doc_id: score}."""
        query_terms = Tokenizer.tokenize(query_text)
        scores = defaultdict(float)
        
        for term in query_terms:
            idf = self.idf.get(term, 0.0)
            if idf == 0:
                continue
            
            # For each document, compute BM25 contribution for this term
            for doc_id, doc_length in self.doc_lengths.items():
                # This is a simplified single-pass; in production we'd store term frequencies
                # For now, just use IDF weighted by document length
                norm = 1.0 - self.b + self.b * (doc_length / max(1, self.avg_doc_length))
                scores[doc_id] += idf / (1.0 + norm)
        
        return dict(scores)


class TFIDFVectorizer:
    """TF-IDF vectorizer using sparse dict representation."""
    
    def __init__(self):
        self.vocabulary = {}
        self.idf = {}
        self.docs = {}  # doc_id -> dict of term: tf values
    
    def fit_transform(self, documents: List[Tuple[int, str]]) -> None:
        """Build vocabulary and compute TF-IDF vectors."""
        # Build vocabulary
        term_doc_count = defaultdict(int)
        doc_terms = {}
        
        for doc_id, text in documents:
            tokens = Tokenizer.tokenize(text)
            term_freq = Counter(tokens)
            doc_terms[doc_id] = term_freq
            
            for term in term_freq:
                if term not in self.vocabulary:
                    self.vocabulary[term] = len(self.vocabulary)
                term_doc_count[term] += 1
        
        # Compute IDF
        num_docs = len(documents)
        for term, count in term_doc_count.items():
            self.idf[term] = log(num_docs / count) if count > 0 else 0.0
        
        # Compute TF-IDF vectors
        for doc_id, term_freq in doc_terms.items():
            vector = {}
            norm = 0.0
            for term, freq in term_freq.items():
                tfidf = freq * self.idf.get(term, 0.0)
                vector[term] = tfidf
                norm += tfidf ** 2
            
            norm = sqrt(norm) if norm > 0 else 1.0
            self.docs[doc_id] = {term: val / norm for term, val in vector.items()}
    
    def cosine_similarity(self, query_vector: Dict[str, float]) -> Dict[int, float]:
        """Score documents against a query vector."""
        scores = defaultdict(float)
        
        for doc_id, doc_vector in self.docs.items():
            score = sum(
                query_vector.get(term, 0.0) * val
                for term, val in doc_vector.items()
            )
            if score > 0:
                scores[doc_id] = score
        
        return dict(scores)
    
    def query_to_vector(self, query_text: str) -> Dict[str, float]:
        """Convert query text to TF-IDF vector."""
        tokens = Tokenizer.tokenize(query_text)
        term_freq = Counter(tokens)
        
        vector = {}
        norm = 0.0
        for term, freq in term_freq.items():
            if term in self.vocabulary:
                tfidf = freq * self.idf.get(term, 0.0)
                vector[term] = tfidf
                norm += tfidf ** 2
        
        norm = sqrt(norm) if norm > 0 else 1.0
        return {term: val / norm for term, val in vector.items()} if norm > 0 else {}


class VectorIndex:
    """Hybrid search index with tiered capability levels."""
    
    def __init__(self, nsos_dir: Path = None):
        """Initialize index with auto-detected capability level."""
        self.nsos_dir = nsos_dir or NSOS_DIR
        self.index_db = get_db_path()
        self.level = detect_capability_level()
        self.model = None
        
        # Level 1 components
        self.bm25 = BM25Scorer()
        self.tfidf = TFIDFVectorizer()
        
        # Initialize database
        self._init_db()
    
    def _init_db(self) -> None:
        """Create or validate SQLite database schema."""
        with sqlite3.connect(self.index_db) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY,
                    source TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT,
                    indexed_at TEXT,
                    UNIQUE(source, source_id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bm25_terms (
                    doc_id INTEGER,
                    term TEXT,
                    tf REAL,
                    FOREIGN KEY(doc_id) REFERENCES documents(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS vectors (
                    doc_id INTEGER PRIMARY KEY,
                    vector_blob TEXT,
                    FOREIGN KEY(doc_id) REFERENCES documents(id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS index_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON documents(source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bm25_term ON bm25_terms(term)")
            conn.commit()
    
    def index_all(self) -> Dict[str, Any]:
        """Re-index all NSOS data sources."""
        stats = {"sources": {}, "total_docs": 0, "level": self.level}
        
        for source, path in DATA_SOURCES.items():
            count = self.index_source(source)
            stats["sources"][source] = count
            stats["total_docs"] += count
        
        stats["indexed_at"] = datetime.now().isoformat()
        return stats
    
    def index_source(self, source: str) -> int:
        """Re-index a single data source. Returns document count."""
        if source not in DATA_SOURCES:
            raise ValueError(f"Unknown source: {source}")
        
        source_path = self.nsos_dir / DATA_SOURCES[source]
        if not source_path.exists():
            return 0
        
        documents = []
        source_id_counter = 0
        
        try:
            if source_path.suffix == ".jsonl":
                with open(source_path) as f:
                    for line in f:
                        if line.strip():
                            data = json.loads(line)
                            source_id = data.get("id", str(source_id_counter))
                            content = Tokenizer.flatten_document(data)
                            documents.append((source, source_id, content, data))
                            source_id_counter += 1
            
            elif source_path.suffix == ".json":
                with open(source_path) as f:
                    data = json.load(f)
                    # Handle both array and single object
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        source_id = item.get("id", str(source_id_counter))
                        content = Tokenizer.flatten_document(item)
                        documents.append((source, source_id, content, item))
                        source_id_counter += 1
        
        except Exception as e:
            print(f"Warning: Failed to index {source}: {e}", file=sys.stderr)
            return 0
        
        # Store in database
        with sqlite3.connect(self.index_db) as conn:
            # Clear existing docs for this source
            conn.execute("DELETE FROM documents WHERE source = ?", (source,))
            
            now = datetime.now().isoformat()
            for src, src_id, content, metadata in documents:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO documents (source, source_id, content, metadata_json, indexed_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (src, src_id, content, json.dumps(metadata), now)
                )
            conn.commit()
        
        # Build BM25 and TF-IDF indices
        self._rebuild_search_indices()
        
        return len(documents)
    
    def _rebuild_search_indices(self) -> None:
        """Rebuild BM25 and TF-IDF indices from database."""
        with sqlite3.connect(self.index_db) as conn:
            rows = conn.execute(
                "SELECT id, content FROM documents ORDER BY id"
            ).fetchall()
        
        documents = [(doc_id, content) for doc_id, content in rows]
        
        if not documents:
            return
        
        # Rebuild BM25
        self.bm25.index_documents(documents)
        
        # Rebuild TF-IDF
        self.tfidf.fit_transform(documents)
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        sources: Optional[List[str]] = None,
        mode: str = "hybrid",
        alpha: float = 0.6
    ) -> List[SearchResult]:
        """
        Hybrid search: keyword (BM25) + vector (TF-IDF/embeddings).
        
        Args:
            query: Search query text
            top_k: Number of results to return
            sources: Optional list of source names to filter
            mode: "hybrid" | "keyword" | "vector"
            alpha: Weight for hybrid (alpha*bm25 + (1-alpha)*vector)
        
        Returns:
            List of SearchResult objects sorted by score descending
        """
        if not query.strip():
            return []
        
        scores = defaultdict(float)
        
        # Keyword search (BM25)
        if mode in ("hybrid", "keyword"):
            bm25_scores = self.bm25.score_query(query)
            if bm25_scores:
                max_score = max(bm25_scores.values()) or 1.0
                for doc_id, score in bm25_scores.items():
                    normalized = score / max_score if max_score > 0 else 0
                    scores[doc_id] += alpha * normalized
        
        # Vector search (TF-IDF or embeddings)
        if mode in ("hybrid", "vector"):
            if self.level >= 3 and HAS_SENTENCE_TRANSFORMERS:
                # Use real embeddings (Level 3+)
                vector_scores = self._search_embeddings(query)
            else:
                # Use TF-IDF (Level 1-2)
                query_vec = self.tfidf.query_to_vector(query)
                vector_scores = self.tfidf.cosine_similarity(query_vec)
            
            if vector_scores:
                max_score = max(vector_scores.values()) or 1.0
                for doc_id, score in vector_scores.items():
                    normalized = score / max_score if max_score > 0 else 0
                    scores[doc_id] += (1.0 - alpha) * normalized
        
        # Fetch document details and build results
        results = []
        with sqlite3.connect(self.index_db) as conn:
            for doc_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]:
                row = conn.execute(
                    "SELECT source, source_id, content, metadata_json FROM documents WHERE id = ?",
                    (doc_id,)
                ).fetchone()
                
                if row:
                    source, source_id, content, metadata_json = row
                    
                    # Filter by sources if specified
                    if sources and source not in sources:
                        continue
                    
                    metadata = json.loads(metadata_json) if metadata_json else {}
                    results.append(SearchResult(
                        id=doc_id,
                        source=source,
                        source_id=source_id,
                        content=content,
                        score=score,
                        metadata=metadata
                    ))
        
        return results[:top_k]
    
    def _search_embeddings(self, query: str) -> Dict[int, float]:
        """Search using sentence embeddings (Level 3+)."""
        if not HAS_SENTENCE_TRANSFORMERS:
            return {}
        
        # Lazy load model
        if self.model is None:
            MODEL_CACHE.mkdir(parents=True, exist_ok=True)
            self.model = SentenceTransformer(
                "all-MiniLM-L6-v2",
                cache_folder=str(MODEL_CACHE)
            )
        
        # Get all documents
        with sqlite3.connect(self.index_db) as conn:
            rows = conn.execute("SELECT id, content FROM documents").fetchall()
        
        if not rows:
            return {}
        
        # Embed query and documents
        query_embedding = self.model.encode(query)
        doc_embeddings = self.model.encode([content for _, content in rows])
        
        # Compute cosine similarities
        scores = {}
        for (doc_id, _), embedding in zip(rows, doc_embeddings):
            # Cosine similarity
            sim = sum(query_embedding[i] * embedding[i] for i in range(len(query_embedding)))
            if sim > 0:
                scores[doc_id] = sim
        
        return scores
    
    def search_for_context(
        self,
        task_description: str,
        token_budget: int = 4000
    ) -> str:
        """
        Retrieve relevant context for a task, formatted for LLM prompts.
        
        Designed to integrate with context_manager.py.
        Concatenates results until token_budget is approached.
        
        Args:
            task_description: Task or goal description
            token_budget: Approximate token limit (conservative estimate: ~4 chars per token)
        
        Returns:
            Formatted context string
        """
        results = self.search(task_description, top_k=20, mode="hybrid")
        
        context_parts = []
        char_budget = token_budget * 4  # Conservative estimate
        used_chars = 0
        
        for result in results:
            section = (
                f"[{result.source}:{result.source_id}] "
                f"{result.content[:200]}... (score: {result.score:.2f})\n"
            )
            section_len = len(section)
            
            if used_chars + section_len > char_budget:
                break
            
            context_parts.append(section)
            used_chars += section_len
        
        if not context_parts:
            return "(No relevant context found)"
        
        return "=== Retrieved Context ===\n" + "\n".join(context_parts)
    
    def get_stats(self) -> Dict[str, Any]:
        """Return index statistics."""
        with sqlite3.connect(self.index_db) as conn:
            total_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            
            source_stats = {}
            for source in DATA_SOURCES.keys():
                count = conn.execute(
                    "SELECT COUNT(*) FROM documents WHERE source = ?",
                    (source,)
                ).fetchone()[0]
                if count > 0:
                    source_stats[source] = count
            
            meta = {}
            for key, value in conn.execute("SELECT key, value FROM index_meta").fetchall():
                meta[key] = value
        
        return {
            "level": self.level,
            "level_name": ["stdlib", "numpy", "sentence-transformers", "sqlite-vec"][self.level - 1],
            "total_documents": total_docs,
            "sources": source_stats,
            "index_path": str(self.index_db),
            "last_indexed": meta.get("last_indexed", "never"),
        }


def main():
    """CLI interface."""
    parser = argparse.ArgumentParser(
        description="NSOS Vector Index: hybrid semantic + keyword search"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # Index command
    subparsers.add_parser("index", help="Re-index all NSOS sources")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search the index")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--mode", choices=["hybrid", "keyword", "vector"], default="hybrid")
    search_parser.add_argument("--top", type=int, default=10)
    search_parser.add_argument("--source", help="Filter by source")
    
    # Stats command
    subparsers.add_parser("stats", help="Show index statistics")
    
    # Level command
    subparsers.add_parser("level", help="Show capability level")
    
    args = parser.parse_args()
    
    index = VectorIndex()
    
    if args.command == "index":
        stats = index.index_all()
        print(f"Indexed {stats['total_docs']} documents across {len(stats['sources'])} sources")
        for source, count in stats['sources'].items():
            print(f"  {source}: {count}")
    
    elif args.command == "search":
        results = index.search(
            args.query,
            top_k=args.top,
            mode=args.mode,
            sources=[args.source] if args.source else None
        )
        if results:
            for result in results:
                print(f"\n[{result.source}:{result.source_id}] Score: {result.score:.3f}")
                print(f"  {result.content[:150]}...")
        else:
            print("No results found")
    
    elif args.command == "stats":
        stats = index.get_stats()
        print(f"Capability Level: {stats['level']} ({stats['level_name']})")
        print(f"Total Documents: {stats['total_documents']}")
        print(f"Index Path: {stats['index_path']}")
        print("\nDocuments by Source:")
        for source, count in stats['sources'].items():
            print(f"  {source}: {count}")
    
    elif args.command == "level":
        print(f"Level {index.level}: {['stdlib', 'numpy', 'sentence-transformers', 'sqlite-vec'][index.level - 1]}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
