"""Compound legal questions must return the union of materially relevant articles.

A question naming two legal concepts ("dominant korxona *raqobatga qarshi kelishuv*
qilsa...") is retrieved against two articles on purpose. Regression cover keeps that
union intact without letting single-concept questions widen into neighbouring norms.
"""

import io

import pytest
from docx import Document as WordDocument

from app.services.grounding import extractive_legal_fallback
from app.services.legal_intent import (is_negotiation_heading, legal_concepts)

LAW = (
    "13-modda. Ustun mavqe\n"
    "Xo‘jalik yurituvchi subyektning tovar bozoridagi ulushi qirq foizni va undan "
    "ortiqni tashkil etsa, uning holati ustun mavqe deb e’tirof etiladi.\n\n"
    "14-modda. Ustun muzokara kuchi\n"
    "Ustun muzokara kuchi bitim shartlarini bir tomonlama belgilash imkoniyatidir.\n\n"
    "18-modda. Ustun mavqeni va ustun muzokara kuchini suiiste’mol qilishni taqiqlash\n"
    "Ustun mavqeni suiiste’mol qilish taqiqlanadi.\n\n"
    "19-modda. Raqobatga qarshi kelishuvlarni taqiqlash\n"
    "Raqobatga qarshi kelishuvlarni va muvofiqlashtirilgan harakatlarni tuzish taqiqlanadi.\n\n"
    "29-modda. Savdolarda raqobatni cheklashga qarshi talablar\n"
    "Savdolarda raqobatni cheklovchi harakatlar taqiqlanadi.\n"
)


def law_docx(text: str = LAW) -> bytes:
    stream = io.BytesIO()
    document = WordDocument()
    for paragraph in text.split("\n"):
        document.add_paragraph(paragraph)
    document.save(stream)
    return stream.getvalue()


@pytest.fixture
def indexed_law(client, admin_headers):
    response = client.post(
        "/api/nhh", headers=admin_headers,
        data={"title": "Raqobat to‘g‘risida (O‘RQ-850)", "category": "Qonun",
              "official_number": "O‘RQ-850", "source_url": "https://lex.uz/compound-routing"},
        files={"file": ("qonun.docx", law_docx())},
    )
    assert response.status_code == 201, response.text
    return response.json()


def ask(client, headers, question: str) -> dict:
    response = client.post("/api/chat", headers=headers,
                           json={"question": question, "legal": True})
    assert response.status_code == 200, response.text
    return response.json()


def articles(result: dict) -> list[str]:
    return [source.get("display_label") or source.get("article_or_clause")
            for source in result["sources"]]


# --- concept model -----------------------------------------------------------

@pytest.mark.parametrize("question,expected", [
    ("Dominant korxona raqobatga qarshi kelishuv qilsa qaysi normalar tegishli?",
     ("dominance", "agreements")),
    ("Ustun mavqedagi korxona kelishuv tuzsa qaysi moddalar qo‘llaniladi?",
     ("dominance", "agreements")),
    ("Ustun mavqe va raqobatga qarshi kelishuv bo‘yicha huquqiy asoslarni ko‘rsat",
     ("dominance", "agreements")),
    # Abuse of dominance is one topic, not two: it must stay on a single article.
    ("Ustun mavqeni suiiste’mol qilish nima?", ("abuse",)),
    ("Raqobat to‘g‘risidagi qonunda ustun mavqeni aniqlash mezonlarini top", ("dominance",)),
    ("Raqobatga qarshi kelishuvlar qaysi moddada tartibga solingan?", ("agreements",)),
    ("Savdolarda raqobatni cheklash bo‘yicha talablarni top", ("trade_restrictions",)),
])
def test_distinct_topics_are_detected_per_question(question, expected):
    concepts = legal_concepts(question)
    assert concepts.distinct_topics == expected
    assert concepts.is_compound is (len(expected) > 1)


def test_abuse_heading_is_not_treated_as_a_bargaining_power_definition():
    """18-modda names bargaining power but prohibits abusing it; it is not a definition."""
    assert is_negotiation_heading("14-modda. Ustun muzokara kuchi") is True
    assert is_negotiation_heading(
        "18-modda. Ustun mavqeni va ustun muzokara kuchini suiiste’mol qilishni taqiqlash"
    ) is False


# --- routing -----------------------------------------------------------------

@pytest.mark.parametrize("question,expected", [
    ("Raqobat to‘g‘risidagi qonunda ustun mavqeni aniqlash mezonlarini top", ["13-modda"]),
    ("Ustun mavqeni suiiste’mol qilish nima?", ["18-modda"]),
    ("Raqobatga qarshi kelishuvlar qaysi moddada tartibga solingan?", ["19-modda"]),
    ("Savdolarda raqobatni cheklash bo‘yicha talablarni top", ["29-modda"]),
])
def test_single_intent_query_returns_only_the_intended_article(
        client, xodim_headers, indexed_law, question, expected):
    assert articles(ask(client, xodim_headers, question)) == expected


@pytest.mark.parametrize("question", [
    "Dominant korxona raqobatga qarshi kelishuv qilsa qaysi normalar tegishli?",
    "Ustun mavqedagi korxona kelishuv tuzsa qaysi moddalar qo‘llaniladi?",
    "Dominant kompaniya raqobatga qarshi kelishuv qilgan bo‘lsa qaysi normalar tegishli?",
    "Ustun mavqe va raqobatga qarshi kelishuv bo‘yicha huquqiy asoslarni ko‘rsat",
])
def test_compound_query_returns_the_union_of_relevant_articles(
        client, xodim_headers, indexed_law, question):
    result = ask(client, xodim_headers, question)
    assert articles(result) == ["13-modda", "19-modda"]
    # Neither neighbouring article may ride along.
    assert "18-modda" not in articles(result) and "29-modda" not in articles(result)


def test_compound_answer_cites_every_returned_source(client, xodim_headers, indexed_law):
    result = ask(
        client, xodim_headers,
        "Dominant korxona raqobatga qarshi kelishuv qilsa qaysi normalar tegishli?",
    )
    assert len(result["sources"]) == 2
    for source in result["sources"]:
        assert f"[{source['citation_number']}]" in result["answer"]
    # Citation numbers are backend-owned, contiguous and in display order.
    assert [source["citation_number"] for source in result["sources"]] == [1, 2]


def test_nonexistent_article_is_not_substituted_in_a_compound_shaped_query(
        client, xodim_headers, indexed_law):
    result = ask(client, xodim_headers, "99-modda haqida ma’lumot ber")
    assert result["result_kind"] == "no_sources"
    assert result["sources"] == []
    assert "yetarli huquqiy asos topilmadi" in result["answer"]
    for absent in ("13-modda", "18-modda", "19-modda", "29-modda"):
        assert absent not in result["answer"]


def test_compound_article_order_is_deterministic(client, xodim_headers, indexed_law):
    question = "Dominant korxona raqobatga qarshi kelishuv qilsa qaysi normalar tegishli?"
    observed = {
        tuple((source["citation_number"], source["article_or_clause"])
              for source in ask(client, xodim_headers, question)["sources"])
        for _ in range(6)
    }
    assert len(observed) == 1


def test_admin_and_xodim_get_the_same_grounded_compound_result(
        client, admin_headers, xodim_headers, indexed_law):
    question = "Dominant korxona raqobatga qarshi kelishuv qilsa qaysi normalar tegishli?"
    admin_result = ask(client, admin_headers, question)
    xodim_result = ask(client, xodim_headers, question)
    assert articles(admin_result) == articles(xodim_result) == ["13-modda", "19-modda"]
    assert admin_result["answer"] == xodim_result["answer"]
    assert [s["url"] for s in admin_result["sources"]] == [s["url"] for s in xodim_result["sources"]]


def test_provider_failure_still_returns_both_compound_articles(
        client, xodim_headers, indexed_law, monkeypatch):
    """The original defect: the extractive fallback kept only the first source."""
    from app.services.llm import llm

    async def unavailable(*_args, **_kwargs):
        from fastapi import HTTPException
        raise HTTPException(429, "AI xizmati band")

    monkeypatch.setattr(llm, "generate_structured", unavailable)
    monkeypatch.setattr(llm, "generate", unavailable)
    result = ask(
        client, xodim_headers,
        "Dominant korxona raqobatga qarshi kelishuv qilsa qaysi normalar tegishli?",
    )
    assert result["result_kind"] == "source_matches"
    assert articles(result) == ["13-modda", "19-modda"]
    for source in result["sources"]:
        assert f"[{source['citation_number']}]" in result["answer"]


def test_fallback_renders_and_cites_every_supplied_source():
    sources = [
        {"citation_number": 1, "document_name": "Qonun", "article_or_clause": "13-modda",
         "excerpt": "13-modda. Ustun mavqe ulush asosida e’tirof etiladi."},
        {"citation_number": 2, "document_name": "Qonun", "article_or_clause": "19-modda",
         "excerpt": "19-modda. Raqobatga qarshi kelishuvlar taqiqlanadi."},
    ]
    answer, displayed = extractive_legal_fallback(sources)
    assert displayed == sources
    assert "13-modda" in answer and "19-modda" in answer
    assert answer.count("[1]") == 1 and answer.count("[2]") == 1
    # No provider/debug wording ever reaches user prose.
    for forbidden in ("AI", "fallback", "provider", "groq"):
        assert forbidden.lower() not in answer.lower()
