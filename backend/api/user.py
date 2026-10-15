from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from api import db
from api.auth import get_user, require_admin

router = APIRouter(prefix="/api")


class FeedbackIn(BaseModel):
    message: str = Field(..., min_length=3, max_length=2000)
    rating: int | None = Field(None, ge=1, le=5)
    name: str = Field("", max_length=80)
    email: str = Field("", max_length=120)


@router.get("/me/activity")
async def my_activity(authorization: str = Header("")):
    u = get_user(authorization)
    if not u:
        raise HTTPException(401, "Sign in to see your activity")
    return db.user_activity(u["id"])


@router.post("/feedback")
async def send_feedback(body: FeedbackIn, authorization: str = Header("")):
    u = get_user(authorization)
    name = (u or {}).get("name") or body.name.strip() or "Guest"
    email = (u or {}).get("email") or body.email.strip()
    db.add_feedback(u, name, email, body.rating, body.message.strip())
    return {"ok": True}


@router.get("/admin/overview")
async def admin_overview(_: dict = Depends(require_admin)):
    return {"stats": db.stats(), "users": db.list_users(), "feedback": db.list_feedback()}
