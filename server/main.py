from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StartletteHttpException
from database import Base, engine
from routers import users, practices, sessions, ws


@asynccontextmanager
async def lifesapn(_app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(lifespan=lifesapn)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory="media"), name="media")
templates = Jinja2Templates(directory="templates")
app.include_router(users.router, prefix="/api/users", tags=["Users"])
app.include_router(sessions.router, prefix="/api/sessions", tags=["Sesstions"])
app.include_router(
    practices.router, prefix="/api/practices", tags=["Practice Sessions"]
)
app.include_router(ws.router, prefix="", tags=["WebSocket"])


@app.get("/health", include_in_schema=False)
async def health_check():
    return {"status": "ok"}


@app.exception_handler(StartletteHttpException)
async def general_http_exception_handler(
    request: Request, exception: StartletteHttpException
):

    if request.url.path.startswith("/api"):
        return await http_exception_handler(request, exception)

    message = exception.detail if exception.detail else "An Error Occured."
    return templates.TemplateResponse(
        request,
        "error.html",
        {"status_code": exception.status_code, "message": message},
        status_code=exception.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exception: RequestValidationError
):
    if request.url.path.startswith("/api"):
        return await request_validation_exception_handler(request, exception)

    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            "message": "Invalid request. Check your inputs again.",
        },
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
