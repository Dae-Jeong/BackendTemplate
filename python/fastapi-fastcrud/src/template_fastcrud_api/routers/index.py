from fastapi import APIRouter

from template_fastcrud_api.http.errors import PROBLEM_RESPONSES
from template_fastcrud_api.schemas.responses import MessageData, Success

router = APIRouter()


@router.get("/", responses=PROBLEM_RESPONSES)
def index() -> Success[MessageData]:
    return Success(data=MessageData(message="Hello, FastAPI!"))
