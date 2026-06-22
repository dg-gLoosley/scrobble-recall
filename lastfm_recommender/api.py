from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class LastFmError(RuntimeError):
    """Raised when Last.fm cannot return the requested data."""


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text_field(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("#text") or value.get("name") or "")
    if value is None:
        return ""
    return str(value)


def _parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass
class LastFmClient:
    api_key: str
    base_url: str = "https://ws.audioscrobbler.com/2.0/"
    timeout: float = 10.0
    user_agent: str = "lastfm-memory-lane/0.1"

    def request(self, method: str, **params: Any) -> dict[str, Any]:
        query = {
            "method": method,
            "api_key": self.api_key,
            "format": "json",
            **{key: value for key, value in params.items() if value is not None},
        }
        url = f"{self.base_url}?{urlencode(query)}"
        request = Request(url, headers={"User-Agent": self.user_agent})

        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LastFmError(f"HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise LastFmError(f"Network error: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LastFmError("Request timed out") from exc

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise LastFmError("Last.fm returned invalid JSON") from exc

        if "error" in data:
            message = data.get("message", "Unknown Last.fm error")
            raise LastFmError(f"{message} (code {data['error']})")

        return data

    def get_recent_tracks(
        self,
        user: str,
        *,
        limit: int = 200,
        max_pages: int = 3,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> list[dict[str, Any]]:
        tracks: list[dict[str, Any]] = []
        limit = max(1, min(limit, 200))
        max_pages = max(1, max_pages)

        for page in range(1, max_pages + 1):
            data = self.request(
                "user.getRecentTracks",
                user=user,
                limit=limit,
                page=page,
                **{"from": from_ts, "to": to_ts},
            )
            recent = data.get("recenttracks", {})
            for item in _as_list(recent.get("track")):
                if not isinstance(item, dict):
                    continue
                date = item.get("date") if isinstance(item.get("date"), dict) else {}
                attrs = item.get("@attr") if isinstance(item.get("@attr"), dict) else {}
                tracks.append(
                    {
                        "artist": _text_field(item.get("artist")),
                        "track": str(item.get("name") or ""),
                        "album": _text_field(item.get("album")),
                        "url": str(item.get("url") or ""),
                        "played_at": _parse_int(date.get("uts"), 0),
                        "now_playing": attrs.get("nowplaying") == "true",
                    }
                )

            attrs = recent.get("@attr") if isinstance(recent.get("@attr"), dict) else {}
            total_pages = _parse_int(attrs.get("totalPages"), page)
            if page >= total_pages:
                break

        return tracks

    def get_user_top_artists(
        self, user: str, *, period: str = "overall", limit: int = 50
    ) -> list[dict[str, Any]]:
        data = self.request(
            "user.getTopArtists", user=user, period=period, limit=max(1, min(limit, 1000))
        )
        artists = data.get("topartists", {})
        return [self._parse_artist(item, index) for index, item in enumerate(_as_list(artists.get("artist")), 1)]

    def get_user_top_tracks(
        self, user: str, *, period: str = "overall", limit: int = 50
    ) -> list[dict[str, Any]]:
        data = self.request(
            "user.getTopTracks", user=user, period=period, limit=max(1, min(limit, 1000))
        )
        tracks = data.get("toptracks", {})
        return [self._parse_track(item, index) for index, item in enumerate(_as_list(tracks.get("track")), 1)]

    def get_user_top_albums(
        self, user: str, *, period: str = "overall", limit: int = 50
    ) -> list[dict[str, Any]]:
        data = self.request(
            "user.getTopAlbums", user=user, period=period, limit=max(1, min(limit, 1000))
        )
        albums = data.get("topalbums", {})
        return [self._parse_album(item, index) for index, item in enumerate(_as_list(albums.get("album")), 1)]

    def get_similar_artists(self, artist: str, *, limit: int = 10) -> list[dict[str, Any]]:
        data = self.request("artist.getSimilar", artist=artist, limit=max(1, min(limit, 100)))
        artists = data.get("similarartists", {})
        return [self._parse_artist(item, index) for index, item in enumerate(_as_list(artists.get("artist")), 1)]

    def get_artist_top_tracks(self, artist: str, *, limit: int = 10) -> list[dict[str, Any]]:
        data = self.request("artist.getTopTracks", artist=artist, limit=max(1, min(limit, 50)))
        tracks = data.get("toptracks", {})
        parsed = []
        for index, item in enumerate(_as_list(tracks.get("track")), 1):
            parsed_item = self._parse_track(item, index)
            if not parsed_item["artist"]:
                parsed_item["artist"] = artist
            parsed.append(parsed_item)
        return parsed

    def get_artist_top_albums(self, artist: str, *, limit: int = 10) -> list[dict[str, Any]]:
        data = self.request("artist.getTopAlbums", artist=artist, limit=max(1, min(limit, 50)))
        albums = data.get("topalbums", {})
        parsed = []
        for index, item in enumerate(_as_list(albums.get("album")), 1):
            parsed_item = self._parse_album(item, index)
            if not parsed_item["artist"]:
                parsed_item["artist"] = artist
            parsed.append(parsed_item)
        return parsed

    def get_similar_tracks(self, artist: str, track: str, *, limit: int = 10) -> list[dict[str, Any]]:
        data = self.request(
            "track.getSimilar", artist=artist, track=track, limit=max(1, min(limit, 100))
        )
        tracks = data.get("similartracks", {})
        return [self._parse_track(item, index) for index, item in enumerate(_as_list(tracks.get("track")), 1)]

    def get_track_user_playcount(self, user: str, artist: str, track: str) -> int:
        data = self.request(
            "track.getInfo",
            username=user,
            artist=artist,
            track=track,
            autocorrect=1,
        )
        info = data.get("track") if isinstance(data.get("track"), dict) else {}
        stats = info.get("stats") if isinstance(info.get("stats"), dict) else {}
        return _parse_int(info.get("userplaycount") or stats.get("userplaycount"), 0)

    def get_artist_user_playcount(self, user: str, artist: str) -> int:
        data = self.request("artist.getInfo", username=user, artist=artist, autocorrect=1)
        info = data.get("artist") if isinstance(data.get("artist"), dict) else {}
        stats = info.get("stats") if isinstance(info.get("stats"), dict) else {}
        return _parse_int(info.get("userplaycount") or stats.get("userplaycount"), 0)

    def get_album_user_playcount(self, user: str, artist: str, album: str) -> int:
        data = self.request(
            "album.getInfo",
            username=user,
            artist=artist,
            album=album,
            autocorrect=1,
        )
        info = data.get("album") if isinstance(data.get("album"), dict) else {}
        stats = info.get("stats") if isinstance(info.get("stats"), dict) else {}
        return _parse_int(info.get("userplaycount") or stats.get("userplaycount"), 0)

    def _parse_artist(self, item: Any, fallback_rank: int) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {"name": "", "playcount": 0, "rank": fallback_rank, "match": 0.0, "url": ""}
        attrs = item.get("@attr") if isinstance(item.get("@attr"), dict) else {}
        return {
            "name": str(item.get("name") or ""),
            "playcount": _parse_int(item.get("playcount"), 0),
            "rank": _parse_int(attrs.get("rank"), fallback_rank),
            "match": _parse_float(item.get("match"), 0.0),
            "url": str(item.get("url") or ""),
        }

    def _parse_track(self, item: Any, fallback_rank: int) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {
                "track": "",
                "artist": "",
                "playcount": 0,
                "rank": fallback_rank,
                "match": 0.0,
                "url": "",
            }
        attrs = item.get("@attr") if isinstance(item.get("@attr"), dict) else {}
        return {
            "track": str(item.get("name") or ""),
            "artist": _text_field(item.get("artist")),
            "playcount": _parse_int(item.get("playcount"), 0),
            "rank": _parse_int(attrs.get("rank"), fallback_rank),
            "match": _parse_float(item.get("match"), 0.0),
            "url": str(item.get("url") or ""),
        }

    def _parse_album(self, item: Any, fallback_rank: int) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {"album": "", "artist": "", "playcount": 0, "rank": fallback_rank, "url": ""}
        attrs = item.get("@attr") if isinstance(item.get("@attr"), dict) else {}
        return {
            "album": str(item.get("name") or ""),
            "artist": _text_field(item.get("artist")),
            "playcount": _parse_int(item.get("playcount"), 0),
            "rank": _parse_int(attrs.get("rank"), fallback_rank),
            "url": str(item.get("url") or ""),
        }
