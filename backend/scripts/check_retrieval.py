"""Developer-only deterministic legal retrieval diagnostic.

Usage: python -m scripts.check_retrieval --username admin
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal
from app.models import User
from app.services.ai_agent import distinct_source_chunks, prefer_article_starts
from app.services.rag import filter_legal_topic, legal_lexical_fallback, search


QUERIES = {
    "agreements": "Raqobatga qarshi kelishuvlar qaysi moddada tartibga solingan?",
    "dominant_criteria": "Raqobat to‘g‘risidagi qonunda ustun mavqeni aniqlash mezonlarini top",
    "dominant_abuse": "Ustun mavqeni suiiste’mol qilish taqiqi qaysi moddada?",
    "trade_restrictions": "Savdolarda raqobatni cheklash bo‘yicha talablarni top",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if not user:
            raise SystemExit(f"User not found: {args.username}")
        for key, query in QUERIES.items():
            chunks = search(db, query, user, "nhh", None, 12)
            if not chunks:
                chunks = legal_lexical_fallback(db, query, 12)
            selected = prefer_article_starts(
                db, distinct_source_chunks(filter_legal_topic(chunks, query), limit=3),
            )
            labels = [chunk.article_clause for chunk in selected]
            print(f"{key}: {labels}")


if __name__ == "__main__":
    main()
