"""HW7 Part 4 UI + API: http://localhost:8498/hw7/bikeshare"""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .hw7_bikeshare_agent import DEFAULT_PRICING_URL, run_bikeshare_agent
from .hw7_runlog import header, log

REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE = Path(__file__).resolve().parent / "hw7_static" / "bikeshare.html"
RAW_DIR = REPO_ROOT / "reports" / "hw07" / "raw" / "bikeshare"
FIXTURE_DIR = REPO_ROOT / "reports" / "hw07" / "fixtures"
MAX_UPLOAD_BYTES = 30 * 1024 * 1024

router = APIRouter(prefix="/hw7", tags=["HW7 bike-share agent"])


@router.get("/bikeshare", include_in_schema=False)
def bikeshare_page() -> FileResponse:
    return FileResponse(PAGE)


@router.get("/fixtures/{name}", include_in_schema=False)
def fixture(name: str) -> FileResponse:
    """Serve local verification fixtures (e.g. the hostile pricing page)."""
    if not re.fullmatch(r"[A-Za-z0-9_\-]+\.(html|txt)", name):
        raise HTTPException(status_code=404, detail="Not found")
    path = FIXTURE_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path)


@router.post("/bikeshare/run")
def run(
    trips: UploadFile = File(...),
    pricing_url: str = Form(DEFAULT_PRICING_URL),
    label: str = Form("run"),
    prompt_defense: bool = Form(True),
    tool_defense: bool = Form(True),
) -> dict:
    data = trips.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="CSV larger than 30 MB")
    if not data.strip():
        raise HTTPException(status_code=422, detail="Uploaded CSV is empty")
    safe_label = re.sub(r"[^A-Za-z0-9_\-]", "_", label)[:60] or "run"
    out_dir = RAW_DIR / safe_label
    header(f"HW7 Part 4 UI run '{safe_label}' on {trips.filename} ({pricing_url})")
    result = run_bikeshare_agent(
        data,
        pricing_url.strip(),
        snapshot_dir=out_dir,
        prompt_defense=prompt_defense,
        tool_defense=tool_defense,
    )
    result["label"] = safe_label
    result["uploaded_filename"] = trips.filename
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "run.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    metrics, final = result["metrics"], result["final"]
    for step in result["timeline"]:
        if step["type"] == "tool_call":
            log(f"  CALL {step['tool']} {json.dumps(step['input'])[:240]}")
    log(
        f"  decision={result['decision']} "
        f"pay_per_use={final.get('pay_per_use_total')} "
        f"membership={final.get('membership_total')} "
        f"steps={metrics['step_count']} time_ms={metrics['total_time_ms']} "
        f"stop={metrics['stop_reason']}"
    )
    for cite in result["citations"]:
        log(f"  citation {cite['url']} {cite['captured_at']} sha256={cite['sha256']}")
    return result
