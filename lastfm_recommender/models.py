from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

Kind = Literal["artists", "tracks", "albums"]
Mode = Literal["unheard", "forgotten"]


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.casefold().strip().split())


def artist_key(artist: str | None) -> str:
    return normalize_name(artist)


def track_key(artist: str | None, track: str | None) -> tuple[str, str]:
    return (normalize_name(artist), normalize_name(track))


def album_key(artist: str | None, album: str | None) -> tuple[str, str]:
    return (normalize_name(artist), normalize_name(album))


@dataclass
class Recommendation:
    kind: Kind
    title: str
    category: Mode
    score: float
    reason: str
    artist: str | None = None
    album: str | None = None
    url: str | None = None

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["score"] = round(self.score, 4)
        return data
