from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from ..jinja import render
from ..views.home import home_context

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def home():
    # Lazy import: app.py imports this router and we'd loop on import otherwise.
    from ..projects import get_projects
    projects = get_projects()
    return render(
        "home.html",
        title="Home",
        projects=projects,
        breadcrumbs=[{"label": "holoctl", "href": "/"}, {"label": "Home"}],
        **home_context(projects),
    )
