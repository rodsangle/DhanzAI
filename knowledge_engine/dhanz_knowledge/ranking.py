"""Chunking and ranking utilities (no external services)."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

_TOKEN = re.compile(r"[\w][\w'-]*", re.UNICODE)
STOPWORDS = frozenset(
    """a an and are as at be by can do does for from has have how i in is it its me my of on or our please should
    so tell that the their them then there these this to us was we were what when where which who why will with
    you your about into than also any some just more most search internet web latest find look up show give""".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in (m.lower() for m in _TOKEN.findall(text)) if t not in STOPWORDS and len(t) > 1]


def chunk_text(text: str, *, target_chars: int = 1600, overlap_chars: int = 200) -> list[str]:
    """Split on paragraph boundaries into ~target_chars chunks with a small overlap for context."""
    paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        while len(para) > target_chars:  # very long paragraph: hard split on sentence-ish boundary
            cut = para.rfind(". ", 0, target_chars)
            cut = cut + 1 if cut > target_chars // 2 else target_chars
            pieces = [para[:cut].strip(), para[cut:].strip()]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(pieces[0])
            para = pieces[1]
        if current and len(current) + len(para) + 1 > target_chars:
            chunks.append(current)
            tail = current[-overlap_chars:]
            space = tail.find(" ")
            current = (tail[space + 1 :] if space >= 0 else tail) + "\n" + para
        else:
            current = f"{current}\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks


def bm25_scores(query: str, docs: Sequence[str], *, k1: float = 1.5, b: float = 0.75) -> list[float]:
    q = tokenize(query)
    if not q or not docs:
        return [0.0] * len(docs)
    tokenized = [tokenize(d) for d in docs]
    avgdl = sum(len(t) for t in tokenized) / len(tokenized) or 1.0
    df = Counter(term for toks in tokenized for term in set(toks))
    n = len(docs)
    scores = []
    for toks in tokenized:
        tf = Counter(toks)
        score = 0.0
        for term in q:
            if term not in tf:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * tf[term] * (k1 + 1) / (tf[term] + k1 * (1 - b + b * len(toks) / avgdl))
        scores.append(score)
    return scores


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def reciprocal_rank_fusion(rankings: Sequence[Sequence[int]], k: int = 60) -> dict[int, float]:
    """Combine several ranked lists of item indexes into one score per item."""
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank + 1)
    return fused
