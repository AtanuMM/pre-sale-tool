import os
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import get_session_factory
from app.health_checks import assert_dependencies_ready, run_dependency_checks
from app.models.auth import User
from app.routers import auth as auth_router
from app.routers import projects as projects_router
from app.routers import roles as roles_router
from app.routers import settings as settings_router
from app.routers import steps as steps_router
from app.routers import users as users_router
from app.security.deps import require_permission
from app.services.generation_recovery import try_startup_recovery
from app.services.step_generation import shutdown_generation_executor

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.SKIP_STARTUP_CHECKS:
        assert_dependencies_ready()
    with get_session_factory()() as session:
        try_startup_recovery(session)
    yield
    shutdown_generation_executor()


app = FastAPI(title="ScopeDesk API", lifespan=lifespan)

app.include_router(auth_router.router)
app.include_router(users_router.router)
app.include_router(roles_router.router)
app.include_router(settings_router.router)
app.include_router(projects_router.router)
app.include_router(steps_router.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def health_ready(response: Response) -> dict[str, Any]:
    status = run_dependency_checks()
    body: dict[str, Any] = {
        "status": "ready" if status.is_ready else "not_ready",
        "checks": {
            "database": status.database,
            "object_storage": status.object_storage,
        },
    }
    if not status.is_ready:
        response.status_code = 503
    return body


if (
    settings.APP_ENV in ("development", "test")
    and os.environ.get("ENABLE_TEST_ROUTES") == "true"
):
    _require_audit_view = require_permission("audit.view")

    @app.get("/test/protected")
    def test_protected(
        user: Annotated[User, Depends(_require_audit_view)],
    ):
        return {"ok": True}
