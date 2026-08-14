"""Read-only structural audit for indexed NHH chunks."""

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import joinedload

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal
from app.models import Chunk


ARTICLE_RE = re.compile(r"\b(\d{1,3})\s*[-.]?\s*(?:modda|модда|статья)\b", re.IGNORECASE)
TARGETS = {8, 19, 21, 29, 42}


def article_number(value: str | None) -> int | None:
    match = ARTICLE_RE.search(value or "")
    return int(match.group(1)) if match else None


def main():
    with SessionLocal() as db:
        chunks = list(db.scalars(
            select(Chunk).options(joinedload(Chunk.nhh))
            .where(Chunk.corpus_type == "nhh").order_by(Chunk.nhh_id, Chunk.chunk_order)
        ))
    hashes = Counter(hashlib.sha256(re.sub(r"\s+", " ", chunk.text).encode()).hexdigest()
                     for chunk in chunks)
    mismatches = []
    broken = []
    source_metadata = set()
    target_details: dict[int, dict] = {}
    for chunk in chunks:
        source_metadata.add((chunk.nhh.title, chunk.nhh.source_url))
        label_number = article_number(chunk.article_clause)
        leading = ARTICLE_RE.match(chunk.text.strip())
        if leading and label_number != int(leading.group(1)):
            mismatches.append({
                "chunk_order": chunk.chunk_order,
                "label": chunk.article_clause,
                "text_article": int(leading.group(1)),
            })
        if "�" in chunk.text or "\x00" in chunk.text:
            broken.append(chunk.chunk_order)
        if label_number in TARGETS:
            detail = target_details.setdefault(label_number, {
                "article": label_number, "chunk_orders": [], "label": chunk.article_clause,
                "source_title": chunk.nhh.title, "source_url": chunk.nhh.source_url,
                "first_excerpt": re.sub(r"\s+", " ", chunk.text)[:360],
            })
            detail["chunk_orders"].append(chunk.chunk_order)
    report = {
        "chunk_count": len(chunks),
        "distinct_article_labels": len({chunk.article_clause for chunk in chunks if chunk.article_clause}),
        "source_metadata": [dict(title=title, url=url) for title, url in sorted(source_metadata)],
        "exact_duplicate_groups": sum(count > 1 for count in hashes.values()),
        "article_label_mismatches": mismatches,
        "broken_text_chunks": broken,
        "target_articles": [target_details[value] for value in sorted(target_details)],
        "continuation_chunks": sum(not ARTICLE_RE.match(chunk.text.strip()) for chunk in chunks),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
