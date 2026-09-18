"""Authentication routes for the municipal transit incident application."""

import os
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates


BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
router = APIRouter()

# Demo credentials are intentionally local to this coursework application.
USERS = {
    "samina": {"password": "Transit4098!", "name": "Samina Maraj"},
    "reviewer": {"password": "Transit260!", "name": "Transit Reviewer"},
}

SESSION_USER_KEY = "user"
SESSION_LOGIN_TIME_KEY = "login_time"
IDLE_TIMEOUT_SECONDS = int(os.getenv("SESSION_IDLE_TIMEOUT", "900"))


def current_user(request: Request) -> dict | None:
    """Return the session user unless the idle timeout has expired."""
    user = request.session.get(SESSION_USER_KEY)
    login_time = request.session.get(SESSION_LOGIN_TIME_KEY)

    if not user or not isinstance(login_time, (int, float)):
        return None

    if time.time() - login_time > IDLE_TIMEOUT_SECONDS:
        request.session.clear()
        return None

    # Refresh the activity timestamp on every authenticated request.
    request.session[SESSION_LOGIN_TIME_KEY] = time.time()
    return user


def page_context(request: Request, **values: object) -> dict[str, object]:
    return {"request": request, "user": current_user(request), **values}


@router.get("/", response_class=HTMLResponse, name="home")
async def home_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context=page_context(request),
    )


@router.get("/login", response_class=HTMLResponse, name="login")
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context=page_context(request),
    )


@router.post("/login", response_class=HTMLResponse, response_model=None)
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    account = USERS.get(username.strip().casefold())
    if account is None or account["password"] != password:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context=page_context(
                request,
                error="Invalid username or password. Please try again.",
                attempted_username=username,
            ),
            status_code=401,
        )

    request.session.clear()
    request.session[SESSION_USER_KEY] = {
        "username": username.strip().casefold(),
        "name": account["name"],
    }
    request.session[SESSION_LOGIN_TIME_KEY] = time.time()
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse, name="dashboard")
async def dashboard_page(request: Request) -> HTMLResponse:
    user = current_user(request)
    if user is None:
        return RedirectResponse(url="/login?next=/dashboard", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=page_context(request),
    )


@router.get("/logout", response_class=RedirectResponse, name="logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url="/", status_code=303)
