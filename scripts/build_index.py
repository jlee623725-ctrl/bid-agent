"""Build TF-IDF vector index from laws and policy data.

Usage: python scripts/build_index.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.tools_bidding import DB_PATH
from agent.vector_store import INDEX_DIR, VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

if __name__ == "__main__":
    store = VectorStore.build_from_db(DB_PATH, INDEX_DIR)

    # Verify
    results = store.search("招标投标保证金", top_k=3)
    print("\nTop results for '招标投标保证金':")
    for r in results:
        print(f"  [{r['_score']:.4f}] {r.get('document_title', r.get('title', ''))[:70]}")
    print("\nIndex built and verified.")
