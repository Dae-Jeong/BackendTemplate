from template_fastcrud_api.exceptions.application import ApplicationError


class ProductNotFound(ApplicationError):
    pass


class SoldOut(ApplicationError):
    pass


class IdempotencyConflict(ApplicationError):
    pass
