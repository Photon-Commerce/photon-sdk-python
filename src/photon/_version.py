"""Single source of truth for the package version.

``pyproject.toml`` reads the version from here (hatchling ``[tool.hatch.version]``),
so bump it in this file only.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.0.1"
