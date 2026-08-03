from app.repositories.alert_repo import AlertRepository


class AlertService:
    def __init__(self, repo: AlertRepository):
        self.repo = repo

    def get_alerts_for_lines(self, line_ids: list[int]) -> dict:
        if not line_ids:
            return {"lines": {}}

        lines: dict[str, list[dict]] = {}
        for alert in self.repo.get_alerts_for_lines(line_ids):
            entry = {
                "headerText": alert.header_text,
                "descriptionText": alert.description_text,
                "effect": alert.effect,
                "url": alert.url,
            }
            for line in alert.lines:
                if line.id in line_ids:
                    lines.setdefault(str(line.id), []).append(entry)

        return {"lines": lines}
