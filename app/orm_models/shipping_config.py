from sqlalchemy import Column, Integer, String

from app.orm_models.db import Base


class ShippingOptionConfig(Base):
    __tablename__ = "shipping_option_config"

    id          = Column(Integer, primary_key=True, index=True)
    option_code = Column(String(100), unique=True, nullable=False)


class ShippingCountry(Base):
    __tablename__ = "shipping_country"

    id           = Column(Integer, primary_key=True, index=True)
    country_code = Column(String(3), unique=True, nullable=False)
    sort_order   = Column(Integer, nullable=False, default=0)
