"""The Trophy case (0.52.0): what the library has finished, and milestones for it."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.auth.dependencies import DbSession, RequiredUser
from app.services import look, pagination, trophies
from app.templating import get_templates

router = APIRouter()


@router.get("/trophies", response_class=HTMLResponse)
def trophy_case(request: Request, session: DbSession, user: RequiredUser, page: int = 1):
    found = trophies.case(session)
    # Collections can run to hundreds; franchises and directors to a few dozen.
    pager = pagination.paginate(found.collections, page, path="/trophies", anchor="#collections")
    # Only Showcase makes a moment of a new badge, so only it uses one up (as with the confetti).
    unlocked = trophies.newly_earned(session, user.id, found) if look.get(session, user.id) == look.SHOWCASE else set()
    return get_templates().TemplateResponse(
        request, "trophies.html", {"user": user, "case": found, "pager": pager, "collections": pager.items,
                                   "unlocked": unlocked},
    )
