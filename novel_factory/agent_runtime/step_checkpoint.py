"""StepCheckpoint — agent internal step-level checkpoints.

v6.10.13: Inspired by ainovel-cli's step-level checkpoint design.
Allows agents to save progress at each step for precise recovery.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StepCheckpoint:
    """Agent internal step-level checkpoint manager.

    Each checkpoint is saved as a JSON file with:
    - project_id
    - chapter_number
    - step_name
    - data (arbitrary JSON)
    - digest (SHA256 of data for idempotency)
    - timestamp
    """

    def __init__(self, base_dir: str | Path, agent_id: str):
        self.base_dir = Path(base_dir)
        self.agent_id = agent_id
        self.checkpoints_dir = self.base_dir / "checkpoints" / agent_id
        self._lock = threading.Lock()

        # Ensure directory exists
        self.checkpoints_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        project_id: str,
        chapter: int,
        step: str,
        data: dict[str, Any],
    ) -> str:
        """Save checkpoint for a step.

        Returns the digest of the saved data.
        """
        # Calculate digest
        data_json = json.dumps(data, sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(data_json.encode()).hexdigest()[:16]

        checkpoint = {
            "project_id": project_id,
            "chapter_number": chapter,
            "step": step,
            "agent_id": self.agent_id,
            "data": data,
            "digest": digest,
            "timestamp": datetime.now().isoformat(),
        }

        with self._lock:
            checkpoint_path = self._checkpoint_path(project_id, chapter, step)
            checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

            try:
                with open(checkpoint_path, "w", encoding="utf-8") as f:
                    json.dump(checkpoint, f, ensure_ascii=False, indent=2)

                logger.debug(
                    "StepCheckpoint: saved %s/%s/%s (digest=%s)",
                    project_id,
                    chapter,
                    step,
                    digest,
                )
                return digest
            except Exception as e:
                logger.error(
                    "StepCheckpoint: failed to save %s/%s/%s: %s",
                    project_id,
                    chapter,
                    step,
                    e,
                )
                raise

    def load(
        self,
        project_id: str,
        chapter: int,
        step: str,
    ) -> Optional[dict[str, Any]]:
        """Load checkpoint data for a step.

        Returns None if checkpoint doesn't exist.
        """
        with self._lock:
            checkpoint_path = self._checkpoint_path(project_id, chapter, step)
            if not checkpoint_path.exists():
                return None

            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    checkpoint = json.load(f)
                return checkpoint.get("data")
            except Exception as e:
                logger.warning(
                    "StepCheckpoint: failed to load %s/%s/%s: %s",
                    project_id,
                    chapter,
                    step,
                    e,
                )
                return None

    def has_step(
        self,
        project_id: str,
        chapter: int,
        step: str,
    ) -> bool:
        """Check if checkpoint exists for a step."""
        with self._lock:
            checkpoint_path = self._checkpoint_path(project_id, chapter, step)
            return checkpoint_path.exists()

    def get_digest(
        self,
        project_id: str,
        chapter: int,
        step: str,
    ) -> Optional[str]:
        """Get digest of existing checkpoint."""
        with self._lock:
            checkpoint_path = self._checkpoint_path(project_id, chapter, step)
            if not checkpoint_path.exists():
                return None

            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    checkpoint = json.load(f)
                return checkpoint.get("digest")
            except Exception:
                return None

    def list_steps(
        self,
        project_id: str,
        chapter: int,
    ) -> list[str]:
        """List all checkpoint steps for a chapter."""
        with self._lock:
            chapter_dir = self._chapter_dir(project_id, chapter)
            if not chapter_dir.exists():
                return []

            steps = []
            for checkpoint_file in chapter_dir.glob("*.json"):
                steps.append(checkpoint_file.stem)

            return sorted(steps)

    def clear_chapter(
        self,
        project_id: str,
        chapter: int,
    ) -> None:
        """Clear all checkpoints for a chapter.

        Called after chapter is committed successfully.
        """
        with self._lock:
            chapter_dir = self._chapter_dir(project_id, chapter)
            if not chapter_dir.exists():
                return

            for checkpoint_file in chapter_dir.glob("*.json"):
                try:
                    checkpoint_file.unlink()
                except Exception as e:
                    logger.warning(
                        "StepCheckpoint: failed to clear %s: %s",
                        checkpoint_file.name,
                        e,
                    )

            # Remove directory if empty
            try:
                chapter_dir.rmdir()
            except OSError:
                pass

            logger.info(
                "StepCheckpoint: cleared checkpoints for %s/%s",
                project_id,
                chapter,
            )

    def clear_project(self, project_id: str) -> None:
        """Clear all checkpoints for a project."""
        with self._lock:
            project_dir = self.checkpoints_dir / project_id
            if not project_dir.exists():
                return

            import shutil

            try:
                shutil.rmtree(project_dir)
                logger.info(
                    "StepCheckpoint: cleared all checkpoints for %s",
                    project_id,
                )
            except Exception as e:
                logger.error(
                    "StepCheckpoint: failed to clear project %s: %s",
                    project_id,
                    e,
                )

    def get_latest_checkpoint(
        self,
        project_id: str,
        chapter: int,
    ) -> Optional[dict[str, Any]]:
        """Get the latest checkpoint for a chapter.

        Returns the checkpoint with the latest timestamp.
        """
        steps = self.list_steps(project_id, chapter)
        if not steps:
            return None

        latest = None
        latest_time = None

        for step in steps:
            checkpoint_path = self._checkpoint_path(project_id, chapter, step)
            try:
                with open(checkpoint_path, "r", encoding="utf-8") as f:
                    checkpoint = json.load(f)

                timestamp = checkpoint.get("timestamp")
                if timestamp and (latest_time is None or timestamp > latest_time):
                    latest = checkpoint
                    latest_time = timestamp
            except Exception:
                continue

        return latest

    # ── Internal ──

    def _chapter_dir(self, project_id: str, chapter: int) -> Path:
        """Get chapter checkpoints directory."""
        return self.checkpoints_dir / project_id / f"chapter_{chapter:04d}"

    def _checkpoint_path(
        self, project_id: str, chapter: int, step: str
    ) -> Path:
        """Get checkpoint file path."""
        return self._chapter_dir(project_id, chapter) / f"{step}.json"


class CheckpointManager:
    """Manager for multiple agent checkpoint instances."""

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self._checkpoints: dict[str, StepCheckpoint] = {}
        self._lock = threading.Lock()

    def get_checkpoint(self, agent_id: str) -> StepCheckpoint:
        """Get or create checkpoint instance for an agent."""
        with self._lock:
            if agent_id not in self._checkpoints:
                self._checkpoints[agent_id] = StepCheckpoint(
                    self.base_dir, agent_id
                )
            return self._checkpoints[agent_id]

    def clear_chapter(self, project_id: str, chapter: int) -> None:
        """Clear all agent checkpoints for a chapter."""
        with self._lock:
            for checkpoint in self._checkpoints.values():
                checkpoint.clear_chapter(project_id, chapter)

    def clear_project(self, project_id: str) -> None:
        """Clear all agent checkpoints for a project."""
        with self._lock:
            for checkpoint in self._checkpoints.values():
                checkpoint.clear_project(project_id)

    def list_agents(self) -> list[str]:
        """List all registered agent IDs."""
        with self._lock:
            return list(self._checkpoints.keys())
