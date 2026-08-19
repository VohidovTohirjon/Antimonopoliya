"""The chat mode the user selects in the UI is a contract, not a hint.

"Umumiy savol" must reach the configured local LLM as an ordinary generation even
when the text mentions a law, a modda or the constitution. Legal-intent inference
is confined to the opt-in "auto" mode.
"""

import io

import pytest
from docx import Document as WordDocument

from app.schemas import ChatRequest
from app.services import ai_agent
from app.services.llm import llm

LAW = (
    "13-modda. Ustun mavqe\n"
    "Xo‘jalik yurituvchi subyektning tovar bozoridagi ulushi qirq foizni va undan "
    "ortiqni tashkil etsa, uning holati ustun mavqe deb e’tirof etiladi.\n\n"
    "19-modda. Raqobatga qarshi kelishuvlarni taqiqlash\n"
    "Raqobatga qarshi kelishuvlarni va muvofiqlashtirilgan harakatlarni tuzish taqiqlanadi.\n"
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
              "official_number": "O‘RQ-850", "source_url": "https://lex.uz/mode-contract"},
        files={"file": ("qonun.docx", law_docx())},
    )
    assert response.status_code == 201, response.text
    return response.json()


class Spy:
    """Counts LLM generations and fails loudly if legal retrieval is touched."""

    def __init__(self, monkeypatch, *, answer="Umumiy javob.", block_retrieval=True):
        self.llm_calls: list[dict] = []

        async def fake_generate(system, user, **options):
            self.llm_calls.append({"user": user, "options": options})
            return answer

        async def fake_structured(system, user, schema, **options):
            self.llm_calls.append({"user": user, "options": options})
            return {"answer_blocks": [{"text": "Manba asosida javob", "source_ids": ["L1"]}]}

        monkeypatch.setattr(llm, "generate", fake_generate)
        monkeypatch.setattr(llm, "generate_structured", fake_structured)

        if block_retrieval:
            def forbidden(*_args, **_kwargs):
                raise AssertionError("general rejimda huquqiy qidiruv ishlamasligi kerak")

            for name in ("search_async", "legal_lexical_fallback", "filter_legal_topic",
                         "distinct_source_chunks", "prefer_article_starts",
                         "expand_article_sources"):
                monkeypatch.setattr(ai_agent, name, forbidden)


# --- request contract ----------------------------------------------------------

@pytest.mark.parametrize("payload,expected", [
    ({"question": "savol", "mode": "general"}, "general"),
    ({"question": "savol", "mode": "legal"}, "legal"),
    ({"question": "savol", "mode": "auto"}, "auto"),
    # Explicit mode wins over the legacy boolean.
    ({"question": "savol", "mode": "general", "legal": True}, "general"),
    ({"question": "savol", "mode": "legal", "legal": False}, "legal"),
    # Legacy clients that only send `legal` keep working.
    ({"question": "savol", "legal": False}, "general"),
    ({"question": "savol", "legal": True}, "legal"),
    ({"question": "savol"}, "legal"),
])
def test_mode_resolution_is_unambiguous(payload, expected):
    assert ChatRequest(**payload).resolved_mode == expected


# --- general mode --------------------------------------------------------------

@pytest.mark.parametrize("question", [
    "Sun’iy intellekt nima?",
    "Konstitutsiya nima?",
    "O‘zbekiston Konstitutsiyasida nechta modda bor?",
    "Raqobat qonuni nima?",
    "13-modda haqida umumiy tushuncha ber",
])
def test_general_mode_never_becomes_legal_rag(client, xodim_headers, indexed_law,
                                              monkeypatch, question):
    """Legal vocabulary must not hijack an explicitly general request."""
    spy = Spy(monkeypatch, answer="Bu umumiy javob.")
    response = client.post("/api/chat", headers=xodim_headers,
                           json={"question": question, "mode": "general"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["effective_mode"] == "general"
    assert body["evidence_context"] == "general"
    assert body["routed_to_legal"] is False
    assert body["sources"] == [], "umumiy javobga huquqiy manba biriktirilmasligi kerak"
    assert body["answer"] == "Bu umumiy javob."
    assert len(spy.llm_calls) == 1, "general rejim aynan bitta LLM chaqirig‘i qilishi kerak"


def test_general_mode_records_general_history(client, xodim_headers, monkeypatch):
    Spy(monkeypatch)
    client.post("/api/chat", headers=xodim_headers,
                json={"question": "Konstitutsiya nima?", "mode": "general"})
    history = client.get("/api/history", headers=xodim_headers).json()
    assert history[0]["operation"] == "general_chat"


# --- auto mode retains the old inference --------------------------------------

def test_auto_mode_still_routes_a_legal_question(client, xodim_headers, indexed_law,
                                                 monkeypatch):
    Spy(monkeypatch, block_retrieval=False)
    response = client.post("/api/chat", headers=xodim_headers, json={
        "question": "Raqobatga qarshi kelishuvlar qaysi moddada tartibga solingan?",
        "mode": "auto"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["effective_mode"] == "legal"
    assert body["routed_to_legal"] is True


def test_auto_mode_leaves_a_non_legal_question_general(client, xodim_headers, monkeypatch):
    Spy(monkeypatch)
    response = client.post("/api/chat", headers=xodim_headers,
                           json={"question": "Sun’iy intellekt nima?", "mode": "auto"})
    assert response.status_code == 200, response.text
    assert response.json()["effective_mode"] == "general"


# --- legal mode ----------------------------------------------------------------

def test_legal_mode_uses_retrieval_and_returns_citations(client, xodim_headers,
                                                         indexed_law, monkeypatch):
    Spy(monkeypatch, block_retrieval=False)
    response = client.post("/api/chat", headers=xodim_headers, json={
        "question": "Raqobatga qarshi kelishuvlar qaysi moddada tartibga solingan?",
        "mode": "legal"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["effective_mode"] == "legal"
    assert body["sources"], "huquqiy rejim manba qaytarishi kerak"
    for source in body["sources"]:
        assert source["evidence_type"] == "nhh"
        assert f"[{source['citation_number']}]" in body["answer"]


def test_legal_mode_without_relevant_evidence_says_so(client, xodim_headers,
                                                      indexed_law, monkeypatch):
    """An unrelated law must never be presented as authority for another topic."""
    Spy(monkeypatch, block_retrieval=False)
    response = client.post("/api/chat", headers=xodim_headers, json={
        "question": "O‘zbekiston Konstitutsiyasida nechta modda bor?", "mode": "legal"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result_kind"] == "no_sources"
    assert body["sources"] == []
    assert "yetarli huquqiy asos topilmadi" in body["answer"]
    assert "O‘RQ-850" not in body["answer"] and "Raqobat" not in body["answer"]


# --- off-topic evidence guard -------------------------------------------------

def _chunk(article: str, text: str, title="Raqobat to‘g‘risida (O‘RQ-850)"):
    from types import SimpleNamespace
    return SimpleNamespace(nhh=SimpleNamespace(title=title), document=None,
                           article_clause=article, text=text)


def test_off_topic_evidence_is_refused_even_when_retrieval_returns_it():
    """Vector similarity alone must not turn an unrelated statute into authority.

    Legal texts resemble each other, so a question the concept model does not know
    ("Konstitutsiyada nechta modda bor?") can clear the similarity floor against the
    competition law. Retrieval thresholds stay untouched; the result is simply not
    presented as evidence.
    """
    from app.services.ai_agent import _evidence_is_on_topic

    unrelated = [
        _chunk("45-modda. Nizolarni hal etish", "Nizolar sud tartibida hal etiladi."),
        _chunk("46-modda. Yakuniy qoidalar", "Ushbu Qonun rasmiy e’lon qilingan kundan kuchga kiradi."),
    ]
    assert _evidence_is_on_topic("O‘zbekiston Konstitutsiyasida nechta modda bor?",
                                 unrelated) is False

    # A question naming a known legal concept keeps its evidence.
    dominance = [_chunk("13-modda. Ustun mavqe", "Bozordagi ulush qirq foizdan ortiq bo‘lsa.")]
    assert _evidence_is_on_topic("Ustun mavqe qanday aniqlanadi?", dominance) is True

    # An explicitly requested article is always admissible.
    assert _evidence_is_on_topic("45-modda haqida ma’lumot ber", unrelated) is True

    # Subject-matter overlap without a modelled concept still counts.
    tariffs = [_chunk("16-modda. Tabiiy monopoliya tariflari",
                      "Tabiiy monopoliya subyektlari tariflari tasdiqlanadi.")]
    assert _evidence_is_on_topic("Tabiiy monopoliya tariflari qanday tasdiqlanadi?",
                                 tariffs) is True

    assert _evidence_is_on_topic("Savol", []) is False
