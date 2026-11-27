"""Per-session editing history. Frames live on disk, never in RAM."""
import os

import config
from utils import image_utils


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


class EditHistory:
    """original_path is never deleted until the whole session folder is removed."""

    def __init__(self, directory: str, original_path: str, max_frames: int = None):
        self.directory = directory
        self.original_path = original_path
        self.max_frames = max_frames or config.MAX_HISTORY_FRAMES
        self._frames: list = []  # oldest -> newest
        self._counter = 0

    @property
    def current_path(self) -> str:
        return self._frames[-1] if self._frames else self.original_path

    @property
    def frame_count(self) -> int:
        return len(self._frames)

    @property
    def can_undo(self) -> bool:
        return bool(self._frames)

    def push(self, img) -> str:
        """Save a new frame; drop the oldest one if the limit is exceeded."""
        self._counter += 1
        path = os.path.join(self.directory, f"frame_{self._counter}{image_utils.frame_extension(img)}")
        image_utils.save_image(img, path)
        self._frames.append(path)
        while len(self._frames) > self.max_frames:
            _remove(self._frames.pop(0))
        return path

    def undo(self) -> bool:
        if not self._frames:
            return False
        _remove(self._frames.pop())
        return True

    def reset(self) -> None:
        self.clear()

    def clear(self) -> None:
        for path in self._frames:
            _remove(path)
        self._frames.clear()
