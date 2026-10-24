"""HW7 Part 3 - hard per-run token budget for the agent loop and Reflexion.

Definition (what is counted)
----------------------------
Every model call is charged
    input_bound + output_tokens
and the sum of all charges of one Reflexion run (every attempt AND every
reflection-generation call) may never exceed `limit`.

* input_bound is an UPPER BOUND on the prompt tokens of that call. qwen3 uses a
  byte-level BPE tokenizer, so every token covers at least one UTF-8 byte of
  the rendered prompt. The rendered prompt is the message contents, the tool
  schemas and the chat-template text. We bound it by the length of the JSON
  of messages + tools (ASCII-escaped, so never shorter than the UTF-8 bytes)
  plus a fixed template allowance per call and per message.
* output_tokens is Ollama's eval_count. Before each call the generation limit
  (num_predict) is set to the remaining allowance after the input bound, so
  the model cannot generate past the budget.

If the remaining allowance after the input bound is smaller than MIN_OUTPUT,
the call is NOT made and the run stops with stop_reason="budget_exhausted".

Because input_bound >= the real prompt tokens and output <= num_predict, the
real Ollama token count of a run is always <= the charged total <= limit. The
bound is loose (about 4-5x the real prompt tokens for JSON-heavy prompts), so
`limit` is expressed in these bounded tokens.
"""

from __future__ import annotations

import json
import os
from typing import Any

TEMPLATE_OVERHEAD = 1024  # chat-template text around system prompt and tools
PER_MESSAGE_OVERHEAD = 64  # <|im_start|>role ... <|im_end|> and tool wrappers
MIN_OUTPUT = 64  # do not start a call that could generate fewer tokens than this


def input_bound(messages: list[dict[str, Any]], tools: list[dict] | None) -> int:
    body = json.dumps(messages, ensure_ascii=True, default=str)
    schema = json.dumps(tools or [], ensure_ascii=True)
    return (
        len(body)
        + len(schema)
        + TEMPLATE_OVERHEAD
        + PER_MESSAGE_OVERHEAD * len(messages)
    )


class TokenBudget:
    """Shared by all model calls of one run. Never lets `charged` exceed `limit`."""

    def __init__(self, limit: int, max_output: int | None = None):
        self.limit = int(limit)
        self.max_output = int(max_output or os.environ.get("MODEL_MAX_TOKENS", "256"))
        self.charged = 0  # bounded tokens (the hard budget)
        self.reported = 0  # tokens Ollama reported (prompt_eval_count + eval_count)
        self.calls: list[dict[str, Any]] = []

    @property
    def remaining(self) -> int:
        return self.limit - self.charged

    def reserve(
        self, messages: list[dict[str, Any]], tools: list[dict] | None
    ) -> tuple[int | None, int]:
        """Return (max_tokens for this call, input_bound). None = cannot afford."""
        bound = input_bound(messages, tools)
        cap = min(self.max_output, self.remaining - bound)
        if cap < MIN_OUTPUT:
            return None, bound
        return cap, bound

    def charge(self, bound: int, cap: int, response: dict[str, Any], kind: str) -> bool:
        """Record one finished call. Returns False if the model broke its cap."""
        reported = int(response.get("total_tokens", 0))
        output = response.get("output_tokens")
        output = int(output) if output is not None else reported  # conservative
        within_cap = output <= cap
        self.charged += bound + min(output, cap)
        self.reported += reported
        self.calls.append(
            {
                "kind": kind,
                "input_bound": bound,
                "max_tokens": cap,
                "output_tokens": output,
                "reported_tokens": reported,
                "charged_total": self.charged,
                "within_cap": within_cap,
            }
        )
        return within_cap

    def summary(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "charged": self.charged,
            "reported_tokens": self.reported,
            "model_calls": len(self.calls),
            "never_exceeded": self.charged <= self.limit
            and all(c["within_cap"] for c in self.calls),
        }
