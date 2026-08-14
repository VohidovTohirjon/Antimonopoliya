"""Generic deterministic facts extracted from retrieved legal evidence.

This module deliberately knows nothing about a particular law or article number.  It
operates on the sources selected by the RAG layer, so newly indexed legislation gets
the same numeric and list handling without production-code changes.
"""

import re
from dataclasses import dataclass
from decimal import Decimal

from .grounding import _complete_excerpt, _latin_explanation, article_label
from .legal_intent import LegalConcepts, legal_concepts


@dataclass(frozen=True)
class LegalSourceFacts:
    label: str
    text: str
    clauses: tuple[str, ...]
    percentages: tuple[Decimal, ...]
    source: dict


NUMBER_UNITS = {
    "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "besh": 5,
    "olti": 6, "yetti": 7, "sakkiz": 8, "to'qqiz": 9,
}
NUMBER_TENS = {
    "o'n": 10, "yigirma": 20, "o'ttiz": 30, "qirq": 40, "ellik": 50,
    "oltmish": 60, "yetmish": 70, "sakson": 80, "to'qson": 90,
}


def _word_number(value: str) -> int | None:
    tokens = re.findall(r"[a-z']+", value.lower())
    total = current = 0
    recognized = False
    for token in tokens:
        if token in NUMBER_UNITS:
            current += NUMBER_UNITS[token]
            recognized = True
        elif token in NUMBER_TENS:
            current += NUMBER_TENS[token]
            recognized = True
        elif token == "yuz":
            current = (current or 1) * 100
            recognized = True
        elif token == "ming":
            total += (current or 1) * 1000
            current = 0
            recognized = True
    return total + current if recognized else None


def _decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def _fmt(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


def parse_legal_source(source: dict) -> LegalSourceFacts | None:
    raw = source.get("full_excerpt") or source.get("excerpt") or ""
    text = _latin_explanation(re.sub(r"\s+", " ", raw).strip())
    if not text:
        return None
    percentages = [_decimal(value) for value in re.findall(r"(\d+(?:[.,]\d+)?)\s*foiz", text,
                                                           flags=re.IGNORECASE)]
    for words in re.findall(r"([a-z‘’'\s-]{2,30})\s+foiz", text, flags=re.IGNORECASE):
        parsed = _word_number(words.replace("‘", "'").replace("’", "'"))
        if parsed is not None:
            percentages.append(Decimal(parsed))
    normalized_clauses: list[str] = []
    for part in re.split(r";|(?<=\.)\s+(?=[A-ZА-ЯO‘G‘])", text):
        clause = part.strip(" -;.")
        if len(clause) >= 25:
            normalized_clauses.append(clause + ("" if clause.endswith(".") else "."))
    return LegalSourceFacts(
        article_label(source), text, tuple(normalized_clauses),
        tuple(dict.fromkeys(percentages)), source,
    )


def _citation(source: dict) -> str:
    return f"[{source['citation_number']}]"


def _share_threshold(facts: LegalSourceFacts) -> Decimal | None:
    patterns = (
        r"(?:bozor(?:dagi)?\s+)?ulushi\s+(\d+(?:[.,]\d+)?)\s*foiz",
        r"(\d+(?:[.,]\d+)?)\s*foiz(?:dan|ga)?\s+(?:teng|ortiq|kam)",
    )
    for pattern in patterns:
        match = re.search(pattern, facts.text, flags=re.IGNORECASE)
        if match:
            return _decimal(match.group(1))
    return facts.percentages[0] if len(facts.percentages) == 1 else None


def _relevant_clauses(facts: LegalSourceFacts, question: str, limit: int = 6) -> list[str]:
    stop = {"qanday", "qaysi", "uchun", "bilan", "bo'yicha", "haqida", "nima", "bor",
            "modda", "band", "qonun", "qonunda", "hollarda", "shartlar", "mezonlar"}
    terms = {word for word in re.findall(r"[a-z0-9‘’']{4,}", question.lower()) if word not in stop}
    ranked = sorted(
        facts.clauses,
        key=lambda clause: sum(term in clause.lower() for term in terms),
        reverse=True,
    )
    return ranked[:limit]


def deterministic_legal_fact_answer(question: str,
                                    sources: list[dict]) -> tuple[str, list[dict]] | None:
    """Answer only facts that can be deterministically read from retrieved sources."""
    concepts: LegalConcepts = legal_concepts(question)
    parsed = [facts for source in sources if (facts := parse_legal_source(source))]
    if not parsed:
        return None

    if concepts.requested_share is not None:
        candidates = [(facts, _share_threshold(facts)) for facts in parsed]
        candidates = [(facts, threshold) for facts, threshold in candidates if threshold is not None]
        if candidates:
            facts, threshold = candidates[0]
            requested = concepts.requested_share
            relation = "qanoatlantiradi" if requested >= threshold else "o‘z-o‘zidan qanoatlantirmaydi"
            answer = (
                f"**To‘g‘ridan-to‘g‘ri javob:** {_fmt(requested)}% ko‘rsatkich manbada qayd "
                f"etilgan {_fmt(threshold)}% mezonni {relation}. {_citation(facts.source)}\n\n"
                "Bu faqat sonli mezon taqqoslanishidir; yakuniy huquqiy bahoda shu normadagi "
                f"boshqa shartlar va istisnolar ham tekshiriladi. {_citation(facts.source)}"
            )
            return answer, [facts.source]

    asks_list = bool(re.search(
        r"\b(mezon\w*|shart\w*|qaysi hollarda|qanday hollarda|nimalar|ro'yxat)\b",
        question.lower(),
    ))
    if asks_list:
        facts = parsed[0]
        clauses = _relevant_clauses(facts, question)
        if clauses:
            lines = [f"**{facts.label} bo‘yicha manbada qayd etilgan shartlar:**"]
            lines.extend(f"- {clause} {_citation(facts.source)}" for clause in clauses)
            return "\n".join(lines), [facts.source]

    asks_articles = bool(re.search(r"\b(qanday|qaysi|nechta)\s+modda|moddalar\s+bor", question.lower()))
    if asks_articles:
        lines = ["Mavjud bazada savolga mos topilgan normalar:"]
        used: list[dict] = []
        for facts in parsed:
            excerpt = _complete_excerpt(facts.text, 360)
            lines.append(f"- **{facts.label}:** {excerpt} {_citation(facts.source)}")
            used.append(facts.source)
        return "\n".join(lines), used

    return None
