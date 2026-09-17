"""Only UI preferences are persisted. No application keys, paths or traffic."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile


@dataclass(frozen=True, slots=True)
class UiPreferences:
    mode: str = "micro"
    micro_position: tuple[int, int] | None = None
    compact_position: tuple[int, int] | None = None
    micro_on_top: bool = False

    @classmethod
    def from_mapping(cls, data: object) -> UiPreferences:
        if not isinstance(data, dict) or data.get("version", 1) != 1:
            return cls()
        def position(key: str) -> tuple[int, int] | None:
            value = data.get(key)
            if (isinstance(value, (list, tuple)) and len(value) == 2
                    and all(type(v) is int and abs(v) <= 1_000_000 for v in value)):
                return value[0], value[1]
            return None
        return cls(
            mode=data.get("mode") if data.get("mode") in ("micro", "compact") else "micro",
            micro_position=position("micro_position"),
            compact_position=position("compact_position"),
            micro_on_top=data.get("micro_on_top") is True,
        )


class PreferencesStore:
    def __init__(self, path: Path | None = None) -> None:
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".config")
        self.path = path or root / "NetMonitor" / "ui.json"

    def load(self) -> UiPreferences:
        try:
            # Bound reads even when a malformed file has been placed here.
            with self.path.open("r", encoding="utf-8") as stream:
                text = stream.read(8193)
            return UiPreferences.from_mapping(json.loads(text)) if len(text) <= 8192 else UiPreferences()
        except (OSError, ValueError, TypeError, RecursionError):
            return UiPreferences()

    def save(self, preferences: UiPreferences) -> bool:
        temporary: str | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"version": 1, **asdict(preferences)}
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix="ui-", suffix=".tmp", delete=False) as stream:
                temporary = stream.name
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            return True
        except (OSError, ValueError):
            return False
        finally:
            if temporary is not None:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
