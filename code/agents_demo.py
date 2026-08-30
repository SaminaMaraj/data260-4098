

import argparse, json, os, re, sys, time
from dataclasses import dataclass
from typing import List, Dict, Any, Iterable, Tuple

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.model_client import complete


# Optional: students can expand/modify this
STOP = {
    "the", "and", "for", "that", "with", "this", "from", "into", "than", "your", "you",
    "are", "was", "were", "have", "has", "had", "use", "used", "using", "about", "how",
    "can", "will", "more", "less", "very", "over", "under", "their", "there", "then",
    "our", "out", "on", "in", "of", "to", "by", "a", "an", "is","at", "during", "it", "as",
}


# -------------------------
# Text cleanup + extraction
# -------------------------

def strip_code_and_md(s: str) -> str:
    """
    TODO: Remove markdown/code artifacts from model output.
    Suggested:
      - remove fenced code blocks
      - remove inline backticks
      - normalize whitespace
    """
    # Placeholder implementation:
    text = str(s)
    text = re.sub(r"```(?:[A-Za-z0-9_+-]+)?", "", text)
    text = text.replace("`", "")
    return " ".join(text.split())


def extract_json_block(text: str) -> str:
    cleaned = strip_code_and_md(text)

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start != -1 and end != -1 and end > start:
        return cleaned[start:end + 1]

    return json.dumps({"message": cleaned})





def tokens(txt: str) -> List[str]:
    """
    TODO: Tokenize into lowercase words (optionally keep hyphens) , filter junk, etc.
    """
    return re.findall(r"[a-z]+(?:-[a-z]+)*", str(txt).lower())


def ngrams(words: List[str], n: int) -> Iterable[Tuple[str, ...]]:
    """
    TODO: Yield word n-grams from a token list.
    """
    for i in range(max(0, len(words) - n + 1)):
        yield tuple(words[i:i + n])


def phrase_candidates(title: str, content: str, maxn: int = 12) -> List[str]:
    """
    TODO: Build tag candidates derived ONLY from title+content.
    Suggested approach:
      - tokenize + remove STOP words
      - gather bigrams/trigrams
      - rank by frequency
      - fall back to unigrams
      - return up to maxn
    """

    title_words = [word for word in tokens(title) if word not in STOP]
    content_words = [word for word in tokens(content) if word not in STOP]

    counts = {}

    for words in (title_words, content_words):
        for n in (3, 2):
            for group in ngrams(words, n):
                phrase = " ".join(group)
                counts[phrase] = counts.get(phrase, 0) + 1

    ranked_phrases = sorted(
        counts,
        key=lambda phrase: (-counts[phrase], phrase)
    )

    all_words = title_words + content_words
    unigram_counts = {}

    for word in all_words:
        unigram_counts[word] = unigram_counts.get(word, 0) + 1

    ranked_words = sorted(
        unigram_counts,
        key=lambda word: (-unigram_counts[word], word)
    )

    candidates = []

    for candidate in ranked_phrases + ranked_words:
        if candidate not in candidates:
            candidates.append(candidate)

        if len(candidates) == maxn:
            break

    return candidates
    

    

# -------------------------
# Output schema coercion
# -------------------------

def coerce_reply(raw_obj: Any, title: str, content: str, strict: bool) -> Dict[str, Any]:
    """
    TODO: Coerce arbitrary model output into the required schema:
      {
        "thought": str,
        "message": str (non-empty, <= 60 words),
        "data": {
          "tags": [str, str, str],        # exactly 3 topical tags
          "summary": str,                # <= 25 words, ends with '.'
          "issues": [str, ...]
        }
      }

    strict=True suggestion:
      - enforce at least two multi-word tags
    """
   
    obj = raw_obj if isinstance(raw_obj, dict) else {}

    data = obj.get("data", {})
    if not isinstance(data, dict):
        data = {}

    candidates = phrase_candidates(title, content)
    source_words = set(tokens(f"{title} {content}"))

    raw_tags = data.get("tags", [])
    if not isinstance(raw_tags, list):
        raw_tags = []

    valid_tags = []

    for tag in raw_tags:
        cleaned_tag = " ".join(tokens(strip_code_and_md(tag)))
        tag_words = cleaned_tag.split()

        if (
            tag_words
            and all(word in source_words for word in tag_words)
            and cleaned_tag not in valid_tags
        ):
            valid_tags.append(cleaned_tag)

    tags = []

    if strict:
        for tag in valid_tags + candidates:
            if len(tag.split()) >= 2 and tag not in tags:
                tags.append(tag)

            if len(tags) == 2:
                break

    for tag in valid_tags + candidates:
        if tag not in tags:
            tags.append(tag)

        if len(tags) == 3:
            break

    tags = tags[:3]

    summary = strip_code_and_md(data.get("summary", ""))

    if not summary:
        summary = strip_code_and_md(content)

    summary = re.sub(r"\.{2,}", ".", summary)
    summary = re.split(r"(?<=[.!?])\s+", summary)[0]
    summary_words = summary.split()[:25]

    if summary_words:
        summary = " ".join(summary_words).rstrip(".,;:!?") + "."
    else:
        summary = "Summary unavailable."

    message = strip_code_and_md(obj.get("message", ""))

    if not message:
        message = "Proposal reviewed; tags and summary prepared."

    message = " ".join(message.split()[:60])

    thought = strip_code_and_md(obj.get("thought", ""))

    raw_issues = data.get("issues", [])
    if not isinstance(raw_issues, list):
        raw_issues = [raw_issues] if raw_issues else []

    issues = [
        strip_code_and_md(issue)
        for issue in raw_issues
        if strip_code_and_md(issue)
    ]

    return {
        "thought": thought,
        "message": message,
        "data": {
            "tags": tags,
            "summary": summary,
            "issues": issues,
        },
    }


def parse_and_coerce(text: str, title: str, content: str, strict: bool) -> Dict[str, Any]:
    """
    TODO:
      - extract_json_block()
      - json.loads()
      - coerce_reply()
      - handle JSON parse failures gracefully
    """
    try:
        obj = json.loads(extract_json_block(text))
    except Exception:
        obj = {"message": strip_code_and_md(text)}
    return coerce_reply(obj, title, content, strict)


# -------------------------
# Agent wrapper
# -------------------------

@dataclass
class SimpleAgent:
    name: str
    system: str
    model_name: str
    base_url: str
    temperature: float

    def respond(
        self,
        conversation: List[Dict[str, str]],
        task: str,
        title: str,
        content: str,
        strict: bool,
    ) -> Dict[str, Any]:
        history_text = "\n".join(
            f'{message["role"]}: {message["content"]}'
            for message in conversation
        ) or "(empty)"

        human_instruction = (
            f"Task:\n{task}\n\n"
            f"Conversation so far:\n{history_text}\n\n"
            "Return ONLY one JSON object. Do not use code fences, "
            "markdown, or explanations outside the JSON. "
            "Use these keys: thought (string), message "
            "(non-empty and no more than 60 words), data.tags "
            "(exactly 3 topical tags), data.summary "
            "(one sentence of no more than 25 words), and "
            "data.issues (array)."
        )

        messages = [
            {
                "role": "system",
                "content": self.system,
            },
            {
                "role": "user",
                "content": human_instruction,
            },
        ]

        result = complete(
            messages,
            model=self.model_name,
            base_url=self.base_url,
            temperature=self.temperature,
            response_format="json",
        )

        return parse_and_coerce(
            result["content"],
            title,
            content,
            strict,
        )


# -------------------------
# CLI entrypoint
# -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="Your Blog Title Here")
    ap.add_argument("--content", default="Your blog post content goes here.")
    ap.add_argument("--email", default="student@example.com")
    ap.add_argument("--model", default=os.environ.get("SMOL_MODEL", "your-ollama-model-tag"))
    ap.add_argument("--base_url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--turns", type=int, default=1)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    

    # Define three agents (Planner -> Reviewer -> Finalizer)
    planner = SimpleAgent(
        name="Planner",
        system="Propose exactly 3 distinct, topical tags (prefer multi-word phrases) and a one-line summary for the blog post.",
        model_name=args.model,
        base_url=args.base_url,
        temperature=args.temperature,
    )
    reviewer = SimpleAgent(
        name="Reviewer",
        system=(
            "Validate: tags topical and not generic; summary ≤ 25 words; no code or markdown. "
            "If issues, list in data.issues; otherwise echo cleaned tags/summary."
        ),
        model_name=args.model,
        base_url=args.base_url,
        temperature=args.temperature,
    )
    finalizer = SimpleAgent(
        name="Finalizer",
        system=(
            "Use reviewer feedback to finalize. Output exactly 3 tags in data.tags and the final summary in data.summary. "
            "Set data.issues to []."
        ),
        model_name=args.model,
        base_url=args.base_url,
        temperature=args.temperature,
            )

    task = (
        f'Given blog title "{args.title}" and content "{args.content}", produce exactly 3 topical tags '
        f'and a one-sentence summary in your own words. Email is {args.email}.'
    )

    transcript: List[Dict[str, str]] = []

    # Planner
    t0 = time.time()
    a = planner.respond(transcript, task, args.title, args.content, args.strict)
    t1 = time.time()
    transcript.append({"role": "Planner", "content": a.get("message", "")})
    print(f"\n--- Planner ({int((t1 - t0) * 1000)} ms) ---\n{json.dumps(a, indent=2)}")

    # Reviewer
    t0 = time.time()
    b = reviewer.respond(transcript, task, args.title, args.content, args.strict)
    t1 = time.time()
    transcript.append({"role": "Reviewer", "content": b.get("message", "")})
    print(f"\n--- Reviewer ({int((t1 - t0) * 1000)} ms) ---\n{json.dumps(b, indent=2)}")

    # Finalizer
    final = finalizer.respond(transcript, task, args.title, args.content, args.strict)
    print(f"\n Finalized Output \n{json.dumps(final, indent=2)}")

    # Publish package
    package = {
        "title": args.title,
        "email": args.email,
        "content": args.content,
        "agents": {"transcript": transcript, "final": final.get("data", {})},
        "submissionDate": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    print(f"\n Publish Package \n{json.dumps(package, indent=2)}")


if __name__ == "__main__":
    main()
