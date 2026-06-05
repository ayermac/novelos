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
from .characters import router as characters_router
from .outlines import router as outlines_router
from .world_settings import router as world_settings_router
from .factions import router as factions_router
from .plot_holes import router as plot_holes_router
from .instructions import router as instructions_router
from .project_context import router as context_router
from .chapter_readonly import router as readonly_router
from .genesis import router as genesis_router
from .memory_updates import router as memory_updates_router
from .story_facts import router as story_facts_router
from .skills import router as skills_router
from .project_skill_overrides import router as project_skill_overrides_router
from .production import router as production_router
from .versions import router as versions_router
from .workflow_timeline import router as workflow_timeline_router
from .agent_memory import router as agent_memory_router
from .agent_ops import router as agent_ops_router
from .desktop import router as desktop_router
from .quality_diagnosis import router as quality_diagnosis_router
from .creative_contracts import router as creative_contracts_router

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
    "characters_router",
    "outlines_router",
    "world_settings_router",
    "factions_router",
    "plot_holes_router",
    "instructions_router",
    "context_router",
    "readonly_router",
    "genesis_router",
    "memory_updates_router",
    "story_facts_router",
    "skills_router",
    "project_skill_overrides_router",
    "production_router",
    "versions_router",
    "workflow_timeline_router",
    "agent_memory_router",
    "agent_ops_router",
    "desktop_router",
    "quality_diagnosis_router",
    "creative_contracts_router",
]
