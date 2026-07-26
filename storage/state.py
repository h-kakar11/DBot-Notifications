"""
Persists the set of MAL ids we've already posted about, so that restarting the
bot doesn't repost entries it already announced.
"""

import json
import logging
from pathlib import Path
from typing import Set

logger = logging.getLogger(__name__)


class SeenEntriesStore:
    """JSON-file backed store of the MAL ids that have already been posted"""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> Set[str]:
        if not self.path.exists():
            return set()
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return {str(entry) for entry in data}
        except (OSError, json.JSONDecodeError) as e:
            logger.error(
                f"Failed to read state file {self.path}, starting from empty state: {e}"
            )
            return set()

    def save(self, seen_ids: Set[str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # write to a temp file and replace, so a crash mid-write can't corrupt
        # the existing state file
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            ordered = sorted(seen_ids, key=int)
        except ValueError:
            ordered = sorted(seen_ids)
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(ordered, f, indent=2)
        tmp_path.replace(self.path)
