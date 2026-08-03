from sqlalchemy.orm import Session, joinedload

from app.orm_models.alert import LineAlert, line_alert_line


class AlertRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_alerts_for_lines(self, line_ids: list[int]) -> list[LineAlert]:
        if not line_ids:
            return []
        return (
            self.db.query(LineAlert)
            .join(line_alert_line, line_alert_line.c.alert_id == LineAlert.id)
            .filter(line_alert_line.c.line_id.in_(line_ids))
            .options(joinedload(LineAlert.lines))
            .distinct()
            .all()
        )
