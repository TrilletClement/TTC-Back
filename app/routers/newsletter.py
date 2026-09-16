from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.rate_limit import limiter
from app.domain.exceptions import ValidationError
from app.orm_models.db import get_db
from app.repositories.newsletter_repo import NewsletterRepository
from app.schemas.newsletter import NewsletterSubscribeRequest
from app.services.newsletterService import NewsletterService

router = APIRouter(prefix="/api/newsletter", tags=["newsletter"])


def get_service(db: Session = Depends(get_db)) -> NewsletterService:
    return NewsletterService(NewsletterRepository(db))


@router.post("/subscribe")
@limiter.limit("5/minute")
def subscribe(request: Request, payload: NewsletterSubscribeRequest, svc: NewsletterService = Depends(get_service)):
    svc.subscribe(payload.email, user_id=None, source="blog")
    return {"message": "Inscription réussie."}


@router.get("/unsubscribe")
def unsubscribe(token: str, svc: NewsletterService = Depends(get_service)):
    try:
        return svc.unsubscribe(token)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
