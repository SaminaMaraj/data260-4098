import os
from typing import Any, Dict, List, Optional

from ollama import Client


DEFAULT_MODEL = os.environ.get("SMOL_MODEL", "qwen3:8b")
DEFAULT_BASE_URL = os.environ.get(
    "OLLAMA_URL",
    "http://localhost:11434",
)


def complete(
    messages: List[Dict[str, str]],
    tools: Optional[List[Dict[str, Any]]] = None,
    *,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: Optional[float] = None,
    response_format: Optional[str] = None,
) -> Dict[str, Any]:
    selected_model = model or DEFAULT_MODEL
    selected_base_url = base_url or DEFAULT_BASE_URL

    if temperature is None:
        temperature = float(
            os.environ.get("MODEL_TEMPERATURE", "0.0")
        )

    client = Client(host=selected_base_url)

    request = {
        "model": selected_model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }

    if tools:
        request["tools"] = tools

    if response_format:
        request["format"] = response_format

    response = client.chat(**request)

    input_tokens = int(response.prompt_eval_count or 0)
    output_tokens = int(response.eval_count or 0)

    tool_calls = []

    for tool_call in response.message.tool_calls or []:
        tool_calls.append(tool_call.model_dump())

    return {
        "content": response.message.content or "",
        "tool_calls": tool_calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "model": response.model,
    }