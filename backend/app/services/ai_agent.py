import re
import logging
import time
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Chunk, NhhDocument, User
from .llm import llm
from .legal_facts import deterministic_legal_fact_answer
from .legal_intent import legal_concepts
from .grounding import (article_label, extractive_document_fallback,
                        extractive_legal_fallback, latin_legal_answer, used_sources,
                        repair_document_citations, validate_cited_answer,
                        validate_legal_answer)
from .rag import (_has_topical_overlap, _requested_article_number, filter_legal_topic,
                  legal_lexical_fallback, search_async, sources_from_chunks, clean_excerpt)


LEGAL_INTENT_PATTERNS = (
    r"\bqonun(?:chilik\w*|iy|da|ning|lar)?\b",
    r"\b(?:normativ|huquqiy|huquq|kodeks)\b",
    r"\b\d+[.-]?\s*(?:modda|band)\b",
    r"\b(?:modda(?:lar|si|ning|da)?|farmon|nizom|sanksiya|javobgarlik)\b",
    r"\b(?:prezident|vazirlar mahkamasi)\s+qarori\b",
    r"\b(?:ustun\s+mavqe\w*|raqobatga\s+qarshi|raqobatni\s+chekl\w*)\b",
    r"\blex\.uz\b",
    r"\b(?:норматив\w*|ҳуқуқий\w*|ҳуқуқ\w*|қонун\w*|кодекс\w*|модда\w*|банд\w*|фармон\w*|низом\w*)\b",
)
LEGAL_INTENT_RE = re.compile("|".join(LEGAL_INTENT_PATTERNS), re.IGNORECASE)
logger = logging.getLogger(__name__)

LEGAL_ANSWER_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["answer_blocks"],
    "properties": {
        "answer_blocks": {
            "type": "array", "minItems": 1, "maxItems": 5,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["text", "source_ids"],
                "properties": {
                    "text": {"type": "string"},
                    "source_ids": {
                        "type": "array", "minItems": 1,
                        "items": {"type": "string", "pattern": "^L[1-9][0-9]*$"},
                    },
                },
            },
        },
    },
}


@dataclass
class ChatOutcome:
    answer: str
    sources: list[dict]
    result_kind: str
    warning: str | None
    operation: str
    effective_mode: str
    routed_to_legal: bool


@dataclass
class GroundedGeneration:
    answer: str
    sources: list[dict]
    result_kind: str
    warning: str | None
    failure_reason: str | None = None


def _failure_reason(exc: HTTPException) -> str:
    detail = str(exc.detail).lower()
    if exc.status_code == 429:
        return "rate_limited"
    if exc.status_code == 504:
        return "timeout"
    if "uzunlik" in detail or "uzildi" in detail:
        return "truncated"
    return "provider_unavailable"


def _uncovered_compound_sources(question: str, sources: list[dict],
                                used_citation_ids: tuple[int, ...]) -> tuple[int, ...]:
    """Citation numbers a compound question left unanswered.

    A question naming several legal concepts (dominance *and* anti-competitive
    agreements) is retrieved against several articles on purpose. If the model
    answers only one of them, the reply is incomplete rather than wrong, so it is
    sent back for one correction and otherwise degrades to the extractive answer,
    which cites every verified source. Single-concept questions are untouched.
    """
    if len(sources) < 2 or not legal_concepts(question).is_compound:
        return ()
    used = set(used_citation_ids)
    return tuple(source["citation_number"] for source in sources
                 if source["citation_number"] not in used)


def _friendly_failure(reason: str, _subject: str = "") -> str:
    if reason in {"provider_unavailable", "rate_limited", "timeout", "truncated"}:
        return "AI xizmati vaqtincha mavjud emas. Tekshirilgan huquqiy manbalar ko‘rsatildi."
    return "AI izohi manbalar bilan to‘liq tasdiqlanmagani sababli faqat tekshirilgan huquqiy asoslar ko‘rsatildi."


def has_legal_intent(question: str) -> bool:
    """Route explicit legal/normative requests away from ungrounded general generation."""
    normalized = (question.lower().replace("’", "'").replace("‘", "'")
                  .replace("ʻ", "'").replace("`", "'"))
    concepts = legal_concepts(question)
    return bool(LEGAL_INTENT_RE.search(normalized) or concepts.dominant or concepts.abuse
                or concepts.negotiation_power or concepts.agreements
                or concepts.trade_restrictions)


def _source_identity(chunk: Chunk) -> tuple[str, str]:
    document_id = chunk.nhh_id or chunk.document_id or ""
    article = re.sub(r"\s+", " ", (chunk.article_clause or "").lower()).strip()
    if article:
        return document_id, article
    words = re.findall(r"\w+", chunk.text.lower(), flags=re.UNICODE)
    return document_id, " ".join(words[:24])


def _word_set(value: str) -> set[str]:
    return set(re.findall(r"\w+", value.lower(), flags=re.UNICODE))


def distinct_source_chunks(chunks: list[Chunk], limit: int = 5) -> list[Chunk]:
    """Keep the best-ranked chunk for an article and collapse highly-overlapping excerpts."""
    result: list[Chunk] = []
    identities: set[tuple[str, str]] = set()
    for chunk in chunks:
        identity = _source_identity(chunk)
        if identity in identities:
            continue
        words = _word_set(chunk.text)
        duplicate = False
        for existing in result:
            if (existing.nhh_id or existing.document_id) != (chunk.nhh_id or chunk.document_id):
                continue
            other = _word_set(existing.text)
            union = words | other
            if union and len(words & other) / len(union) >= 0.72:
                duplicate = True
                break
        if duplicate:
            continue
        identities.add(identity)
        result.append(chunk)
        if len(result) >= limit:
            break
    return result


def prefer_article_starts(db: Session, chunks: list[Chunk]) -> list[Chunk]:
    """Display a coherent article beginning instead of a ranked continuation fragment."""
    result: list[Chunk] = []
    for chunk in chunks:
        if not chunk.nhh_id or not chunk.article_clause:
            result.append(chunk)
            continue
        first = db.scalar(
            select(Chunk)
            .where(Chunk.nhh_id == chunk.nhh_id, Chunk.article_clause == chunk.article_clause)
            .order_by(Chunk.chunk_order, Chunk.id)
            .limit(1)
        )
        result.append(first or chunk)
    return result


def grounded_context(chunks: list[Chunk]) -> str:
    settings = get_settings()
    parts: list[str] = []
    length = 0
    for index, chunk in enumerate(chunks, 1):
        name = chunk.nhh.title if chunk.nhh else chunk.document.filename
        block = (
            f"[MANBA {index}]\n"
            f"HUJJAT: {name}\n"
            f"MODDA/BAND: {chunk.article_clause or 'aniqlanmagan'}\n"
            f"RASMIY PARCHA:\n{chunk.text}"
        )
        if parts and length + len(block) > settings.context_max_chars:
            break
        parts.append(block)
        length += len(block)
    return "\n\n".join(parts)


def expand_article_sources(db: Session, chunks: list[Chunk], sources: list[dict]) -> list[dict]:
    """Attach the complete stored article to one source card/citation."""
    expanded: list[dict] = []
    for chunk, source in zip(chunks, sources):
        parts = [chunk]
        if chunk.nhh_id and chunk.article_clause:
            parts = list(db.scalars(
                select(Chunk)
                .where(Chunk.nhh_id == chunk.nhh_id,
                       Chunk.article_clause == chunk.article_clause)
                .order_by(Chunk.chunk_order, Chunk.id)
            )) or [chunk]
        full = ""
        for item in parts:
            piece = re.sub(r"\s+", " ", item.text).strip()
            if not piece or piece in full:
                continue
            overlap = 0
            for size in range(min(len(full), len(piece)), 39, -1):
                if full[-size:] == piece[:size]:
                    overlap = size
                    break
            full = f"{full} {piece[overlap:]}".strip()
        expanded.append({**source, "excerpt": clean_excerpt(full, 700),
                         "full_excerpt": re.sub(r"\s+", " ", full).strip()})
    return expanded


def grounded_source_context(sources: list[dict]) -> str:
    settings = get_settings()
    blocks: list[str] = []
    length = 0
    for index, source in enumerate(sources, 1):
        block = (
            f"[MANBA {index}]\nHUJJAT: {source['document_name']}\n"
            f"MODDA/BAND: {source.get('article_or_clause') or 'aniqlanmagan'}\n"
            f"RASMIY PARCHA:\n{source.get('full_excerpt') or source.get('excerpt') or ''}"
        )
        if blocks and length + len(block) > settings.context_max_chars:
            break
        blocks.append(block)
        length += len(block)
    return "\n\n".join(blocks)


def source_matches_answer(sources: list[dict], question: str = "") -> str:
    answer, _ = extractive_legal_fallback(sources, question=question)
    return answer


def deterministic_legal_answer(question: str, sources: list[dict]) -> tuple[str, list[dict]] | None:
    return deterministic_legal_fact_answer(question, sources)


def _render_legal_blocks(value: dict, sources: list[dict]) -> tuple[str, tuple[int, ...]] | None:
    blocks = value.get("answer_blocks")
    if not isinstance(blocks, list) or not blocks:
        return None
    allowed = {f"L{index}": source["citation_number"] for index, source in enumerate(sources, 1)}
    lines: list[str] = []
    used: list[int] = []
    for block in blocks:
        if not isinstance(block, dict) or not isinstance(block.get("text"), str):
            return None
        ids = block.get("source_ids")
        if not isinstance(ids, list) or not ids or any(value not in allowed for value in ids):
            return None
        citations = []
        for source_id in ids:
            number = allowed[source_id]
            if number not in used:
                used.append(number)
            citations.append(str(number))
        text = block["text"].strip()
        if not text:
            return None
        lines.append(f"{text} [{', '.join(citations)}]")
    return "\n\n".join(lines), tuple(used)


async def generate_grounded_legal(system: str, prompt: str,
                                  sources: list[dict], *,
                                  question: str = "",
                                  additional_evidence: str = "",
                                  compact_prompt: str | None = None,
                                  budget_kind: str = "legal",
                                  allow_external: bool = True) -> GroundedGeneration:
    """Bounded generate -> validate -> one correction -> extractive fallback pipeline."""
    if not allow_external:
        answer, verified = extractive_legal_fallback(sources, question=question)
        return GroundedGeneration(
            answer, verified, "source_matches",
            "Maxfiy yoki ichki ma’lumot tashqi AI xizmatiga yuborilmadi; faqat lokal tekshirilgan parchalar ko‘rsatildi.",
            "confidential_external_blocked",
        )
    last_violations: tuple[str, ...] = ()
    budget = get_settings().max_tokens_for(budget_kind)
    try:
        for attempt in range(2):
            request = re.sub(r"\[MANBA\s+(\d+)\]", r"[L\1]", prompt)
            if attempt:
                request += (
                    "\n\nOLDINGI JAVOB VALIDATSIYADAN O‘TMADI. Quyidagi xatolarni tuzating va "
                    "faqat berilgan manbalarga tayangan yangi to‘liq javob qaytaring:\n- "
                    + "\n- ".join(last_violations)
                )
            structured = await llm.generate_structured(
                system + " Javobni answer_blocks tuzilmasida qaytaring. Har bir blokda faqat "
                "manbada mavjud da'voni yozing va L1, L2 ko‘rinishidagi source_ids bering. "
                "O‘zbek lotin yozuvida tabiiy va ixcham bayon qiling.",
                request, LEGAL_ANSWER_SCHEMA, max_tokens=budget,
            )
            rendered = _render_legal_blocks(structured, sources)
            if not rendered:
                last_violations = ("Javob bloklari yoki manba identifikatorlari yaroqsiz",)
                continue
            generated, _ = rendered
            validation = validate_legal_answer(generated, sources, additional_evidence)
            uncovered = _uncovered_compound_sources(question, sources, validation.used_citation_ids)
            if validation.valid and not uncovered:
                return GroundedGeneration(
                    latin_legal_answer(validation.answer),
                    used_sources(sources, validation.used_citation_ids),
                    "ok",
                    None,
                )
            last_violations = validation.violations or (
                "Savol bir nechta huquqiy tushunchani qamrab oladi; har bir tekshirilgan "
                "manbaga alohida javob bloki va citation bering: "
                + ", ".join(f"[{value}]" for value in uncovered),
            )
            logger.warning(
                "Grounding validation failed request_type=legal attempt=%s violations=%s",
                attempt + 1, "; ".join(last_violations),
            )
            # A factual grounding failure (invented article, citation, number, date,
            # quote or legal identifier) is not worth a second generation: the
            # verified extractive answer is both faster and safer. Only a
            # presentation-level problem earns a correction round.
            repairable = validation.repairable if validation.violations else bool(uncovered)
            if not repairable:
                logger.info(
                    "Skipping correction call request_type=legal reason=hard_grounding_failure "
                    "codes=%s", ",".join(validation.codes),
                )
                break
    except HTTPException as exc:
        reason = _failure_reason(exc)
        answer, verified = extractive_legal_fallback(sources, question=question)
        return GroundedGeneration(answer, verified, "source_matches",
                                  _friendly_failure(reason, "Huquqiy javob"), reason)

    answer, verified = extractive_legal_fallback(sources, question=question)
    return GroundedGeneration(answer, verified, "source_matches",
                              _friendly_failure("validation_failed", "Huquqiy javob"),
                              "validation_failed")


async def generate_grounded_document(system: str, prompt: str,
                                     sources: list[dict], *,
                                     allow_external: bool = True) -> GroundedGeneration:
    """Require every document-analysis result to map to displayed evidence."""
    if not allow_external:
        answer, verified = extractive_document_fallback(
            sources,
            "Maxfiy hujjat matni tashqi AI xizmatiga yuborilmadi; lokal ajratilgan asl parchalar ko‘rsatildi.",
        )
        return GroundedGeneration(
            answer, verified, "source_matches",
            "Maxfiy hujjat uchun tashqi AI ishlatilmadi; faqat lokal tekshirilgan parchalar ko‘rsatildi.",
            "confidential_external_blocked",
        )
    last_violations: tuple[str, ...] = ()
    budget = get_settings().max_tokens_for("document")
    try:
        for attempt in range(2):
            request = prompt
            if attempt:
                request += (
                    "\n\nOLDINGI JAVOB DALIL TEKSHIRUVIDAN O‘TMADI. Xatolarni tuzating va "
                    "har bir fakt yoki xulosadan keyin mos [1] citation yozing:\n- "
                    + "\n- ".join(last_violations)
                )
            generated = await llm.generate(system, request, temperature=0.0,
                                           max_tokens=budget)
            generated = repair_document_citations(generated, sources)
            validation = validate_cited_answer(generated, sources)
            if validation.valid:
                return GroundedGeneration(
                    validation.answer,
                    used_sources(sources, validation.used_citation_ids),
                    "ok",
                    None,
                )
            last_violations = validation.violations
            # Same rule as the legal path: only a missing-citation style problem is
            # worth re-prompting. An unsupported number goes straight to evidence.
            if not validation.repairable:
                logger.info(
                    "Skipping correction call request_type=document "
                    "reason=hard_grounding_failure codes=%s", ",".join(validation.codes),
                )
                break
    except HTTPException as exc:
        answer, verified = extractive_document_fallback(
            sources, "AI tahlili yaratilmadi; asl hujjat parchalari ko‘rsatildi."
        )
        reason = _failure_reason(exc)
        return GroundedGeneration(answer, verified, "source_matches",
                                  _friendly_failure(reason, "Hujjat tahlili"), reason)

    answer, verified = extractive_document_fallback(
        sources,
        "AI tahlili dalillar bilan bog‘lanmagani uchun qabul qilinmadi; asl parchalar ko‘rsatildi.",
    )
    return GroundedGeneration(answer, verified, "source_matches",
                              _friendly_failure("validation_failed", "Hujjat tahlili"),
                              "validation_failed")


def source_based_draft(title: str, instruction: str, base: str, sources: list[dict]) -> str:
    """Produce a usable, explicitly limited draft when the generation provider is unavailable."""
    lines = [
        f"# {title}",
        "",
        "> Ushbu loyiha AI generatsiya xizmati vaqtincha mavjud bo‘lmagani sababli faqat "
        "murojaat matni va tekshirilgan NHH parchalaridan avtomatik shakllantirildi. "
        "Yuborishdan oldin mas’ul xodim tahriri va huquqiy tekshiruvi talab etiladi.",
        "",
        "## Topshiriq",
        instruction,
        "",
        "## Asosiy hujjat mazmuni",
        re.sub(r"\s+", " ", base).strip()[:1800],
        "",
        "## Tekshirilgan huquqiy asoslar",
    ]
    for source in sources:
        citation = source["citation_number"]
        article = article_label(source)
        excerpt = re.sub(r"\s+", " ", source["excerpt"]).strip()
        lines.append(f"- [{citation}] **{article}** — {excerpt[:500]}")
    lines.extend([
        "",
        "## Javob loyihasi",
        "Murojaatingiz ko‘rib chiqildi. Unda bayon etilgan masalalar yuqorida ko‘rsatilgan "
        "normativ-huquqiy manbalar asosida vakolat doirasida qo‘shimcha huquqiy tekshiruvdan "
        "o‘tkaziladi. Yakuniy javobda aniqlangan holatlar, qo‘llanadigan norma va xulosa mas’ul "
        "xodim tomonidan aniq to‘ldirilishi lozim.",
    ])
    return "\n".join(lines)


def _evidence_is_on_topic(question: str, chunks: list[Chunk]) -> bool:
    """Guard against a semantically-close but topically-unrelated law.

    A question the concept model does not recognise ("Konstitutsiyada nechta modda
    bor?") can still clear the vector similarity floor against an unrelated statute,
    because legal texts resemble each other. When the question names no known legal
    concept, no explicit article, and shares no subject-matter word with any selected
    chunk, there is no evidence — only resemblance. Retrieval thresholds are
    untouched; this only refuses to present the result as authority.
    """
    if not chunks:
        return False
    concepts = legal_concepts(question)
    if concepts.distinct_topics or _requested_article_number(question):
        return True
    return any(_has_topical_overlap(question, chunk) for chunk in chunks)


async def run_chat(db: Session, user: User, question: str, mode: str = "legal") -> ChatOutcome:
    """Answer one chat request in the mode the user explicitly selected.

    The mode is a contract, not a hint. "general" never becomes legal RAG just
    because the text mentions a law, a modda or the constitution: legal-intent
    inference is confined to the opt-in "auto" mode.
    """
    started = time.monotonic()
    inferred_legal = has_legal_intent(question) if mode == "auto" else False
    legal = mode == "legal" or (mode == "auto" and inferred_legal)
    routed = mode == "auto" and inferred_legal
    if not legal:
        # A genuinely general question never touches vector retrieval, legal topic
        # filtering, article deduplication or grounding: one generation, nothing else.
        answer = await llm.generate(
            "Siz Raqobat qo‘mitasi ichki AI yordamchisisiz. O‘zbek lotin alifbosida qisqa va aniq "
            "javob bering. Fakt uydirmang. Normativ-huquqiy da’voni manbasiz tasdiqlangan fakt sifatida "
            "taqdim etmang.",
            question,
            max_tokens=get_settings().max_tokens_for("general"),
        )
        logger.info(
            "chat mode=general provider=%s model=%s llm_calls=1 retrieval_calls=0 "
            "elapsed_ms=%s", llm.provider_name, llm.active_model,
            round((time.monotonic() - started) * 1000),
        )
        return ChatOutcome(answer, [], "ok", None, "general_chat", "general", False)

    warning = None
    corpus_count = db.scalar(
        select(func.count(NhhDocument.id)).where(
            NhhDocument.is_active.is_(True), NhhDocument.indexed.is_(True)
        )
    ) or 0
    retrieval_started = time.monotonic()
    chunks = await search_async(db, question, user, "nhh", None, 12) if corpus_count else []
    if corpus_count and not chunks:
        chunks = legal_lexical_fallback(db, question, 12)
    retrieval_ms = round((time.monotonic() - retrieval_started) * 1000)
    requested_article = re.search(
        r"\b(\d{1,3})\s*[-‐‑‒–—.]?\s*(?:modda(?:si|ning|ga|da)?|модда(?:си|нинг|га|да)?)\b",
        question, re.IGNORECASE,
    )
    if requested_article:
        number = requested_article.group(1)
        article_pattern = re.compile(
            rf"\b{re.escape(number)}\s*[-‐‑‒–—.]?\s*(?:modda|модда|статья)\b",
            re.IGNORECASE,
        )
        # An explicitly requested article is a hard constraint. Returning a
        # semantically similar but different article would be legally unsafe.
        chunks = [chunk for chunk in chunks if article_pattern.search(
            f"{chunk.article_clause or ''} {chunk.text[:180]}"
        )]
    chunks = filter_legal_topic(chunks, question)
    selected = prefer_article_starts(db, distinct_source_chunks(chunks, limit=3))
    if selected and not _evidence_is_on_topic(question, selected):
        logger.info("chat mode=legal dropped_offtopic_evidence=%s",
                    [chunk.article_clause for chunk in selected])
        selected = []
    sources = expand_article_sources(db, selected, sources_from_chunks(selected))
    if not selected:
        if corpus_count == 0:
            answer = (
                "Normativ-huquqiy hujjatlar bazasi hozircha bo‘sh. Huquqiy javob olish uchun "
                "Administrator panelidagi NHH bazasiga tegishli rasmiy hujjatni nomi va manba "
                "havolasi bilan yuklab, indekslash kerak. Manbasiz huquqiy javob yaratilmaydi."
            )
            result_kind = "corpus_empty"
        else:
            answer = (
                "Mavjud normativ-huquqiy hujjatlar bazasida ushbu savolga yetarli huquqiy asos "
                "topilmadi. Savolni aniqroq modda, mavzu yoki hujjat nomi bilan qayta yozing yoxud "
                "tegishli NHHni bazaga qo‘shing."
            )
            result_kind = "no_sources"
        logger.info(
            "chat mode=legal provider=%s model=%s llm_calls=0 retrieval_ms=%s "
            "result_kind=%s sources=0 elapsed_ms=%s", llm.provider_name, llm.active_model,
            retrieval_ms, result_kind, round((time.monotonic() - started) * 1000),
        )
        return ChatOutcome(answer, [], result_kind, warning, "legal_chat", "legal", routed)

    settings = get_settings()
    deterministic = deterministic_legal_answer(question, sources)
    if deterministic:
        answer, sources = deterministic
        result_kind = "ok"
        warning = None
    internal_source = any(
        chunk.nhh and chunk.nhh.category == "Idoraviy (ichki) hujjat" for chunk in selected
    )
    external_allowed = settings.allow_external_confidential_ai or not internal_source
    if deterministic:
        pass
    elif llm.configured:
        generation = await generate_grounded_legal(
            "Siz Raqobat qo‘mitasi huquqiy yordamchisisiz. Faqat berilgan NHH parchalariga "
            "tayangan holda, o‘zbek lotin alifbosida ixcham ro‘yxat shaklida javob bering. "
            "Har bir huquqiy da’vodan keyin aynan taqdim etilgan [1] ko‘rinishidagi manba "
            "raqamini yozing. Hujjat nomi, raqami, sanasi, modda, band, iqtibos, URL yoki citation "
            "uydirmang. Yetarli asos bo‘lmasa buni aniq ayting.",
            f"SAVOL:\n{question}\n\nTEKSHIRILGAN MANBALAR:\n{grounded_source_context(sources)}",
            sources,
            question=question,
            compact_prompt=(
                f"SAVOL:\n{question}\n\nTEKSHIRILGAN MANBALAR:\n"
                f"{grounded_source_context(sources[:2])[:4500]}"
            ), allow_external=external_allowed,
        )
        answer = generation.answer
        sources = generation.sources
        result_kind = generation.result_kind
        warning = generation.warning
    else:
        answer = source_matches_answer(sources, question)
        result_kind = "source_matches"
        warning = "AI xizmati vaqtincha mavjud emas. Tekshirilgan huquqiy manbalar ko‘rsatildi."
    logger.info(
        "chat mode=legal provider=%s model=%s llm_used=%s retrieval_ms=%s result_kind=%s "
        "sources=%s elapsed_ms=%s", llm.provider_name, llm.active_model,
        not bool(deterministic), retrieval_ms, result_kind, len(sources),
        round((time.monotonic() - started) * 1000),
    )
    return ChatOutcome(answer, sources, result_kind, warning, "legal_chat", "legal", routed)
