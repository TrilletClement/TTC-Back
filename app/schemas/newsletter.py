from datetime import datetime

from pydantic import BaseModel, EmailStr


class NewsletterSubscribeRequest(BaseModel):
    email: EmailStr


class NewsletterSubscriberOut(BaseModel):
    id: int
    email: str
    source: str
    subscribed_at: datetime

    class Config:
        from_attributes = True


class NewsletterCampaignRequest(BaseModel):
    subject: str
    body_html: str
