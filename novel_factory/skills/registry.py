"""Skill Registry for v2.2 manifest-based plugin system.

Manages skill registration, configuration, and execution.
Skills are loaded from skills.yaml with manifest support.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

from .base import BaseSkill
from .manifest import (
    SkillManifestError,
    load_manifest,
    validate_manifest_for_agent,
)
from ..models.skill_manifest import SkillManifest

logger = logging.getLogger(__name__)


class SkillPermissionError(Exception):
    """Error when skill lacks required permissions."""

    pass


class SkillStageNotAllowedError(Exception):
    """Error when skill is not allowed for agent/stage."""

    pass


class SkillRegistry:
    """Registry for managing skills.

    Skills are loaded from skills.yaml with manifest support.
    v2.2 validates manifest permissions and agent/stage restrictions.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        """Initialize registry.

        Args:
            config_path: Path to skills.yaml. If None, uses default location.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "skills.yaml"

        self.config_path = Path(config_path)
        self.skills_config: dict[str, Any] = {}
        self.agent_skills: dict[str, dict[str, list[str]]] = {}
        self._skill_cache: dict[str, BaseSkill] = {}
        self._manifest_cache: dict[str, SkillManifest] = {}

        self._load_config()
    
    def _load_config(self) -> None:
        """Load skills.yaml configuration."""
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            self.skills_config = config.get("skills", {})
            self.agent_skills = config.get("agent_skills", {})

            logger.info(f"Loaded {len(self.skills_config)} skills from {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load skills config: {e}")
            self.skills_config = {}
            self.agent_skills = {}

        # v3.8: Auto-discover imported skill packages
        self._discover_imported_skills()

    def _discover_imported_skills(self) -> None:
        """Scan skill_packages/ for imported skills and register them.

        Imported skills are added to skills_config with enabled=false so
        they can be inspected via ``skills show/test``, but they are NOT
        added to agent_skills (no auto-mount).
        """
        packages_dir = self.config_path.parent.parent / "skill_packages"
        if not packages_dir.is_dir():
            return

        for pkg_dir in sorted(packages_dir.iterdir()):
            if not pkg_dir.is_dir():
                continue

            manifest_path = pkg_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest_data = yaml.safe_load(f)
            except Exception:
                continue

            # Only register imported_instruction skills
            if not isinstance(manifest_data, dict):
                continue
            if manifest_data.get("kind") != "imported_instruction":
                continue

            skill_id = manifest_data.get("id")
            if not skill_id or skill_id in self.skills_config:
                continue

            # Register with safe defaults
            self.skills_config[skill_id] = {
                "enabled": manifest_data.get("enabled", False),
                "package": f"skill_packages/{pkg_dir.name}",
                "type": manifest_data.get("kind", "context"),
                "class": manifest_data.get("class_name", "ImportedInstructionSkill"),
                "description": manifest_data.get("description", ""),
                "config": {},
                "_imported": True,  # marker for imported skills
            }

            logger.info(f"Auto-discovered imported skill: {skill_id}")
    
    def _resolve_package_manifest_path(self, package_path: str) -> Optional[Path]:
        """Resolve package manifest path with security validation.
        
        Args:
            package_path: Package relative path (e.g., "skill_packages/humanizer_zh")
            
        Returns:
            Resolved manifest path or None if invalid
            
        Security:
            - Rejects absolute paths
            - Rejects paths with ".." (directory traversal)
            - Rejects paths outside repository
        """
        # Security: reject absolute paths
        if Path(package_path).is_absolute():
            logger.error(f"Package path must be relative: {package_path}")
            return None
        
        # Security: reject directory traversal
        if ".." in package_path:
            logger.error(f"Package path contains directory traversal: {package_path}")
            return None
        
        # Resolve full path
        full_path = self.config_path.parent.parent / package_path / "manifest.yaml"
        
        # Security: ensure path is within repository
        try:
            full_path.resolve().relative_to(self.config_path.parent.parent.resolve())
        except ValueError:
            logger.error(f"Package path outside repository: {package_path}")
            return None
        
        # Check if manifest exists
        if not full_path.exists():
            logger.warning(f"Package manifest not found: {full_path}")
            return None
        
        return full_path
    
    def get_manifest(self, skill_id: str) -> Optional[SkillManifest]:
        """Get manifest for a skill.

        Args:
            skill_id: Skill identifier

        Returns:
            SkillManifest or None if not found
        """
        # Check cache
        if skill_id in self._manifest_cache:
            return self._manifest_cache[skill_id]

        # Check if skill exists
        if skill_id not in self.skills_config:
            logger.warning(f"Unknown skill: {skill_id}")
            return None

        skill_config = self.skills_config[skill_id]
        
        # v2.3: Try package manifest first
        package_path = skill_config.get("package")
        if package_path:
            manifest_path = self._resolve_package_manifest_path(package_path)
            if manifest_path:
                try:
                    manifest = load_manifest(manifest_path)
                    
                    # Validate skill id matches manifest id
                    if manifest.id != skill_id:
                        raise SkillManifestError(
                            f"Skill id '{skill_id}' does not match manifest id '{manifest.id}'"
                        )
                    
                    # Cache manifest
                    self._manifest_cache[skill_id] = manifest
                    logger.info(f"Loaded manifest from package for skill {skill_id}")
                    return manifest
                except SkillManifestError as e:
                    logger.error(f"Failed to load package manifest for skill {skill_id}: {e}")
                    # Fall through to legacy manifest
        
        # v2.2: Try legacy manifest
        manifest_path = skill_config.get("manifest")
        if manifest_path:
            try:
                manifest = load_manifest(manifest_path)

                # Validate skill id matches manifest id
                if manifest.id != skill_id:
                    raise SkillManifestError(
                        f"Skill id '{skill_id}' does not match manifest id '{manifest.id}'"
                    )

                # Cache manifest
                self._manifest_cache[skill_id] = manifest
                return manifest
            except SkillManifestError as e:
                logger.error(f"Failed to load manifest for skill {skill_id}: {e}")
                return None
        
        # v2.1 compatibility: no manifest, return None
        logger.debug(f"Skill {skill_id} has no manifest (v2.1 compatibility)")
        return None
    
    def get_skill(self, skill_id: str) -> Optional[BaseSkill]:
        """Get a skill instance by ID.

        Args:
            skill_id: Skill identifier (e.g., "humanizer-zh")

        Returns:
            Skill instance or None if not found/disabled
        """
        # Check if skill exists in config
        if skill_id not in self.skills_config:
            logger.warning(f"Unknown skill: {skill_id}")
            return None

        skill_config = self.skills_config[skill_id]

        # Check if skill is enabled
        if not skill_config.get("enabled", True):
            logger.info(f"Skill {skill_id} is disabled")
            return None

        # Check cache
        if skill_id in self._skill_cache:
            return self._skill_cache[skill_id]

        # Get manifest
        manifest = self.get_manifest(skill_id)
        
        # v2.3: If package is configured, it's the ONLY loading path (no fallback)
        package_path = skill_config.get("package")
        if package_path:
            # Package is configured - must load from package handler
            if not manifest or not manifest.package:
                logger.error(f"Skill {skill_id} has package path but no package manifest")
                return None
            
            skill_class = self._load_skill_from_package(
                package_path, 
                manifest.package.entry_class
            )
            if not skill_class:
                logger.error(f"Failed to load skill class from package for {skill_id}")
                return None
            
            try:
                skill_instance = skill_class(config=skill_config.get("config", {}))
                self._skill_cache[skill_id] = skill_instance
                logger.info(f"Instantiated skill from package: {skill_id}")
                return skill_instance
            except Exception as e:
                logger.error(f"Failed to instantiate skill {skill_id} from package: {e}")
                return None
        
        # v2.2/v2.1: Legacy loading (only for skills without package)
        if manifest:
            skill_class_name = manifest.class_name
        else:
            # v2.1 compatibility: use config class field
            skill_class_name = skill_config.get("class")

        if not skill_class_name:
            logger.error(f"Skill {skill_id} has no class defined")
            return None

        # Import skill class using base.py whitelist
        from .base import _get_skill_class

        skill_class = _get_skill_class(skill_class_name)
        if skill_class is None:
            logger.error(f"Skill class {skill_class_name} not in whitelist")
            return None

        # Import and instantiate
        try:
            skill_instance = skill_class(config=skill_config.get("config", {}))
            self._skill_cache[skill_id] = skill_instance

            logger.info(f"Instantiated skill: {skill_id}")
            return skill_instance
        except Exception as e:
            logger.error(f"Failed to instantiate skill {skill_id}: {e}")
            return None
    
    def _load_skill_from_package(
        self, 
        package_path: str, 
        entry_class: str
    ) -> Optional[type]:
        """Load skill class from package handler.
        
        Args:
            package_path: Package relative path (e.g., "skill_packages/humanizer_zh")
            entry_class: Entry class name (e.g., "HumanizerZhSkill")
            
        Returns:
            Skill class or None if failed
            
        Security:
            - Only allows loading from novel_factory.skill_packages.*
            - Validates package path is within repository
        """
        # Security: validate package path
        manifest_path = self._resolve_package_manifest_path(package_path)
        if not manifest_path:
            logger.error(f"Invalid package path: {package_path}")
            return None
        
        # Extract package name from path
        # e.g., "skill_packages/humanizer_zh" -> "humanizer_zh"
        package_name = Path(package_path).name
        
        # Construct module path
        # e.g., "novel_factory.skill_packages.humanizer_zh.handler"
        module_path = f"novel_factory.skill_packages.{package_name}.handler"
        
        try:
            import importlib
            module = importlib.import_module(module_path)
            
            # Get entry class from module
            if not hasattr(module, entry_class):
                logger.error(f"Module {module_path} has no class {entry_class}")
                return None
            
            skill_class = getattr(module, entry_class)
            
            # Validate it's a BaseSkill subclass
            from .base import BaseSkill
            if not issubclass(skill_class, BaseSkill):
                logger.error(f"Class {entry_class} is not a BaseSkill subclass")
                return None
            
            logger.info(f"Loaded skill class {entry_class} from {module_path}")
            return skill_class
            
        except ImportError as e:
            logger.error(f"Failed to import module {module_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load skill from package {package_path}: {e}")
            return None
    
    def run_skill(
        self,
        skill_id: str,
        payload: dict[str, Any],
        agent: str = "manual",
        stage: str = "manual",
    ) -> dict[str, Any]:
        """Run a skill by ID with manifest validation.

        Args:
            skill_id: Skill identifier
            payload: Input data for the skill
            agent: Agent name (default: "manual")
            stage: Stage name (default: "manual")

        Returns:
            Skill result envelope: {ok: bool, error: str|null, data: dict}
        """
        # Check if skill exists
        if skill_id not in self.skills_config:
            return {
                "ok": False,
                "error": f"Skill not found: {skill_id}",
                "data": {},
            }

        skill_config = self.skills_config[skill_id]

        # Check if skill is enabled
        if not skill_config.get("enabled", True):
            return {
                "ok": False,
                "error": f"Skill is disabled: {skill_id}",
                "data": {},
            }

        # Validate manifest if present
        manifest = self.get_manifest(skill_id)
        if manifest:
            # Validate agent/stage
            is_allowed, error_msg = validate_manifest_for_agent(manifest, agent, stage)
            if not is_allowed:
                logger.warning(f"Skill {skill_id} not allowed: {error_msg}")
                return {
                    "ok": False,
                    "error": error_msg,
                    "data": {},
                }

        # Get skill instance
        skill = self.get_skill(skill_id)
        if not skill:
            return {
                "ok": False,
                "error": f"Skill not found or disabled: {skill_id}",
                "data": {},
            }

        try:
            result = skill.run(payload)

            # Add manifest version to result if available
            if manifest and result.get("ok"):
                if "data" in result:
                    result["data"]["_manifest_version"] = manifest.version

            return result
        except Exception as e:
            logger.error(f"Skill {skill_id} execution failed: {e}")
            return {
                "ok": False,
                "error": str(e),
                "data": {},
            }
    
    def get_skills_for_agent(self, agent: str, stage: str) -> list[str]:
        """Get skills configured for an agent at a specific stage.

        Args:
            agent: Agent name (e.g., "polisher")
            stage: Stage name (e.g., "after_llm")

        Returns:
            List of skill IDs (only enabled skills with valid manifest)
        """
        agent_config = self.agent_skills.get(agent, {})
        all_skills = agent_config.get(stage, [])

        # Filter out disabled skills and validate manifest
        enabled_skills = []
        for skill_id in all_skills:
            skill_config = self.skills_config.get(skill_id, {})
            if not skill_config.get("enabled", True):
                continue

            # Validate manifest if present
            manifest = self.get_manifest(skill_id)
            if manifest:
                is_allowed, _ = validate_manifest_for_agent(manifest, agent, stage)
                if not is_allowed:
                    logger.warning(
                        f"Skill {skill_id} not allowed for {agent}/{stage}, skipping"
                    )
                    continue

            enabled_skills.append(skill_id)

        return enabled_skills
    
    def run_skills_for_agent(
        self,
        agent: str,
        stage: str,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Run all skills configured for an agent at a specific stage.

        Args:
            agent: Agent name
            stage: Stage name
            payload: Input data

        Returns:
            List of skill results
        """
        skill_ids = self.get_skills_for_agent(agent, stage)
        results = []

        for skill_id in skill_ids:
            result = self.run_skill(skill_id, payload, agent=agent, stage=stage)
            results.append({
                "skill_id": skill_id,
                "result": result,
            })

            # Check failure policy
            if not result.get("ok"):
                manifest = self.get_manifest(skill_id)
                if manifest and manifest.failure_policy.on_error == "block":
                    logger.error(f"Skill {skill_id} failed with block policy, stopping")
                    break
                else:
                    logger.warning(f"Skill {skill_id} failed, continuing")

        return results
    
    def list_skills(self) -> list[dict[str, Any]]:
        """List all configured skills with manifest info.

        Returns:
            List of skill info dicts
        """
        skills = []
        for skill_id, config in self.skills_config.items():
            manifest = self.get_manifest(skill_id)
            
            # Get package info
            package_path = config.get("package")

            if manifest:
                # Use manifest info
                skill_info = {
                    "id": skill_id,
                    "name": manifest.name,
                    "version": manifest.version,
                    "kind": manifest.kind,
                    "type": manifest.kind,  # v2.1 compatibility
                    "enabled": config.get("enabled", True) and manifest.enabled,
                    "class": manifest.class_name,  # v2.1 compatibility
                    "class_name": manifest.class_name,
                    "description": manifest.description,
                    "allowed_agents": manifest.allowed_agents,
                    "allowed_stages": manifest.allowed_stages,
                }
                
                # Add package info if available
                if package_path:
                    skill_info["package"] = package_path
                    if manifest.package:
                        skill_info["package_info"] = {
                            "name": manifest.package.name,
                            "handler": manifest.package.handler,
                            "entry_class": manifest.package.entry_class,
                            "prompts_dir": manifest.package.prompts_dir,
                            "rules_dir": manifest.package.rules_dir,
                            "fixtures": manifest.package.fixtures,
                        }
            else:
                # v2.1 compatibility
                skill_info = {
                    "id": skill_id,
                    "type": config.get("type"),
                    "kind": config.get("type"),  # v2.2 compatibility
                    "enabled": config.get("enabled", True),
                    "class": config.get("class"),
                    "class_name": config.get("class"),  # v2.2 compatibility
                    "description": config.get("description", ""),
                }
                
                # Add package info if available
                if package_path:
                    skill_info["package"] = package_path
            
            skills.append(skill_info)

        return skills
    
    def is_skill_enabled(self, skill_id: str) -> bool:
        """Check if a skill is enabled.

        Args:
            skill_id: Skill identifier

        Returns:
            True if skill exists and is enabled
        """
        if skill_id not in self.skills_config:
            return False
        return self.skills_config[skill_id].get("enabled", True)

    def validate_all(self) -> dict[str, Any]:
        """Validate all skills and manifests.

        Returns:
            Validation result: {ok: bool, errors: list, warnings: list}
        """
        errors = []
        warnings = []

        for skill_id, config in self.skills_config.items():
            # v2.3: Check package first
            package_path = config.get("package")
            if package_path:
                # Validate package path
                manifest_path = self._resolve_package_manifest_path(package_path)
                if not manifest_path:
                    errors.append(f"Skill '{skill_id}' has invalid package path: {package_path}")
                    continue
                
                # Validate package structure
                package_dir = manifest_path.parent
                
                # Check handler exists
                handler_path = package_dir / "handler.py"
                if not handler_path.exists():
                    warnings.append(f"Skill '{skill_id}' package missing handler.py")
                
                # Check fixtures exists
                fixtures_path = package_dir / "tests" / "fixtures.yaml"
                if not fixtures_path.exists():
                    warnings.append(f"Skill '{skill_id}' package missing tests/fixtures.yaml")
            
            # Check if skill has manifest (v2.2 or package manifest)
            manifest = self.get_manifest(skill_id)
            if not manifest:
                if not package_path:
                    warnings.append(f"Skill '{skill_id}' has no manifest (v2.1 compatibility)")
                continue

            # Validate skill id matches manifest id
            if manifest.id != skill_id:
                errors.append(
                    f"Skill id '{skill_id}' does not match manifest id '{manifest.id}'"
                )

        return {
            "ok": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    def validate_skill_for_agent(
        self,
        skill_id: str,
        agent: str,
        stage: str,
    ) -> tuple[bool, str]:
        """Validate if a skill can be used by an agent at a stage.

        Args:
            skill_id: Skill identifier
            agent: Agent name
            stage: Stage name

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check if skill exists
        if skill_id not in self.skills_config:
            return False, f"Skill not found: {skill_id}"

        # Check if skill is enabled
        if not self.is_skill_enabled(skill_id):
            return False, f"Skill is disabled: {skill_id}"

        # Check manifest
        manifest = self.get_manifest(skill_id)
        if manifest:
            return validate_manifest_for_agent(manifest, agent, stage)

        # No manifest, allow (v2.1 compatibility)
        return True, ""
    
    def test_skill(self, skill_id: str) -> dict[str, Any]:
        """Run fixtures for a skill.

        Unlike run_skill, this method can test disabled skills because
        ``skills test`` is a manual operation — the user explicitly asked
        to test the skill.

        Args:
            skill_id: Skill identifier

        Returns:
            Test result: {ok: bool, error: str|null, data: {passed: int, failed: int, total: int, cases: list}}
        """
        # Check if skill exists
        if skill_id not in self.skills_config:
            return {
                "ok": False,
                "error": f"Skill not found: {skill_id}",
                "data": None,
            }
        
        skill_config = self.skills_config[skill_id]
        
        # Get package path
        package_path = skill_config.get("package")
        if not package_path:
            return {
                "ok": False,
                "error": f"Skill '{skill_id}' has no package (test requires package)",
                "data": None,
            }
        
        # Resolve fixtures path
        manifest_path = self._resolve_package_manifest_path(package_path)
        if not manifest_path:
            return {
                "ok": False,
                "error": f"Invalid package path: {package_path}",
                "data": None,
            }
        
        fixtures_path = manifest_path.parent / "tests" / "fixtures.yaml"
        if not fixtures_path.exists():
            return {
                "ok": False,
                "error": f"Fixtures not found: {fixtures_path}",
                "data": None,
            }
        
        # Load fixtures
        try:
            with open(fixtures_path, "r", encoding="utf-8") as f:
                fixtures = yaml.safe_load(f)
        except Exception as e:
            return {
                "ok": False,
                "error": f"Failed to load fixtures: {e}",
                "data": None,
            }
        
        # Run test cases
        cases = fixtures.get("cases", [])
        if not cases:
            return {
                "ok": False,
                "error": "No test cases found in fixtures",
                "data": None,
            }

        # Get skill instance — allow testing disabled skills
        skill = self.get_skill(skill_id)
        if not skill:
            # For disabled skills, try to instantiate directly via package
            manifest = self.get_manifest(skill_id)
            if manifest and manifest.package:
                skill_class = self._load_skill_from_package(
                    package_path, manifest.package.entry_class
                )
                if skill_class:
                    try:
                        skill = skill_class(config=skill_config.get("config", {}))
                    except Exception:
                        pass

        if not skill:
            return {
                "ok": False,
                "error": f"Cannot instantiate skill: {skill_id}",
                "data": None,
            }

        # Validate manifest for agent/stage access (manual/manual is allowed for imported)
        # Note: We check allowed_agents/allowed_stages but NOT manifest.enabled,
        # because ``skills test`` is a manual operation that should work on
        # disabled skills.
        manifest = self.get_manifest(skill_id)
        if manifest:
            if "manual" not in manifest.allowed_agents:
                return {
                    "ok": False,
                    "error": f"Skill '{skill_id}' is not allowed for agent 'manual'",
                    "data": None,
                }
            if "manual" not in manifest.allowed_stages:
                return {
                    "ok": False,
                    "error": f"Skill '{skill_id}' is not allowed for stage 'manual'",
                    "data": None,
                }

        passed = 0
        failed = 0
        results = []
        
        for case in cases:
            case_name = case.get("name", "unnamed")
            case_input = case.get("input", {})
            case_expect = case.get("expect", {})
            
            # Run skill directly (bypass enabled check)
            try:
                result = skill.run(case_input)
            except Exception as e:
                result = {"ok": False, "error": str(e), "data": {}}

            # Validate result against expectations
            is_passed = self._validate_test_result(result, case_expect)
            
            if is_passed:
                passed += 1
            else:
                failed += 1
            
            results.append({
                "name": case_name,
                "passed": is_passed,
                "result": result,
                "expect": case_expect,
            })
        
        return {
            "ok": failed == 0,
            "error": None if failed == 0 else f"{failed} test(s) failed",
            "data": {
                "passed": passed,
                "failed": failed,
                "total": len(cases),
                "cases": results,
            },
        }
    
    def _validate_test_result(
        self,
        result: dict[str, Any],
        expect: dict[str, Any],
    ) -> bool:
        """Validate test result against expectations.
        
        Args:
            result: Skill execution result
            expect: Expected result specification
            
        Returns:
            True if result matches expectations
        """
        # Check ok status
        expected_ok = expect.get("ok")
        if expected_ok is not None and result.get("ok") != expected_ok:
            return False
        
        # Check error contains
        error_contains = expect.get("error_contains", [])
        if error_contains:
            error = result.get("error", "") or ""
            for substring in error_contains:
                if substring not in error:
                    return False
        
        # Check contains (in data)
        contains = expect.get("contains", [])
        if contains:
            data = result.get("data", {})
            for item in contains:
                # Check if item is a key in data
                if item in data:
                    continue
                # Check if item is a substring in humanized_text
                humanized_text = data.get("humanized_text", "")
                if item in humanized_text:
                    continue
                # Not found
                return False
        
        # Check not_contains (in data)
        not_contains = expect.get("not_contains", [])
        if not_contains:
            data = result.get("data", {})
            humanized_text = data.get("humanized_text", "")
            for substring in not_contains:
                if substring in humanized_text:
                    return False
        
        # Check specific values
        check = expect.get("check", {})
        if check:
            data = result.get("data", {})
            
            # Check ai_trace_score range
            if "ai_trace_score_min" in check:
                score = data.get("ai_trace_score", 0)
                if score < check["ai_trace_score_min"]:
                    return False
            
            if "ai_trace_score_max" in check:
                score = data.get("ai_trace_score", 100)
                if score > check["ai_trace_score_max"]:
                    return False
            
            # Check overall_score range
            if "overall_score_min" in check:
                scores = data.get("scores", {})
                overall = scores.get("overall_score", 0)
                if overall < check["overall_score_min"]:
                    return False
            
            # Check specific score ranges
            for score_key in ["conflict_intensity", "hook_strength", "dialogue_naturalness", 
                             "scene_immersion", "character_motivation", "pacing_control"]:
                max_key = f"{score_key}_max"
                min_key = f"{score_key}_min"
                
                if max_key in check or min_key in check:
                    scores = data.get("scores", {})
                    score = scores.get(score_key, 50)
                    
                    if max_key in check and score > check[max_key]:
                        return False
                    if min_key in check and score < check[min_key]:
                        return False
            
            # Check risk_level
            if "risk_level" in check:
                if data.get("risk_level") != check["risk_level"]:
                    return False
            
            # Check blocking
            if "blocking" in check:
                if data.get("blocking") != check["blocking"]:
                    return False
            
            # Check grade
            if "grade_in" in check:
                if data.get("grade") not in check["grade_in"]:
                    return False
            
            # Check has_issue_type
            if "has_issue_type" in check:
                issues = data.get("issues", [])
                issue_types = [i.get("type") for i in issues]
                if check["has_issue_type"] not in issue_types:
                    return False
            
            # Check has_issues
            if "has_issues" in check:
                has_issues = len(data.get("issues", [])) > 0
                if has_issues != check["has_issues"]:
                    return False
            
            # Check has_suggestions
            if "has_suggestions" in check:
                has_suggestions = len(data.get("suggestions", [])) > 0
                if has_suggestions != check["has_suggestions"]:
                    return False
            
            # Check changes_count
            if "changes_count" in check:
                changes = data.get("changes", [])
                if len(changes) != check["changes_count"]:
                    return False
        
        return True
