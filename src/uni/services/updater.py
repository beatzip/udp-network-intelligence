"""Update checker — check GitHub releases for new versions."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com/repos/{owner}/{repo}/releases/latest"


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    """Information about a GitHub release."""
    version: str
    url: str
    body: str


class UpdateChecker:
    """Check for application updates via GitHub releases API."""

    def __init__(self, owner: str, repo: str, current_version: str) -> None:
        """Initialize the update checker.

        Args:
            owner: GitHub repository owner.
            repo: GitHub repository name.
            current_version: Current app version string.
        """
        self._owner = owner
        self._repo = repo
        self._current = current_version

    @property
    def api_url(self) -> str:
        """GitHub API URL for latest release."""
        return GITHUB_API_URL.format(owner=self._owner, repo=self._repo)

    async def check(self) -> ReleaseInfo | None:
        """Check for a newer release.

        Returns:
            ReleaseInfo if a newer version is available, None otherwise.
        """
        # Placeholder — will implement HTTP fetch in Phase 8
        logger.debug("Update check: current=%s", self._current)
        return None
