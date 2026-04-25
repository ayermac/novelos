"""pytest configuration and shared fixtures."""

import sys
from pathlib import Path

# Ensure novel_factory is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
