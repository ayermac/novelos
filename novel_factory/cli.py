"""Novel Factory CLI — command-line interface for v3.7.

Provides the ``novelos`` console script and preserves ``python -m novel_factory.cli``
compatibility.

Commands:
    init-db          Initialize the database
    run-chapter      Drive a chapter through the production pipeline
    status           Show chapter status
    runs             Show workflow runs for a project
    artifacts        Show artifacts for a chapter
    human-resume     Resume a blocked chapter to a new status
    config show      Show current configuration
    config validate  Validate configuration
    seed-demo        Seed demo project data
    smoke-run        Run a smoke test on demo project
    doctor           Run system diagnostics
    batch run        Run batch production for multiple chapters
    batch status     Get batch production run status
    batch enqueue    Enqueue a batch production request (v3.4)
    batch queue-run  Execute next pending queue item (v3.4)
    batch queue-status  Get production queue status (v3.4)
    batch queue-pause   Pause a queue item (v3.4)
    batch queue-resume  Resume a paused queue item (v3.4)
    batch queue-retry   Retry a failed/timed-out queue item (v3.4)
    batch queue-timeouts  Mark timed-out queue items (v3.4)
    batch queue-events   View queue item audit events (v3.5)
    batch queue-cancel   Cancel a queue item (v3.5)
    batch queue-recover  Recover a stuck running item (v3.5)
    batch queue-doctor   Diagnose queue item (v3.5)
    serial create    Create a serial plan (v3.6)
    serial status    Get serial plan status (v3.6)
    serial enqueue-next  Enqueue next batch for serial plan (v3.6)
    serial advance   Advance serial plan with decision (v3.6)
    serial pause     Pause a serial plan (v3.6)
    serial resume    Resume a paused serial plan (v3.6)
    serial cancel    Cancel a serial plan (v3.6)
"""

# ── Re-export from cli_app for backward compatibility ─────────────

from .cli_app.main import build_parser, main

# Re-export helpers used by tests
from .cli_app.common import (
    _get_effective_llm_mode,
    _get_settings,
    _get_llm,
    _build_dispatcher,
    _StubLLM,
)
from .cli_app.output import _print_output

# Re-export command functions used by tests
from .cli_app.commands.core import (
    cmd_init_db,
    cmd_run_chapter,
    cmd_status,
    cmd_runs,
    cmd_artifacts,
    cmd_human_resume,
)
from .cli_app.commands.config import (
    cmd_config_show,
    cmd_config_validate,
    cmd_llm_profiles,
    cmd_llm_route,
    cmd_llm_validate,
    cmd_doctor,
)
from .cli_app.commands.demo import (
    cmd_seed_demo,
    cmd_smoke_run,
)
from .cli_app.commands.sidecar import (
    cmd_scout,
    cmd_report_daily,
    cmd_export_chapter,
    cmd_continuity_check,
    cmd_architect_suggest,
)
from .cli_app.commands.skills import (
    cmd_skill_list,
    cmd_skill_run,
    cmd_skill_show,
    cmd_skill_validate,
    cmd_skill_test,
)
from .cli_app.commands.quality import (
    cmd_quality_check,
    cmd_quality_report,
)
from .cli_app.commands.batch import (
    cmd_batch_run,
    cmd_batch_status,
    cmd_batch_review,
    cmd_batch_revise,
    cmd_batch_revision_status,
    cmd_batch_continuity,
    cmd_batch_continuity_status,
    cmd_batch_enqueue,
    cmd_batch_queue_run,
    cmd_batch_queue_status,
    cmd_batch_queue_pause,
    cmd_batch_queue_resume,
    cmd_batch_queue_retry,
    cmd_batch_queue_timeouts,
    cmd_batch_queue_events,
    cmd_batch_queue_cancel,
    cmd_batch_queue_recover,
    cmd_batch_queue_doctor,
    cmd_batch_queue_run_limit,
)
from .cli_app.commands.serial import (
    cmd_serial_create,
    cmd_serial_status,
    cmd_serial_enqueue_next,
    cmd_serial_advance,
    cmd_serial_pause,
    cmd_serial_resume,
    cmd_serial_cancel,
)
from .cli_app.commands.review import (
    cmd_review_pack,
    cmd_review_chapter,
    cmd_review_timeline,
    cmd_review_diff,
    cmd_review_export,
)

# Re-export commonly used dependencies for test convenience
from .config.loader import load_settings_with_cli, validate_settings
from .config.settings import Settings
from .db.connection import init_db
from .db.repository import Repository
from .dispatcher import Dispatcher
from .llm.stub_provider import StubLLM
from .llm.provider import LLMProvider

if __name__ == "__main__":
    main()
