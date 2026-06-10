from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.user_access import require_admin
from app.orm_models.auth import User
from app.orm_models.db import get_db
from app.repositories.price_repo import PriceRepository
from app.schemas.price import PriceVersionCreate
from app.services.adminPricesService import AdminPricesService

router = APIRouter(prefix="/api/admin/price-versions", tags=["admin-prices"])


def get_service(db: Session = Depends(get_db)) -> AdminPricesService:
    return AdminPricesService(PriceRepository(db))


@router.get("")
@require_admin
def list_price_versions(current_user: User, svc: AdminPricesService = Depends(get_service)):
    return svc.list_versions()


@router.post("", status_code=201)
@require_admin
def create_price_version(
    payload: PriceVersionCreate,
    current_user: User,
    svc: AdminPricesService = Depends(get_service),
):
    return svc.create_version(payload)