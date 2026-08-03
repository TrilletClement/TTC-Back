from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import relationship

from app.orm_models.db import Base


line_alert_line = Table(
    "line_alert_line",
    Base.metadata,
    Column("line_id", Integer, ForeignKey("line.id", ondelete="CASCADE"), primary_key=True),
    Column("alert_id", Integer, ForeignKey("line_alert.id", ondelete="CASCADE"), primary_key=True),
)


class LineAlert(Base):
    __tablename__ = "line_alert"

    id = Column(Integer, primary_key=True)
    agency_name = Column(String(100), ForeignKey("agency.name"), nullable=False)
    gtfs_alert_id = Column(String(100), nullable=False)
    effect = Column(String(50), nullable=True)
    header_text = Column(Text, nullable=False)
    description_text = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    agency = relationship("Agency", backref="alerts")
    lines = relationship("Line", secondary=line_alert_line, backref="alerts")
