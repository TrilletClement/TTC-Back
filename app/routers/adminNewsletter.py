from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.domain.exceptions import NotFoundError
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.repositories.newsletter_repo import NewsletterRepository
from app.schemas.newsletter import NewsletterCampaignRequest, NewsletterSubscriberOut
from app.services.newsletterService import NewsletterService

router = APIRouter(prefix="/api/admin/newsletter", tags=["admin-newsletter"])


def get_service(db: Session = Depends(get_db)) -> NewsletterService:
    return NewsletterService(NewsletterRepository(db))


@router.get("", response_model=list[NewsletterSubscriberOut])
@require_admin
def list_subscribers(current_user: User, svc: NewsletterService = Depends(get_service)):
    return svc.list_subscribers()


@router.delete("/{subscriber_id}")
@require_admin
def remove_subscriber(subscriber_id: int, current_user: User, svc: NewsletterService = Depends(get_service)):
    try:
        svc.remove_subscriber(subscriber_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "removed"}


@router.post("/send")
@require_admin
async def send_campaign(
    payload: NewsletterCampaignRequest,
    background_tasks: BackgroundTasks,
    current_user: User,
    svc: NewsletterService = Depends(get_service),
):
    total = len(svc.list_subscribers())
    background_tasks.add_task(svc.send_campaign, payload.subject, payload.body_html)
    return {"message": f"Envoi en cours à {total} abonné(s)."}
