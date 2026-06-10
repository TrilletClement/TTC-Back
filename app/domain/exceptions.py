class NotFoundError(Exception):
    def __init__(self, resource: str, id: int | str):
        super().__init__(f"{resource} '{id}' not found")

class BusinessError(Exception):
    pass

class ValidationError(Exception):
    pass