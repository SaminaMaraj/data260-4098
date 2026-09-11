import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Annotated, Any, Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, StringConstraints, ValidationError, field_validator


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.model_client import complete


Tag = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=30),
]


class PlannerProposal(BaseModel):
    tags: List[Tag] = Field(min_length=3, max_length=3)
    summary: str

    @field_validator("tags")
    @classmethod
    def tags_must_be_distinct(cls, value: List[str]) -> List[str]:
        normalized = [tag.casefold() for tag in value]
        if len(set(normalized)) != 3:
            raise ValueError("The three tags must be distinct.")
        return value

    @field_validator("summary")
    @classmethod
    def summary_must_be_short(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Summary must not be empty.")
        if len(cleaned.split()) > 25:
            raise ValueError("Summary must contain at most 25 words.")
        return cleaned


class ReviewerFeedback(BaseModel):
    approved: bool
    issues: List[str] = Field(default_factory=list)


class AgentState(TypedDict):
    title: str
    content: str
    email: str
    strict: bool
    task: str
    llm: Any
    planner_proposal: Dict[str, Any]
    reviewer_feedback: Dict[str, Any]
    validation_error: str
    turn_count: int
    max_turns: int
    status: str
    force_review_issue: bool
    event_log: List[Dict[str, Any]]


def parse_json_object(text: str) -> Dict[str, Any]:
    cleaned = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.replace("```", "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("The model did not return a JSON object.")
    value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("The model response must be one JSON object.")
    return value


def planner_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: Planner ---")
    previous_issues = state.get("reviewer_feedback", {}).get("issues", [])
    previous_error = state.get("validation_error", "")

    messages = [
        {
            "role": "system",
            "content": (
                "You are the Planner for a municipal transit incident system. "
                "Return only JSON with keys tags and summary. tags must contain "
                "exactly three distinct topical strings, each 3 to 30 characters. "
                "summary must contain no more than 25 words."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "task": state["task"],
                    "title": state["title"],
                    "content": state["content"],
                    "previous_reviewer_issues": previous_issues,
                    "previous_validation_error": previous_error,
                }
            ),
        },
    ]

    result = complete(
        messages,
        model=state["llm"]["model"],
        base_url=state["llm"]["base_url"],
        temperature=state["llm"]["temperature"],
        response_format="json",
    )

    log = list(state.get("event_log", []))
    try:
        parsed = parse_json_object(result["content"])
        proposal = PlannerProposal.model_validate(parsed).model_dump()
        validation_error = ""
        log.append(
            {
                "node": "planner",
                "valid": True,
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
            }
        )
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        proposal = {}
        validation_error = str(exc)
        log.append(
            {
                "node": "planner",
                "valid": False,
                "error": validation_error,
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
            }
        )

    return {
        "planner_proposal": proposal,
        "reviewer_feedback": {},
        "validation_error": validation_error,
        "event_log": log,
    }


def reviewer_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: Reviewer ---")
    log = list(state.get("event_log", []))

    if state.get("validation_error"):
        feedback = {
            "approved": False,
            "issues": [state["validation_error"]],
        }
        log.append({"node": "reviewer", "approved": False, "reason": "schema"})
        return {"reviewer_feedback": feedback, "event_log": log}

    if state.get("force_review_issue", False):
        feedback = {
            "approved": False,
            "issues": ["Forced reviewer issue used to demonstrate the correction loop."],
        }
        log.append({"node": "reviewer", "approved": False, "reason": "forced"})
        return {"reviewer_feedback": feedback, "event_log": log}

    messages = [
        {
            "role": "system",
            "content": (
                "You are the Reviewer. Check whether the tags and summary are "
                "topical, clear, and supported by the transit incident. Return only "
                "JSON with approved (boolean) and issues (array of strings)."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "title": state["title"],
                    "content": state["content"],
                    "proposal": state["planner_proposal"],
                }
            ),
        },
    ]

    result = complete(
        messages,
        model=state["llm"]["model"],
        base_url=state["llm"]["base_url"],
        temperature=state["llm"]["temperature"],
        response_format="json",
    )

    try:
        parsed = parse_json_object(result["content"])
        checked = ReviewerFeedback.model_validate(parsed)
        feedback = checked.model_dump()
        if feedback["issues"]:
            feedback["approved"] = False
    except (ValueError, json.JSONDecodeError, ValidationError) as exc:
        feedback = {
            "approved": False,
            "issues": [f"Reviewer response could not be validated: {exc}"],
        }

    log.append(
        {
            "node": "reviewer",
            "approved": feedback["approved"],
            "input_tokens": result["input_tokens"],
            "output_tokens": result["output_tokens"],
        }
    )
    return {"reviewer_feedback": feedback, "event_log": log}


def supervisor_node(state: AgentState) -> Dict[str, Any]:
    print("--- NODE: Supervisor ---")
    new_turn_count = state.get("turn_count", 0) + 1
    approved = state.get("reviewer_feedback", {}).get("approved", False)

    if approved:
        status = "completed"
    elif new_turn_count >= state["max_turns"]:
        status = "abandoned_at_ceiling"
    else:
        status = "retrying"

    log = list(state.get("event_log", []))
    log.append(
        {
            "node": "supervisor",
            "turn_count": new_turn_count,
            "status": status,
        }
    )
    return {
        "turn_count": new_turn_count,
        "status": status,
        "event_log": log,
    }


def router_logic(state: AgentState) -> str:
    if state["status"] in {"completed", "abandoned_at_ceiling"}:
        return "end"
    return "planner"


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("planner", planner_node)
    builder.add_node("reviewer", reviewer_node)
    builder.add_node("supervisor", supervisor_node)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "reviewer")
    builder.add_edge("reviewer", "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        router_logic,
        {"planner": "planner", "end": END},
    )
    return builder.compile()


def run_graph(args: argparse.Namespace) -> Dict[str, Any]:
    graph = build_graph()
    initial_state: AgentState = {
        "title": args.title,
        "content": args.content,
        "email": args.email,
        "strict": args.strict,
        "task": "Create three topical tags and a short summary for this incident.",
        "llm": {
            "model": args.model,
            "base_url": args.base_url,
            "temperature": args.temperature,
        },
        "planner_proposal": {},
        "reviewer_feedback": {},
        "validation_error": "",
        "turn_count": 0,
        "max_turns": args.max_turns,
        "status": "running",
        "force_review_issue": args.force_review_issue,
        "event_log": [],
    }

    final_state: Dict[str, Any] = dict(initial_state)
    recursion_limit = (args.max_turns * 3) + 5

    for event in graph.stream(
        initial_state,
        {"recursion_limit": recursion_limit},
        stream_mode="updates",
    ):
        for node_name, updates in event.items():
            final_state.update(updates)
            print(f"\n--- STREAM UPDATE: {node_name} ---")
            print(json.dumps(updates, indent=2, default=str))

    print("\n--- FINAL GRAPH RESULT ---")
    print(
        json.dumps(
            {
                "status": final_state["status"],
                "turn_count": final_state["turn_count"],
                "planner_proposal": final_state["planner_proposal"],
                "reviewer_feedback": final_state["reviewer_feedback"],
            },
            indent=2,
        )
    )
    return final_state


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--content", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--model", default=os.environ.get("SMOL_MODEL", "qwen3:8b"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-turns", type=int, default=10)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--force-review-issue", action="store_true")
    args = parser.parse_args()

    if args.max_turns < 1:
        parser.error("--max-turns must be at least 1")

    run_graph(args)


if __name__ == "__main__":
    main()
