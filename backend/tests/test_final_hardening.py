import io
import zipfile
from types import SimpleNamespace

from docx import Document as WordDocument

from app.services.rag import filter_legal_topic, sources_from_chunks


def make_docx(paragraphs: list[str]) -> bytes:
    stream = io.BytesIO()
    doc = WordDocument()
    for value in paragraphs:
        doc.add_paragraph(value)
    doc.save(stream)
    return stream.getvalue()


def upload(client, headers, filename: str, paragraphs: list[str], category="oddiy"):
    response = client.post(
        "/api/documents", headers=headers, data={"category": category},
        files={"file": (filename, make_docx(paragraphs))},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_contradiction_is_structured_deduplicated_and_each_quote_is_verbatim(client, xodim_headers):
    document = upload(client, xodim_headers, "demo_qarama_qarshilik.docx", [
        "DEMO - Topshiriq bayonnomasi",
        "1. Muddat",
        "Topshiriqning yakuniy muddati 15-avgust 2026-yil deb belgilandi.",
        "2. Mas’ullar",
        "Tahliliy bo‘lim ma’lumotlarni yig‘adi.",
        "3. Yakuniy kelishuv",
        "Yig‘ilish yakunida topshiriqning yakuniy muddati 20-avgust 2026-yil ekani qayd etildi.",
    ])
    response = client.post(
        f"/api/documents/{document['id']}/analyze", headers=xodim_headers,
        json={"operation": "contradictions"},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["structured"]["kind"] == "contradiction_analysis"
    assert len(result["structured"]["findings"]) == 1
    assert result["answer"].count("15-avgust") == 1
    assert result["answer"].count("20-avgust") == 1
    assert len(result["sources"]) == 2
    assert {source["section"] for source in result["sources"]} == {"1. Muddat", "3. Yakuniy kelishuv"}
    assert all(source["evidence_type"] == "document" for source in result["sources"])


def test_intent_focused_legal_article_selection():
    article_13 = SimpleNamespace(article_clause="13-модда. Устун мавқе",
                                 text="Устун мавқе деб эътироф этиш мезонлари.")
    article_18 = SimpleNamespace(article_clause="18-модда. Устун мавқени суиистеъмол қилишни тақиқлаш",
                                 text="Устун мавқени суиистеъмол қилиш тақиқланади.")
    assert filter_legal_topic([article_18, article_13],
                              "ustun mavqeni aniqlash mezonlari") == [article_13]
    assert filter_legal_topic([article_13, article_18],
                              "ustun mavqeni suiiste’mol qilish taqiqi") == [article_18]


def test_excerpt_ends_cleanly_and_document_source_has_no_fake_article():
    chunk = SimpleNamespace(
        nhh=None,
        document=SimpleNamespace(id="d1", filename="oddiy.docx"),
        document_id="d1", article_clause="2. Natijalar", page=3,
        text=("Birinchi to‘liq gap. " * 70) + "Oxirgi so‘z",
    )
    source = sources_from_chunks([chunk])[0]
    assert source["evidence_type"] == "document"
    assert source["section"] == "2. Natijalar"
    assert source["excerpt"].endswith((". …", " …"))
    assert len(source["excerpt"]) <= 703


def test_response_letter_docx_has_real_word_structure_and_no_raw_markdown(
        client, admin_headers, xodim_headers):
    document = upload(client, xodim_headers, "murojaat.docx", [
        "Murojaat mazmuni",
        "2026-yil 8-iyulda uchta taklifdagi narx 18 foizga oshgani va kelishuv alomatlari ma’lum qilindi.",
    ], "murojaat")
    nhh = client.post(
        "/api/nhh", headers=admin_headers,
        data={"title": "Raqobatga qarshi kelishuvlar", "category": "Qonun",
              "source_url": "https://lex.uz/test-final"},
        files={"file": ("qonun.docx", make_docx([
            "19-modda. Raqobatga qarshi kelishuvlarni tuzish taqiqlanadi."
        ]))},
    )
    assert nhh.status_code == 201
    response = client.post("/api/drafts", headers=xodim_headers, json={
        "kind": "response_letter", "instruction": "Kelishuv alomatlari bo‘yicha javob xati tayyorla",
        "document_id": document["id"],
    })
    assert response.status_code == 200, response.text
    result = response.json()
    exported = client.get(result["export_url"], headers=xodim_headers)
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
        styles = archive.read("word/styles.xml").decode("utf-8")
        settings = archive.read("word/settings.xml").decode("utf-8")
    assert "**" not in xml and "# Javob" not in xml and "&gt;" not in xml
    assert "Mavzu:" in xml and "Qabul qiluvchi" in xml
    assert "ICHKI TEKSHIRUV VARAQASI" not in xml
    evidence = client.get(result["internal_evidence_url"], headers=xodim_headers)
    assert evidence.status_code == 200
    with zipfile.ZipFile(io.BytesIO(evidence.content)) as archive:
        evidence_xml = archive.read("word/document.xml").decode("utf-8")
    assert "ICHKI DALILLAR VARAQASI" in evidence_xml
    assert "uz-Latn-UZ" in xml
    assert 'w:val="15"' in settings
    assert "Arial" in styles
