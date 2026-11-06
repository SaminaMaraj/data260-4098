"""Grounding facts from s4098_rel for the Q&A endpoint, and the data-version marker.

parse_dependencies(question) finds the records a question is about (routes,
an incident category, an incident code). load_facts(deps) reads exactly those
records from s4098_rel. data_version(facts) is a short hash of those facts.

The cache stores (deps, data_version) with every answer. On a later hit the
same deps are read again; if the hash differs, the underlying records
changed after the answer was produced, so the cached answer is stale.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.engine import Engine

CATEGORY_PATTERNS = {
    "delay": r"\bdelay(s|ed)?\b|\blate\b",
    "collision": r"\bcollisions?\b|\bcrash(es)?\b|\baccidents?\b",
    "service-suspension": r"service[- ]suspensions?|\bsuspen(ded|sions?)\b",
    "infrastructure-issue": r"\binfrastructure\b",
}
COUNT_WORDS = (
    r"how many|number of|\bcount\b|\bincidents?\b|\bmost\b|\bfewest\b|\btotal\b"
)
INCIDENT_CODE = r"\bINC-\d{6}\b"


@dataclass
class Grounding:
    deps: dict
    facts: dict
    data_version: str
    lines: list[str] = field(default_factory=list)

    def as_prompt(self) -> str:
        if not self.lines:
            return "No record in the s4098_rel database matches this question."
        return "\n".join(f"- {line}" for line in self.lines)


def data_version(facts: dict) -> str:
    blob = json.dumps(facts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


class FactStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        self._routes: list[dict] | None = None

    def routes(self) -> list[dict]:
        if self._routes is None:
            with self.engine.connect() as conn:
                rows = (
                    conn.execute(text("SELECT id, route_name, route_code FROM routes"))
                    .mappings()
                    .all()
                )
            self._routes = [dict(r) for r in rows]
        return self._routes

    # ------------------------------------------------------------------ parse
    def parse_dependencies(self, question: str) -> dict:
        q = question.lower()
        found = []
        for route in sorted(self.routes(), key=lambda r: -len(r["route_name"])):
            name = route["route_name"].lower()
            short = re.sub(r"^vta\s+", "", name)
            patterns = [re.escape(name), re.escape(route["route_code"].lower())]
            if short != name:
                patterns.append(r"\b" + re.escape(short) + r"\b")
            if any(re.search(p, q) for p in patterns):
                if route["route_code"] not in found:
                    found.append(route["route_code"])
        category = next(
            (c for c, p in CATEGORY_PATTERNS.items() if re.search(p, q)), None
        )
        code = re.search(INCIDENT_CODE, question.upper())
        return {
            "routes": sorted(found),
            "category": category,
            "incident": code.group(0) if code else None,
            "counts": bool(re.search(COUNT_WORDS, q)),
        }

    # ------------------------------------------------------------------- load
    def load_facts(self, deps: dict) -> Grounding:
        facts: dict = {}
        lines: list[str] = []
        with self.engine.connect() as conn:
            for code in deps.get("routes", []):
                r = (
                    conn.execute(
                        text(
                            "SELECT id, route_code, route_name, operator FROM routes "
                            "WHERE route_code = :c"
                        ),
                        {"c": code},
                    )
                    .mappings()
                    .first()
                )
                if r is None:
                    continue
                item = {"route_name": r["route_name"], "operator": r["operator"]}
                line = (
                    f"Route {r['route_code']} is '{r['route_name']}', "
                    f"operated by {r['operator']}."
                )
                if deps.get("counts"):
                    rows = (
                        conn.execute(
                            text(
                                "SELECT category, COUNT(*) AS n FROM incidents "
                                "WHERE route_id = :rid GROUP BY category"
                            ),
                            {"rid": r["id"]},
                        )
                        .mappings()
                        .all()
                    )
                    by_cat = {row["category"]: int(row["n"]) for row in rows}
                    cat = deps.get("category")
                    if cat:
                        item[f"{cat}_incidents"] = by_cat.get(cat, 0)
                        line += (
                            f" It has {by_cat.get(cat, 0)} recorded {cat} incidents."
                        )
                    else:
                        item["total_incidents"] = sum(by_cat.values())
                        item["incidents_by_category"] = by_cat
                        parts = ", ".join(
                            f"{k}: {v}" for k, v in sorted(by_cat.items())
                        )
                        line += (
                            f" It has {sum(by_cat.values())} recorded incidents "
                            f"({parts})."
                        )
                facts[f"route:{code}"] = item
                lines.append(line)

            if deps.get("category") and not deps.get("routes") and deps.get("counts"):
                cat = deps["category"]
                rows = (
                    conn.execute(
                        text(
                            "SELECT r.route_name, COUNT(*) AS n FROM incidents i "
                            "JOIN routes r ON r.id = i.route_id WHERE i.category = :c "
                            "GROUP BY r.route_name"
                        ),
                        {"c": cat},
                    )
                    .mappings()
                    .all()
                )
                per_route = {row["route_name"]: int(row["n"]) for row in rows}
                facts[f"category:{cat}"] = per_route
                parts = ", ".join(f"{k}: {v}" for k, v in sorted(per_route.items()))
                lines.append(
                    f"{cat} incidents per route: {parts} "
                    f"(total {sum(per_route.values())})."
                )

            if deps.get("incident"):
                i = (
                    conn.execute(
                        text(
                            "SELECT incident_code, incident_title, route_line, category, "
                            "passengers_affected, submission_date FROM incidents "
                            "WHERE incident_code = :c"
                        ),
                        {"c": deps["incident"]},
                    )
                    .mappings()
                    .first()
                )
                if i is not None:
                    item = {k: str(v) for k, v in dict(i).items()}
                    facts[f"incident:{deps['incident']}"] = item
                    lines.append(
                        f"Incident {i['incident_code']}: '{i['incident_title']}' on "
                        f"{i['route_line']}, category {i['category']}, "
                        f"{i['passengers_affected']} passengers affected, submitted "
                        f"{str(i['submission_date'])[:10]}."
                    )
        return Grounding(
            deps=deps, facts=facts, data_version=data_version(facts), lines=lines
        )

    def ground(self, question: str) -> Grounding:
        return self.load_facts(self.parse_dependencies(question))
