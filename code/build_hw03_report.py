"""Build the DATA 260 HW3 report PDF from the recorded raw outputs."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = ROOT / "reports" / "hw03"
RAW_DIR = REPORT_DIR / "raw"
OUTPUT = REPORT_DIR / "report.pdf"


def footer(canvas, document):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#667085"))
    canvas.drawString(0.7 * inch, 0.45 * inch, "DATA 260 - HW3 - Samina Maraj")
    canvas.drawRightString(7.8 * inch, 0.45 * inch, f"Page {document.page}")
    canvas.restoreState()


def p(text, style):
    return Paragraph(text, style)


def build():
    summaries = json.loads((RAW_DIR / "retrieval_summaries.json").read_text())[
        "summaries"
    ]
    by_method = {}
    for row in summaries:
        by_method.setdefault(row["technique"], []).append(row)

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=22,
            leading=27,
            textColor=colors.HexColor("#123B5D"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Subtitle",
            parent=styles["Normal"],
            alignment=TA_CENTER,
            fontSize=11,
            textColor=colors.HexColor("#475467"),
            spaceAfter=20,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#123B5D"),
            spaceBefore=10,
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Small",
            parent=styles["BodyText"],
            fontSize=8.5,
            leading=11,
        )
    )
    styles["BodyText"].fontSize = 10
    styles["BodyText"].leading = 14

    story = [
        Spacer(1, 0.5 * inch),
        p("DATA 260 Homework 3", styles["ReportTitle"]),
        p("Authentication and LlamaIndex retrieval comparison", styles["Subtitle"]),
        p("Student: Samina Maraj | Repository: data260-4098 | SID4: 4098", styles["Normal"]),
        Spacer(1, 0.22 * inch),
        p(
            "This project extends a municipal transit incident application with authenticated web sessions and evaluates three retrieval chunking strategies over a public transit safety and security corpus.",
            styles["BodyText"],
        ),
        Spacer(1, 0.12 * inch),
        p("Executive summary", styles["Section"]),
        p(
            "The authentication verification passed all required checks. The retrieval experiment used five fixed questions, the all-MiniLM-L6-v2 embedding model, in-memory LlamaIndex vector indexes, and top-5 retrieval. Token chunking had the strongest average retrieval scores and perfect recall in this run. Semantic chunking was fastest and produced the fewest chunks. Sentence-window chunking performed well for overview questions but missed one expected keyword at top-5.",
            styles["BodyText"],
        ),
        PageBreak(),
        p("1. Authentication implementation", styles["Section"]),
        p(
            "The FastAPI application provides public home, login, and incident pages, plus a protected dashboard and logout route. Starlette SessionMiddleware stores the authenticated session. The implementation uses secure, HTTP-only, SameSite=Lax cookies, a fifteen-minute idle timeout, invalid-login handling, and redirect behavior for unauthenticated dashboard access.",
            styles["BodyText"],
        ),
        Spacer(1, 0.1 * inch),
        p("Verification results", styles["Section"]),
    ]
    auth_rows = [
        ["Check", "Result"],
        ["Required files", "PASS - 5 present"],
        ["Public home, login, incidents", "PASS - HTTP 200"],
        ["Protected dashboard before login", "PASS - HTTP 303"],
        ["Invalid login", "PASS - HTTP 401"],
        ["Successful login and dashboard", "PASS - HTTP 303 then 200"],
        ["Cookie flags", "PASS - secure, httponly, samesite=lax"],
        ["Logout and expired session", "PASS - HTTP 303"],
    ]
    story.append(Table(auth_rows, colWidths=[3.3 * inch, 3.5 * inch], repeatRows=1, style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123B5D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F4F7")]),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 6),
    ])))
    story.extend([
        Spacer(1, 0.12 * inch),
        p("Browser evidence is stored in reports/hw03/raw/: home.png, login_invalid.png, dashboard.png, and protected_dashboard_redirect.png.", styles["BodyText"]),
        p("2. Corpus and retrieval method", styles["Section"]),
        p(
            "The corpus contains 254,170 bytes from two public Federal Transit Administration sources: the FRA Regulated Mode Major Security Events dataset and the FTA NTD safety and security overview. The corpus manifest records source URLs, access date, byte sizes, and SHA-256 hashes. The corpus exceeds the 200 KB minimum requirement.",
            styles["BodyText"],
        ),
        p(
            "Five questions were written to questions.yaml before retrieval. Each question was embedded with all-MiniLM-L6-v2, which produces 384-dimensional vectors. Three in-memory vector indexes were built using TokenTextSplitter, SemanticSplitterNodeParser, and SentenceWindowNodeParser. For every question and method, the system saved the top five retrieved chunks, similarity scores, cosine checks, chunk lengths, previews, source files, and latency.",
            styles["BodyText"],
        ),
        PageBreak(),
        p("3. Results", styles["Section"]),
    ])
    metric_rows = [["Technique", "Chunks", "Avg length", "Top-1", "Mean@5", "Recall@5", "Latency ms"]]
    order = ["Token", "Semantic", "Sentence-window"]
    for method in order:
        rows = by_method[method]
        metric_rows.append([
            method,
            str(rows[0]["chunk_count"]),
            f"{rows[0]['avg_chunk_length']:.2f}",
            f"{mean(r['top1_cosine'] for r in rows):.4f}",
            f"{mean(r['mean_at_k_cosine'] for r in rows):.4f}",
            f"{sum(r['recall_at_k'] for r in rows)}/5",
            f"{mean(r['retrieval_latency_ms'] for r in rows):.2f}",
        ])
    story.append(Table(metric_rows, colWidths=[1.22 * inch, 0.65 * inch, 0.85 * inch, 0.7 * inch, 0.7 * inch, 0.7 * inch, 0.75 * inch], repeatRows=1, style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#123B5D")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D5DD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F4F7")]),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ])))
    story.extend([
        Spacer(1, 0.15 * inch),
        p("Interpretation", styles["Section"]),
        p(
            "Token chunking was the strongest overall choice for this small corpus: it had the highest mean top-1 cosine and mean cosine@5, while recalling the expected source and keyword for all five questions. Its chunks were moderate in size, which gave the retriever enough context without combining too much unrelated material.",
            styles["BodyText"],
        ),
        p(
            "Semantic chunking created only 32 large chunks and had the lowest mean latency. Its large average chunk length may explain why the similarity scores were lower: a retrieved chunk can contain much more text than the specific answer requires. Sentence-window chunking created the most, shortest chunks and was strongest for questions about the overview page, especially the update schedule question.",
            styles["BodyText"],
        ),
        p("4. Misleading retrieval analysis", styles["Section"]),
        p(
            "Three top-ranked results were flagged because the highest-scoring chunk did not contain an expected answer keyword. These are useful error cases rather than evidence that the entire system failed. They show that a high vector similarity score can indicate related language without guaranteeing that the passage directly answers the question. A production system should combine retrieval scores with answer verification, source checks, or reranking.",
            styles["BodyText"],
        ),
        PageBreak(),
        p("5. Conclusion and reproducibility", styles["Section"]),
        p(
            "The HW3 implementation meets the authentication and retrieval comparison goals. The authentication layer protects the dashboard while keeping the incident page public. The retrieval experiment is reproducible from the fixed questions, local corpus, manifest, model name, chunker settings, and raw JSON outputs. For this corpus and question set, TokenTextSplitter is the recommended default because it achieved the best balance of retrieval quality and complete recall. The result should not be generalized to every corpus; larger experiments could change the comparison.",
            styles["BodyText"],
        ),
        p("Tracked artifacts", styles["Section"]),
        p(
            "reports/hw03 contains RUN_LOG.txt, METRICS.md, SOURCES.md, questions.yaml, CORPUS_MANIFEST.json, report.pdf, the corpus files, authentication screenshots, retrieval_summaries.json, retrieval_outputs.jsonl, and misleading_candidates.json. The verification record is stored in verification.json.",
            styles["BodyText"],
        ),
        Spacer(1, 0.16 * inch),
        p("Sources", styles["Section"]),
        p("Federal Transit Administration dataset: https://data.transportation.gov/d/65fa-qbkf", styles["Small"]),
        p("FTA NTD safety and security overview: https://www.transit.dot.gov/ntd/accessing-national-transit-database-ntd-safety-and-security-event-data", styles["Small"]),
    ])

    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.7 * inch,
        title="DATA 260 HW3 Report",
        author="Samina Maraj",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(OUTPUT)


if __name__ == "__main__":
    build()
