"""Import the official legal corpus through the same pipeline the admin UI uses.

Reads legal-corpus/manifest.json, parses each file with the production parser and
indexes it with the production embedding/chunking path. Idempotent: a document whose
official number (or title) already exists is re-indexed, never duplicated.

    python scripts/import_nhh.py --admin-username admin
    python scripts/import_nhh.py --status
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings
from app.database import SessionLocal
from app.models import Chunk, NhhDocument, Role, User
from app.services.documents import MIMES, detect_type, parse_file
from app.services.rag import index_document

def _default_manifest() -> Path:
    """Repo layout puts legal-corpus beside backend/; the image mounts it at /app."""
    for candidate in (PROJECT_ROOT / "legal-corpus" / "manifest.json",
                      BACKEND_ROOT / "legal-corpus" / "manifest.json"):
        if candidate.exists():
            return candidate
    return PROJECT_ROOT / "legal-corpus" / "manifest.json"


def report(db) -> dict:
    total = db.scalar(select(func.count(NhhDocument.id))) or 0
    active = db.scalar(select(func.count(NhhDocument.id)).where(
        NhhDocument.is_active.is_(True), NhhDocument.indexed.is_(True))) or 0
    chunks = db.scalar(select(func.count(Chunk.id)).where(Chunk.corpus_type == "nhh")) or 0
    return {"nhh_documents": total, "active_indexed": active, "nhh_chunks": chunks}


def print_status(db) -> None:
    counts = report(db)
    print(f"NHH hujjatlar     : {counts['nhh_documents']}")
    print(f"Faol + indekslangan: {counts['active_indexed']}")
    print(f"NHH parchalar     : {counts['nhh_chunks']}")
    for item in db.scalars(select(NhhDocument).order_by(NhhDocument.title)):
        print(f"  - {item.title} | {item.category} | {item.official_number or '-'} "
              f"| chunks={len(item.chunks)} | active={item.is_active} | {item.indexing_status}")


def existing_record(db, entry: dict) -> NhhDocument | None:
    number = (entry.get("official_number") or "").strip()
    if number:
        found = db.scalar(select(NhhDocument).where(NhhDocument.official_number == number))
        if found:
            return found
    return db.scalar(select(NhhDocument).where(NhhDocument.title == entry["title"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Rasmiy NHH korpusini import qilish")
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--status", action="store_true", help="Faqat hisobotni ko‘rsatish")
    parser.add_argument("--reindex", action="store_true",
                        help="Mavjud hujjatni ham qayta indekslash")
    args = parser.parse_args()
    manifest = args.manifest or _default_manifest()

    with SessionLocal() as db:
        if args.status:
            print_status(db)
            return

        admin = db.scalar(select(User).where(User.username == args.admin_username))
        if not admin or admin.role != Role.administrator:
            raise SystemExit(f"Administrator topilmadi: {args.admin_username}. "
                             "Avval `python -m app.cli` bilan administrator yarating.")
        if not manifest.exists():
            raise SystemExit(f"Manifest topilmadi: {manifest}")
        entries = json.loads(manifest.read_text(encoding="utf-8"))

        target_dir = get_settings().data_dir / "nhh"
        target_dir.mkdir(parents=True, exist_ok=True)
        created = reindexed = skipped = 0

        for entry in entries:
            source = (manifest.parent / entry["file"]).resolve()
            if not source.exists():
                raise SystemExit(f"Korpus fayli topilmadi: {source}")
            data = source.read_bytes()
            kind = detect_type(data)
            parsed = parse_file(kind, data)

            record = existing_record(db, entry)
            if record and not args.reindex:
                print(f"[skip] allaqachon mavjud: {record.title}")
                skipped += 1
                continue

            if record:
                record.original_text = parsed
                record.indexing_status = "processing"
            else:
                stored_name = f"corpus_{source.name}"
                (target_dir / stored_name).write_bytes(data)
                adoption = entry.get("adoption_date")
                record = NhhDocument(
                    title=entry["title"], category=entry["category"],
                    source_url=entry.get("source_url"),
                    official_number=(entry.get("official_number") or "").strip() or None,
                    adoption_date=datetime.strptime(adoption, "%Y-%m-%d").date() if adoption else None,
                    original_filename=source.name, stored_name=stored_name,
                    original_text=parsed, created_by=admin.id,
                    extraction_status="completed", indexing_status="processing",
                )
                db.add(record)
            db.flush()
            count = index_document(db, record, "nhh")
            record.indexing_status = "completed"
            record.indexed_at = datetime.now(timezone.utc)
            record.processing_error = None
            record.is_active = True
            db.commit()
            print(f"[ok] {record.title}: {count} parcha indekslandi")
            reindexed += 1 if entry.get("_existing") else 0
            created += 1

        print(f"\nYakun: {created} import/qayta indeks, {skipped} o‘tkazib yuborildi")
        print_status(db)


if __name__ == "__main__":
    main()
