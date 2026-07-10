"""v6.10.19: CharacterStore - aggregates character + style_sample queries."""

from __future__ import annotations

from .base import BaseStore


class CharacterStore(BaseStore):
    """Aggregates character data with style samples."""

    def get_characters_with_samples(self, project_id: str) -> list[dict]:
        """All characters with their style samples."""
        chars = self._repo.list_characters(project_id)
        if not isinstance(chars, list):
            return []
        result = []
        for c in chars:
            char_id = c.get("id")
            samples = self._safe_style_samples(project_id, char_id) if char_id else []
            c["style_samples"] = samples
            result.append(c)
        return result

    def get_character_arc(self, project_id: str, char_id: int) -> dict | None:
        """Character with style samples and protagonist status."""
        char = self._repo.get_character(project_id, char_id)
        if char is None:
            return None
        char["style_samples"] = self._safe_style_samples(project_id, char_id)
        char["is_protagonist"] = self._is_protagonist(project_id, char)
        return char

    def get_protagonist(self, project_id: str) -> dict | None:
        """Protagonist character with style samples."""
        char = self._repo.get_protagonist(project_id)
        if char is None:
            return None
        char_id = char.get("id")
        if char_id:
            char["style_samples"] = self._safe_style_samples(project_id, char_id)
        char["is_protagonist"] = True
        return char

    def _safe_style_samples(self, project_id: str, char_id: int) -> list[dict]:
        try:
            result = self._repo.list_style_samples(project_id, char_id=char_id)
            return result if isinstance(result, list) else []
        except (AttributeError, TypeError):
            return []

    def _is_protagonist(self, project_id: str, char: dict) -> bool:
        try:
            protag = self._repo.get_protagonist(project_id)
            return protag is not None and protag.get("id") == char.get("id")
        except (AttributeError, TypeError):
            return False
