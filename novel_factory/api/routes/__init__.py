"""API routes package."""

from .health import router as health_router
from .dashboard import router as dashboard_router
from .projects import router as projects_router
from .onboarding import router as onboarding_router
from .run import router as run_router
from .runs import router as runs_router
from .review import router as review_router
from .style import router as style_router
from .settings import router as settings_router
from .acceptance import router as acceptance_router

__all__ = [
    "health_router",
    "dashboard_router",
    "projects_router",
    "onboarding_router",
    "run_router",
    "runs_router",
    "review_router",
    "style_router",
    "settings_router",
    "acceptance_router",
]
