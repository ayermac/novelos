"""Stats package for novel_factory.

v6.10.13: Deterministic statistics for quality analysis.
"""

from .style_stats import StyleStats, compute_style_stats

__all__ = ["StyleStats", "compute_style_stats"]
