from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


PORT_BASE = 8498

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "code" / "web_application"

app = FastAPI(title="Municipal Transit Incident API")

app.mount(
    "/static",
    StaticFiles(directory=WEB_DIR),
    name="static",
)


class Incident(BaseModel):
    id: int
    incidentTitle: str
    routeLine: str
    submitterEmail: str
    description: str
    category: str
    termsAccepted: bool
    submissionDate: str


INCIDENTS: list[Incident] = [
    Incident(
        id=1,
        incidentTitle="Bus Delay at Santa Clara Station",
        routeLine="VTA Route 22",
        submitterEmail="kazisaminamaraj.mumu@sjsu.edu",
        description="The bus arrived thirty minutes late during the afternoon commute.",
        category="delay",
        termsAccepted=True,
        submissionDate=datetime.now(timezone.utc).isoformat(),
    ),
    Incident(
        id=2,
        incidentTitle="Light Rail Service Interruption",
        routeLine="VTA Green Line",
        submitterEmail="kazisaminamaraj.mumu@sjsu.edu",
        description="Light rail service was interrupted because of a track maintenance issue.",
        category="service-suspension",
        termsAccepted=True,
        submissionDate=datetime.now(timezone.utc).isoformat(),
    ),
]

next_id = 3


def home_redirect(error: str | None = None) -> RedirectResponse:
    url = "/"

    if error:
        url = f"/?error={quote(error)}"

    return RedirectResponse(url=url, status_code=303)


@app.get("/", response_class=FileResponse)
async def home() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "port": PORT_BASE,
        "record_count": len(INCIDENTS),
    }


@app.get("/api/incidents", response_model=list[Incident])
async def list_incidents(
    q: str = Query(default="", max_length=100),
    simulate_error: bool = False,
) -> list[Incident]:
    if simulate_error:
        raise HTTPException(
            status_code=503,
            detail="Demonstration error: incident records could not be loaded.",
        )

    search_text = q.strip().casefold()

    if not search_text:
        return INCIDENTS

    return [
        incident
        for incident in INCIDENTS
        if search_text in incident.incidentTitle.casefold()
        or search_text in incident.routeLine.casefold()
    ]


@app.post("/incidents")
async def create_incident(
    incidentTitle: str = Form(..., min_length=3, max_length=100),
    routeLine: str = Form(..., min_length=2, max_length=100),
    submitterEmail: str = Form(..., min_length=5, max_length=150),
    description: str = Form(..., min_length=26, max_length=1000),
    category: str = Form(...),
    termsAccepted: bool = Form(False),
) -> RedirectResponse:
    global next_id

    valid_categories = {
        "delay",
        "collision",
        "service-suspension",
        "infrastructure-issue",
    }

    if category not in valid_categories:
        return home_redirect("Please select a valid incident category.")

    if not termsAccepted:
        return home_redirect("You must accept the terms and conditions.")

    incident = Incident(
        id=next_id,
        incidentTitle=incidentTitle.strip(),
        routeLine=routeLine.strip(),
        submitterEmail=submitterEmail.strip(),
        description=description.strip(),
        category=category,
        termsAccepted=True,
        submissionDate=datetime.now(timezone.utc).isoformat(),
    )

    INCIDENTS.append(incident)
    next_id += 1

    return home_redirect()


@app.post("/incidents/1/update")
async def update_incident_one(
    incidentTitle: str = Form(..., min_length=3, max_length=100),
    routeLine: str = Form(..., min_length=2, max_length=100),
) -> RedirectResponse:
    incident = next(
        (item for item in INCIDENTS if item.id == 1),
        None,
    )

    if incident is None:
        return home_redirect("Incident with ID 1 was not found.")

    incident.incidentTitle = incidentTitle.strip()
    incident.routeLine = routeLine.strip()

    return home_redirect()


@app.post("/incidents/delete-highest")
async def delete_highest_incident() -> RedirectResponse:
    if not INCIDENTS:
        return home_redirect("There are no incidents to delete.")

    highest_id = max(item.id for item in INCIDENTS)

    INCIDENTS[:] = [
        item for item in INCIDENTS if item.id != highest_id
    ]

    return home_redirect()