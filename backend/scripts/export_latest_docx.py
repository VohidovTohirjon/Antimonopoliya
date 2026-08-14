"""Developer QA helper: export the latest successful/fallback draft to a chosen path."""

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import SessionLocal
from app.models import AiHistory
from app.services.export import make_docx


TITLES = {
    "response_letter": "Javob xati loyihasi",
    "report": "Hisobot",
    "info_note": "Ma’lumotnoma",
    "brief": "Qisqa ma’lumot",
    "analytical_conclusion": "Tahliliy xulosa",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--operation", default="response_letter")
    args = parser.parse_args()
    with SessionLocal() as db:
        item = db.scalar(
            select(AiHistory).where(AiHistory.operation == args.operation)
            .order_by(AiHistory.created_at.desc()).limit(1)
        )
        if not item:
            raise SystemExit("Mos tarix yozuvi topilmadi")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(make_docx(TITLES.get(item.operation, "Raqobat AI natijasi"),
                                          item.response_text, item.sources,
                                          item.structured_data))
        print(args.output)


if __name__ == "__main__":
    main()
