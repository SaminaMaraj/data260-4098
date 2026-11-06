"""Offline HW9 tests (no Redis Stack, no Ollama, no MySQL needed).

    python tests/test_hw09.py

Uses a temporary SQLite copy of the s4098_rel schema, a tiny fake Redis for the
counter, the in-memory vector backend, the stub embedder and the stub LLM.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["HW9_EMBEDDER"] = "stub"

import yaml  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from src.hw9_agents.agents import EvaluatorAgent  # noqa: E402
from src.hw9_agents.reference import DATA_DIR, lookup  # noqa: E402
from src.hw9_agents.system import gate  # noqa: E402
from src.hw9_cache.agent_path import AgentPath  # noqa: E402
from src.hw9_cache.embeddings import Embedder  # noqa: E402
from src.hw9_cache.facts import FactStore  # noqa: E402
from src.hw9_cache.qa import CachedQA  # noqa: E402
from src.hw9_cache.semantic_cache import MemoryBackend, SemanticCache  # noqa: E402
from src.hw9_cache.views import IncidentStoreWithCache  # noqa: E402


class FakeRedis:
    def __init__(self):
        self.d = {}

    def incr(self, k):
        self.d[k] = int(self.d.get(k, 0)) + 1
        return self.d[k]

    def get(self, k):
        return self.d.get(k)

    def delete(self, *ks):
        for k in ks:
            self.d.pop(k, None)


def make_db():
    path = Path(tempfile.mkdtemp()) / "rel.db"
    eng = create_engine(f"sqlite+pysqlite:///{path}")
    with eng.begin() as c:
        c.execute(
            text(
                "CREATE TABLE routes (id INTEGER PRIMARY KEY, route_name TEXT, "
                "operator TEXT, route_code TEXT)"
            )
        )
        c.execute(
            text(
                "CREATE TABLE incidents (id INTEGER PRIMARY KEY, incident_code TEXT, "
                "incident_title TEXT, route_line TEXT, category TEXT, "
                "passengers_affected INT, submission_date TEXT, route_id INT, "
                "view_count INT NOT NULL DEFAULT 0)"
            )
        )
        names = ["VTA Route 22", "VTA Green Line", "VTA Route 522"]
        for i, n in enumerate(names, 1):
            c.execute(
                text("INSERT INTO routes VALUES (:i, :n, 'VTA', :c)"),
                {"i": i, "n": n, "c": f"RT-{i:03d}"},
            )
        cats = ["delay", "collision", "delay", "service-suspension"]
        for i in range(1, 41):
            c.execute(
                text(
                    "INSERT INTO incidents (id, incident_code, incident_title, "
                    "route_line, category, passengers_affected, submission_date, "
                    "route_id) VALUES (:i, :code, :t, :r, :cat, 0, '2026-01-01', :rid)"
                ),
                {
                    "i": i,
                    "code": f"INC-{i:06d}",
                    "t": f"Incident {i}",
                    "r": names[i % 3],
                    "cat": cats[i % 4],
                    "rid": i % 3 + 1,
                },
            )
    return eng


def test_view_counter_syncs_every_10():
    eng = make_db()
    store = IncidentStoreWithCache(eng, FakeRedis(), verbose=False)
    totals = [store.increment_incident_views(7) for _ in range(25)]
    assert totals == list(range(1, 26))
    assert store.db_writes == 2 and store.last_synced == 20
    assert store.db_view_count(7) == 20


def qa_for(eng, threshold=0.85):
    return CachedQA(
        SemanticCache(MemoryBackend(), threshold),
        FactStore(eng),
        AgentPath("inproc", "stub"),
        Embedder("stub"),
        verbose=False,
    )


def test_semantic_cache_hit_and_miss():
    qa = qa_for(make_db())
    q = "Who operates VTA Route 522?"
    first = qa.ask(q)
    assert first["is_cached"] is False and first["deps"]["routes"] == ["RT-003"]
    again = qa.ask(q)
    assert again["is_cached"] is True and again["similarity"] >= 0.99
    assert again["answer"] == first["answer"]
    other = qa.ask("How do I bake sourdough bread at home?")
    assert other["is_cached"] is False


def test_version_invalidation():
    eng = make_db()
    qa = qa_for(eng)
    q = "Who operates VTA Route 522?"
    stored = qa.ask(q)
    with eng.begin() as c:
        c.execute(text("UPDATE routes SET operator='MV' WHERE route_code='RT-003'"))
    qa.invalidation = "none"
    stale = qa.ask(q)
    assert stale["is_cached"] and stale["data_version"] == stored["data_version"]
    qa.invalidation = "version"
    fresh = qa.ask(q)
    assert fresh["invalidated"] and not fresh["is_cached"]
    assert fresh["data_version"] != stored["data_version"]
    assert qa.ask(q)["is_cached"]


def test_cache_cases_file():
    data = yaml.safe_load((ROOT / "reports/hw09/cases/cache_cases.yaml").read_text())
    seeds = {s["id"] for s in data["seeds"]}
    groups = {}
    for c in data["cases"]:
        groups[c["group"]] = groups.get(c["group"], 0) + 1
        should_hit = c["group"] in ("exact", "paraphrase")
        assert c["expected"] == ("hit" if should_hit else "miss")
        assert c["target"] is None or c["target"] in seeds
    assert len(seeds) == 10 and len(data["cases"]) == 40
    assert set(groups.values()) == {10}
    exact = [c for c in data["cases"] if c["group"] == "exact"]
    by_id = {s["id"]: s["query"] for s in data["seeds"]}
    assert all(c["query"] == by_id[c["target"]] for c in exact)


def test_datasets_have_no_answers_and_lookup_works():
    seen = set()
    for name in ("training_data.json", "validation_data.json", "test_data.json"):
        items = json.loads((DATA_DIR / name).read_text())["items"]
        for it in items:
            assert set(it) == {"id", "question", "topic"}
            assert it["question"] not in seen
            seen.add(it["question"])
            top = lookup(it["question"])
            if it["topic"] == "out_of_scope":
                assert top == [], it
            else:
                assert top and top[0]["topic"] == it["topic"], it


def test_evaluator_rule_and_masking():
    ev = EvaluatorAgent("stub")
    bad = ev.evaluate("q", "bus_bridge", "When the suspension is long.")
    assert bad["result"] == "REVISE" and bad["failure_type"] == "missing_value"
    good = ev.evaluate("q", "bus_bridge", "If it will last more than 20 minutes.")
    assert good["result"] == "PASS"
    assert "[value]" in ev._mask("use 20 minutes", {"required_terms": [["20"]]})
    oos = ev.evaluate("q", "out_of_scope", "Canberra.")
    assert oos["failure_type"] == "unsupported_answer"
    ok = ev.evaluate("q", "out_of_scope", "That is outside the transit reference.")
    assert ok["result"] == "PASS"


def test_gate_rejects_regression():
    def row(i, first, final, topic="x"):
        return {"id": i, "first_result": first, "final_result": final, "topic": topic}

    before = [row("a", "PASS", "PASS"), row("b", "REVISE", "PASS")]
    good = [row("a", "PASS", "PASS"), row("b", "PASS", "PASS")]
    bad = [row("a", "REVISE", "PASS"), row("b", "PASS", "PASS")]
    assert gate(before, good)["keep"] is True
    assert gate(before, bad)["keep"] is False


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"{len(tests)}/{len(tests)} passed")
