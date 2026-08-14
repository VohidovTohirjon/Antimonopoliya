"""The legal pipeline must be generic across several indexed documents.

Everything here is a clearly-marked synthetic TEST-FIXTURE law living only in the
isolated test database. Nothing in this module may be presented as real law, and
none of it is ever written to a production database.
"""

import io

import pytest
from docx import Document as WordDocument

FIXTURE_TAG = "TEST-FIXTURE"

# Three documents that differ in title, article numbering, category, URL and
# internal text structure — deliberately including a repeated article number.
REKLAMA = (
    "7-modda. Reklama beruvchining majburiyatlari\n"
    "Reklama beruvchi reklama materialining ishonchliligi uchun javob beradi.\n\n"
    "13-modda. Nomaqbul reklamani taqiqlash\n"
    "Iste’molchini chalg‘ituvchi nomaqbul reklamani tarqatish taqiqlanadi.\n"
)
MONOPOLIYA = (
    "5-modda. Tabiiy monopoliya subyektlari reyestri\n"
    "Tabiiy monopoliya subyektlari reyestri vakolatli organ tomonidan yuritiladi.\n\n"
    "13-modda. Tabiiy monopoliya sohasidagi tariflar\n"
    "Tabiiy monopoliya subyektining tariflari vakolatli organ tomonidan tasdiqlanadi.\n"
)
IDORAVIY = (
    "3-band. Murojaatlarni ko‘rib chiqish muddati\n"
    "Murojaat kelib tushgan kundan e’tiboran o‘ttiz kun ichida ko‘rib chiqiladi.\n"
)

DOCUMENTS = (
    {
        "key": "reklama",
        "title": f"Reklama to‘g‘risida ({FIXTURE_TAG})",
        "category": "Qonun",
        "official_number": f"{FIXTURE_TAG}-001",
        "source_url": "https://lex.uz/test-fixture-reklama",
        "text": REKLAMA,
        "articles": {"7-modda", "13-modda"},
    },
    {
        "key": "monopoliya",
        "title": f"Tabiiy monopoliyalar to‘g‘risida ({FIXTURE_TAG})",
        "category": "Qonun",
        "official_number": f"{FIXTURE_TAG}-002",
        "source_url": "https://lex.uz/test-fixture-monopoliya",
        "text": MONOPOLIYA,
        "articles": {"5-modda", "13-modda"},
    },
    {
        "key": "idoraviy",
        "title": f"Murojaatlar tartibi ({FIXTURE_TAG})",
        "category": "Vazirlar Mahkamasi qarori",
        "official_number": f"{FIXTURE_TAG}-003",
        "source_url": "https://lex.uz/test-fixture-murojaat",
        "text": IDORAVIY,
        "articles": {"3-band"},
    },
)


def law_docx(text: str) -> bytes:
    stream = io.BytesIO()
    document = WordDocument()
    for paragraph in text.split("\n"):
        document.add_paragraph(paragraph)
    document.save(stream)
    return stream.getvalue()


@pytest.fixture
def corpus(client, admin_headers):
    created = {}
    for spec in DOCUMENTS:
        response = client.post(
            "/api/nhh", headers=admin_headers,
            data={"title": spec["title"], "category": spec["category"],
                  "official_number": spec["official_number"],
                  "source_url": spec["source_url"], "adoption_date": "2024-01-15"},
            files={"file": (f"{spec['key']}.docx", law_docx(spec["text"]))},
        )
        assert response.status_code == 201, response.text
        created[spec["key"]] = response.json()
    return created


def ask(client, headers, question: str) -> dict:
    response = client.post("/api/chat", headers=headers,
                           json={"question": question, "legal": True})
    assert response.status_code == 200, response.text
    return response.json()


def test_every_fixture_document_indexes_with_its_own_metadata(corpus):
    for spec in DOCUMENTS:
        item = corpus[spec["key"]]
        assert item["indexed"] is True
        assert item["indexing_status"] == "completed"
        assert item["chunk_count"] >= 1
        assert item["category"] == spec["category"]
        assert item["source_url"] == spec["source_url"]
        assert item["official_number"] == spec["official_number"]
        assert item["adoption_date"] == "2024-01-15"


def test_article_and_clause_labels_are_extracted_per_document(client, admin_headers, corpus):
    from app.database import SessionLocal
    from app.models import Chunk
    from sqlalchemy import select

    with SessionLocal() as db:
        for spec in DOCUMENTS:
            chunks = list(db.scalars(
                select(Chunk).where(Chunk.nhh_id == corpus[spec["key"]]["id"])
            ))
            assert chunks, f"{spec['key']} uchun chunk yaratilmadi"
            labels = {(chunk.article_clause or "").split(".")[0].strip().lower()
                      for chunk in chunks}
            for expected in spec["articles"]:
                assert any(expected.split("-")[0] in label for label in labels), (
                    f"{spec['key']}: {expected} topilmadi, mavjud: {labels}"
                )
            assert all(chunk.corpus_type == "nhh" for chunk in chunks)


def test_a_query_for_one_law_does_not_cite_another(client, xodim_headers, corpus):
    result = ask(client, xodim_headers, "Nomaqbul reklamani taqiqlash qanday tartibga solingan?")
    assert result["sources"], result["answer"]
    names = {source["document_name"] for source in result["sources"]}
    assert names == {f"Reklama to‘g‘risida ({FIXTURE_TAG})"}
    assert all("monopoliya" not in name.lower() for name in names)


def test_tariff_question_reaches_only_the_natural_monopoly_law(client, xodim_headers, corpus):
    result = ask(client, xodim_headers, "Tabiiy monopoliya tariflarini kim tasdiqlaydi?")
    assert result["sources"], result["answer"]
    names = {source["document_name"] for source in result["sources"]}
    assert names == {f"Tabiiy monopoliyalar to‘g‘risida ({FIXTURE_TAG})"}


def test_repeated_article_number_keeps_its_own_document_identity(client, xodim_headers, corpus):
    """13-modda exists in two fixture laws; citations must not blend them."""
    reklama = ask(client, xodim_headers, "Chalg‘ituvchi nomaqbul reklama taqiqlanadimi?")
    monopoliya = ask(client, xodim_headers, "Tabiiy monopoliya sohasidagi tariflar qanday tasdiqlanadi?")
    for result, expected_url in (
        (reklama, "https://lex.uz/test-fixture-reklama"),
        (monopoliya, "https://lex.uz/test-fixture-monopoliya"),
    ):
        assert result["sources"]
        for source in result["sources"]:
            assert source["url"] == expected_url
            # The excerpt must come from the document the card names.
            assert source["document_name"].endswith(f"({FIXTURE_TAG})")
    assert ({s["document_id"] for s in reklama["sources"]}
            != {s["document_id"] for s in monopoliya["sources"]})


def test_source_cards_carry_document_name_article_url_and_excerpt(client, xodim_headers, corpus):
    result = ask(client, xodim_headers, "Nomaqbul reklamani taqiqlash qanday tartibga solingan?")
    for source in result["sources"]:
        assert source["document_name"]
        assert source["article_or_clause"]
        assert source["url"].startswith("https://lex.uz/test-fixture-")
        assert len(source["excerpt"]) > 10
        assert source["evidence_type"] == "nhh"


def test_citation_numbering_is_contiguous_and_deterministic(client, xodim_headers, corpus):
    question = "Nomaqbul reklamani taqiqlash qanday tartibga solingan?"
    runs = []
    for _ in range(5):
        result = ask(client, xodim_headers, question)
        runs.append(tuple((s["citation_number"], s["document_id"], s["article_or_clause"])
                          for s in result["sources"]))
        numbers = [s["citation_number"] for s in result["sources"]]
        assert numbers == list(range(1, len(numbers) + 1))
    assert len(set(runs)) == 1


def test_question_outside_the_whole_corpus_invents_nothing(client, xodim_headers, corpus):
    result = ask(client, xodim_headers, "Mars sayyorasida qurilish litsenziyasi qanday olinadi?")
    assert result["result_kind"] == "no_sources"
    assert result["sources"] == []
    for spec in DOCUMENTS:
        assert spec["title"] not in result["answer"]


def test_reindex_replaces_chunks_without_losing_metadata(client, admin_headers, corpus):
    from app.database import SessionLocal
    from app.models import Chunk
    from sqlalchemy import func, select

    target = corpus["reklama"]
    with SessionLocal() as db:
        before = db.scalar(select(func.count(Chunk.id)).where(Chunk.nhh_id == target["id"]))
    response = client.post(f"/api/nhh/{target['id']}/reindex", headers=admin_headers)
    assert response.status_code == 200, response.text
    reindexed = response.json()
    assert reindexed["indexing_status"] == "completed"
    assert reindexed["source_url"] == target["source_url"]
    assert reindexed["official_number"] == target["official_number"]
    with SessionLocal() as db:
        after = db.scalar(select(func.count(Chunk.id)).where(Chunk.nhh_id == target["id"]))
    assert after == before, "qayta indekslash chunklarni dublikat qilmasligi kerak"


def test_deactivated_law_is_hidden_from_users_and_from_grounding(client, admin_headers,
                                                                 xodim_headers, corpus):
    target = corpus["monopoliya"]
    patched = client.patch(f"/api/nhh/{target['id']}", headers=admin_headers,
                           json={"is_active": False})
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_active"] is False

    visible = {item["title"] for item in client.get("/api/nhh", headers=xodim_headers).json()}
    assert target["title"] not in visible
    # An administrator still sees it for management purposes.
    assert target["title"] in {item["title"] for item in
                               client.get("/api/nhh", headers=admin_headers).json()}

    result = ask(client, xodim_headers, "Tabiiy monopoliya tariflarini kim tasdiqlaydi?")
    assert all(source["document_name"] != target["title"] for source in result["sources"])


def test_deleting_a_law_removes_its_chunks_and_leaves_the_rest_intact(client, admin_headers,
                                                                     corpus):
    from app.database import SessionLocal
    from app.models import Chunk
    from sqlalchemy import func, select

    target = corpus["idoraviy"]
    assert client.delete(f"/api/nhh/{target['id']}", headers=admin_headers).status_code == 204
    with SessionLocal() as db:
        assert db.scalar(select(func.count(Chunk.id)).where(Chunk.nhh_id == target["id"])) == 0
        for other in ("reklama", "monopoliya"):
            assert db.scalar(
                select(func.count(Chunk.id)).where(Chunk.nhh_id == corpus[other]["id"])
            ) > 0
    remaining = {item["title"] for item in client.get("/api/nhh", headers=admin_headers).json()}
    assert target["title"] not in remaining
