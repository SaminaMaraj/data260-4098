"""Reference dataset access for HW9 Part 4.

* load_reference / fact_for_topic - the Evaluator's ground truth
* lookup(question)                - keyword retrieval over the fact texts; this is
                                    the Answering Agent's lookup tool
* term_present / missing_terms    - the Evaluator's rule check
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "code" / "hw9" / "part4_datasets"
REFERENCE_FILE = DATA_DIR / "reference_facts.json"

STOP = set(
    "a an the of to in on at for by with and or is are be been was were what which who "
    "whom when where why how do does did can could should must may might will would "
    "it its this that these those as from into about after before than then there "
    "their they them i me my we our you your has have had not no any all some much "
    "many more most very just only also if so up out over set use used".split()
)
WHOLE_WORDS = {
    "ten",
    "four",
    "seven",
    "zero",
    "occ",
    "mph",
    "twenty",
    "thirty",
    "sixty",
}
MIN_LOOKUP_SCORE = 3.0  # below this, no reference fact covers the question


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9_-]*", text.lower())
    out = []
    for w in words:
        if w in STOP:
            continue
        if len(w) > 4 and w.endswith("ies"):
            w = w[:-3] + "y"
        elif len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


@lru_cache(maxsize=1)
def load_reference() -> dict:
    return json.loads(REFERENCE_FILE.read_text())


def fact_for_topic(topic: str) -> dict | None:
    return next((f for f in load_reference()["facts"] if f["topic"] == topic), None)


def lookup(question: str, k: int = 2) -> list[dict]:
    """Top-k facts by keyword overlap (keywords count double). [] = not covered."""
    q = set(tokens(question))
    scored = []
    for f in load_reference()["facts"]:
        kw = set(tokens(" ".join(f["keywords"])))
        body = set(tokens(f["title"] + " " + f["fact"]))
        score = 2.0 * len(q & kw) + 1.0 * len(q & (body - kw))
        if score >= MIN_LOOKUP_SCORE:
            scored.append((score, f))
    scored.sort(key=lambda x: -x[0])
    return [dict(f, score=s) for s, f in scored[:k]]


def _pattern(term: str) -> str:
    t = term.strip()
    esc = re.escape(t)
    if re.fullmatch(r"\d+", t):
        return rf"(?<![\d.]){esc}(?!\d)"
    if t.lower() in WHOLE_WORDS:
        return rf"\b{esc}\b"
    return (r"\b" if t[0].isalnum() else "") + esc


def term_present(answer: str, variants: list[str]) -> bool:
    return any(re.search(_pattern(v), answer, flags=re.I) for v in variants)


def missing_terms(answer: str, fact: dict) -> list[list[str]]:
    return [
        group for group in fact["required_terms"] if not term_present(answer, group)
    ]


DECLINE = re.compile(
    r"outside (the|my|of)|not covered|no (reference|information|fact|record)|"
    r"(don't|do not|cannot|can't|can not|unable to) (have|answer|help|provide)|"
    r"not (in|part of) the (transit|reference)|out of scope|only answer|"
    r"not related to (transit|the transit)|beyond (the|my) scope",
    re.I,
)


def declines(answer: str) -> bool:
    return bool(DECLINE.search(answer))
