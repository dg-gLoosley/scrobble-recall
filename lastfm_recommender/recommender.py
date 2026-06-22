from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable

from .api import LastFmClient, LastFmError
from .models import (
    Kind,
    Recommendation,
    album_key,
    artist_key,
    normalize_name,
    track_key,
)


@dataclass
class ListeningProfile:
    recent_tracks_raw: list[dict[str, Any]]
    top_artists: list[dict[str, Any]]
    top_tracks: list[dict[str, Any]]
    top_albums: list[dict[str, Any]]
    recent_artists: set[str]
    recent_tracks: set[tuple[str, str]]
    recent_albums: set[tuple[str, str]]
    known_artists: set[str]
    known_tracks: set[tuple[str, str]]
    known_albums: set[tuple[str, str]]
    recent_artist_counts: Counter[str]


@dataclass(frozen=True)
class ArtistSeed:
    name: str
    weight: float
    reason: str


class RecommendationEngine:
    def __init__(self, client: LastFmClient) -> None:
        self.client = client
        self.warnings: list[str] = []

    def build_profile(
        self,
        user: str,
        *,
        period: str = "overall",
        top_limit: int = 300,
        known_limit: int = 1000,
        history_limit: int = 200,
        history_pages: int = 3,
        from_ts: int | None = None,
        to_ts: int | None = None,
    ) -> ListeningProfile:
        recent_tracks = self.client.get_recent_tracks(
            user,
            limit=history_limit,
            max_pages=history_pages,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        top_limit = max(1, top_limit)
        known_limit = max(top_limit, known_limit)
        if period == "overall":
            all_top_artists = self.client.get_user_top_artists(user, period=period, limit=known_limit)
            all_top_tracks = self.client.get_user_top_tracks(user, period=period, limit=known_limit)
            all_top_albums = self.client.get_user_top_albums(user, period=period, limit=known_limit)
            top_artists = all_top_artists[:top_limit]
            top_tracks = all_top_tracks[:top_limit]
            top_albums = all_top_albums[:top_limit]
        else:
            top_artists = self.client.get_user_top_artists(user, period=period, limit=top_limit)
            top_tracks = self.client.get_user_top_tracks(user, period=period, limit=top_limit)
            top_albums = self.client.get_user_top_albums(user, period=period, limit=top_limit)
            all_top_artists = self.client.get_user_top_artists(user, period="overall", limit=known_limit)
            all_top_tracks = self.client.get_user_top_tracks(user, period="overall", limit=known_limit)
            all_top_albums = self.client.get_user_top_albums(user, period="overall", limit=known_limit)

        recent_artists = {
            artist_key(item.get("artist")) for item in recent_tracks if artist_key(item.get("artist"))
        }
        recent_track_keys = {
            track_key(item.get("artist"), item.get("track"))
            for item in recent_tracks
            if all(track_key(item.get("artist"), item.get("track")))
        }
        recent_album_keys = {
            album_key(item.get("artist"), item.get("album"))
            for item in recent_tracks
            if all(album_key(item.get("artist"), item.get("album")))
        }
        recent_artist_counts = Counter(
            artist_key(item.get("artist")) for item in recent_tracks if artist_key(item.get("artist"))
        )

        top_artist_keys = {
            artist_key(item.get("name")) for item in all_top_artists if artist_key(item.get("name"))
        }
        top_track_keys = {
            track_key(item.get("artist"), item.get("track"))
            for item in all_top_tracks
            if all(track_key(item.get("artist"), item.get("track")))
        }
        top_album_keys = {
            album_key(item.get("artist"), item.get("album"))
            for item in all_top_albums
            if all(album_key(item.get("artist"), item.get("album")))
        }

        return ListeningProfile(
            recent_tracks_raw=recent_tracks,
            top_artists=top_artists,
            top_tracks=top_tracks,
            top_albums=top_albums,
            recent_artists=recent_artists,
            recent_tracks=recent_track_keys,
            recent_albums=recent_album_keys,
            known_artists=recent_artists | top_artist_keys,
            known_tracks=recent_track_keys | top_track_keys,
            known_albums=recent_album_keys | top_album_keys,
            recent_artist_counts=recent_artist_counts,
        )

    def recommend(
        self,
        user: str,
        *,
        kind: Kind = "tracks",
        limit: int = 25,
        mode: str = "both",
        period: str = "overall",
        top_limit: int = 300,
        known_limit: int = 1000,
        history_limit: int = 200,
        history_pages: int = 5,
        from_ts: int | None = None,
        to_ts: int | None = None,
        seed_limit: int = 16,
        similar_per_artist: int = 2,
        candidates_per_artist: int = 15,
        max_per_artist: int | None = 3,
        similar_track_seeds: int = 0,
        forgotten_skip_top: int = 25,
        candidate_skip_top: int = 3,
        verify_new: bool = True,
        verify_pool_multiplier: int = 5,
    ) -> list[Recommendation]:
        self.warnings.clear()
        profile = self.build_profile(
            user,
            period=period,
            top_limit=top_limit,
            known_limit=known_limit,
            history_limit=history_limit,
            history_pages=history_pages,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        include_unheard = mode in {"both", "unheard"}
        include_forgotten = mode in {"both", "forgotten"}
        per_category_limit = mode == "both"
        search_limit = limit
        if include_unheard and verify_new:
            search_limit = max(limit, limit * max(1, verify_pool_multiplier))

        if kind == "artists":
            recommendations = self.recommend_artists(
                profile,
                limit=search_limit,
                include_unheard=include_unheard,
                include_forgotten=include_forgotten,
                seed_limit=seed_limit,
                similar_per_artist=similar_per_artist,
                forgotten_skip_top=forgotten_skip_top,
                per_category_limit=per_category_limit,
            )
        elif kind == "albums":
            recommendations = self.recommend_albums(
                profile,
                limit=search_limit,
                include_unheard=include_unheard,
                include_forgotten=include_forgotten,
                seed_limit=seed_limit,
                similar_per_artist=similar_per_artist,
                candidates_per_artist=candidates_per_artist,
                max_per_artist=max_per_artist,
                forgotten_skip_top=forgotten_skip_top,
                candidate_skip_top=candidate_skip_top,
                per_category_limit=per_category_limit,
            )
        else:
            recommendations = self.recommend_tracks(
                profile,
                limit=search_limit,
                include_unheard=include_unheard,
                include_forgotten=include_forgotten,
                seed_limit=seed_limit,
                similar_per_artist=similar_per_artist,
                candidates_per_artist=candidates_per_artist,
                max_per_artist=max_per_artist,
                similar_track_seeds=similar_track_seeds,
                forgotten_skip_top=forgotten_skip_top,
                candidate_skip_top=candidate_skip_top,
                per_category_limit=per_category_limit,
            )

        if verify_new:
            recommendations = self._filter_played_unheard(user, recommendations, kind)

        return _select_recommendations(
            recommendations,
            limit,
            max_per_artist=max_per_artist,
            per_category_limit=per_category_limit,
        )

    def recommend_artists(
        self,
        profile: ListeningProfile,
        *,
        limit: int,
        include_unheard: bool,
        include_forgotten: bool,
        seed_limit: int,
        similar_per_artist: int,
        forgotten_skip_top: int = 25,
        per_category_limit: bool = False,
    ) -> list[Recommendation]:
        candidates: dict[str, Recommendation] = {}

        if include_forgotten:
            for index, artist in enumerate(profile.top_artists, 1):
                if index <= forgotten_skip_top:
                    continue
                name = str(artist.get("name") or "")
                key = artist_key(name)
                if not key or key in profile.recent_artists:
                    continue
                score = 1.8 + _rank_weight(index, len(profile.top_artists)) + _playcount_weight(artist)
                self._add_candidate(
                    candidates,
                    key,
                    Recommendation(
                        kind="artists",
                        title=name,
                        artist=name,
                        category="forgotten",
                        score=score,
                        reason="A past favorite that was not in the recent scrobbles checked.",
                        url=str(artist.get("url") or ""),
                    ),
                )

        if include_unheard:
            for seed in self._seed_artists(profile, seed_limit):
                similar = self._call(
                    f"similar artists for {seed.name}",
                    self.client.get_similar_artists,
                    seed.name,
                    limit=similar_per_artist,
                )
                for artist in similar:
                    name = str(artist.get("name") or "")
                    key = artist_key(name)
                    if not key or key in profile.known_artists:
                        continue
                    match = float(artist.get("match") or 0.0)
                    score = 0.45 + (seed.weight * 0.45) + (max(match, 0.1) * 0.4)
                    self._add_candidate(
                        candidates,
                        key,
                        Recommendation(
                            kind="artists",
                            title=name,
                            artist=name,
                            category="unheard",
                            score=score,
                            reason=f"Found through listeners of {seed.name}, but not in the fetched history.",
                            url=str(artist.get("url") or ""),
                        ),
                    )

        return _top_recommendations(candidates, limit, per_category_limit=per_category_limit)

    def recommend_tracks(
        self,
        profile: ListeningProfile,
        *,
        limit: int,
        include_unheard: bool,
        include_forgotten: bool,
        seed_limit: int,
        similar_per_artist: int,
        candidates_per_artist: int,
        max_per_artist: int | None = None,
        similar_track_seeds: int = 0,
        forgotten_skip_top: int = 25,
        candidate_skip_top: int = 3,
        per_category_limit: bool = False,
    ) -> list[Recommendation]:
        candidates: dict[tuple[str, str], Recommendation] = {}

        if include_forgotten:
            for index, track in enumerate(profile.top_tracks, 1):
                if index <= forgotten_skip_top:
                    continue
                artist = str(track.get("artist") or "")
                title = str(track.get("track") or "")
                key = track_key(artist, title)
                if not all(key) or key in profile.recent_tracks:
                    continue
                score = 1.9 + _rank_weight(index, len(profile.top_tracks)) + _playcount_weight(track)
                self._add_candidate(
                    candidates,
                    key,
                    Recommendation(
                        kind="tracks",
                        title=title,
                        artist=artist,
                        category="forgotten",
                        score=score,
                        reason="A top track that did not appear in the recent scrobbles checked.",
                        url=str(track.get("url") or ""),
                    ),
                )

        if include_unheard:
            for artist in self._candidate_artist_pool(profile, seed_limit, similar_per_artist):
                top_tracks = self._call(
                    f"top tracks for {artist.name}",
                    self.client.get_artist_top_tracks,
                    artist.name,
                    limit=candidates_per_artist,
                )
                for index, track in enumerate(top_tracks, 1):
                    if index <= candidate_skip_top:
                        continue
                    track_artist = str(track.get("artist") or artist.name)
                    title = str(track.get("track") or "")
                    key = track_key(track_artist, title)
                    if not all(key) or key in profile.known_tracks:
                        continue
                    novelty = 0.25 if artist_key(track_artist) not in profile.known_artists else 0.0
                    score = artist.weight + _rank_weight(index, len(top_tracks)) + novelty
                    self._add_candidate(
                        candidates,
                        key,
                        Recommendation(
                            kind="tracks",
                            title=title,
                            artist=track_artist,
                            category="unheard",
                            score=score,
                            reason=artist.reason,
                            url=str(track.get("url") or ""),
                        ),
                    )

            for seed_track in profile.top_tracks[:similar_track_seeds]:
                seed_artist = str(seed_track.get("artist") or "")
                seed_title = str(seed_track.get("track") or "")
                if not seed_artist or not seed_title:
                    continue
                similar_tracks = self._call(
                    f"similar tracks for {seed_artist} - {seed_title}",
                    self.client.get_similar_tracks,
                    seed_artist,
                    seed_title,
                    limit=candidates_per_artist,
                )
                for index, track in enumerate(similar_tracks, 1):
                    artist = str(track.get("artist") or "")
                    title = str(track.get("track") or "")
                    key = track_key(artist, title)
                    if not all(key) or key in profile.known_tracks:
                        continue
                    match = float(track.get("match") or 0.0)
                    score = 0.9 + _rank_weight(index, len(similar_tracks)) + max(match, 0.1)
                    self._add_candidate(
                        candidates,
                        key,
                        Recommendation(
                            kind="tracks",
                            title=title,
                            artist=artist,
                            category="unheard",
                            score=score,
                            reason=f"Similar to {seed_artist} - {seed_title}.",
                            url=str(track.get("url") or ""),
                        ),
                    )

        return _top_recommendations(
            candidates,
            limit,
            max_per_artist=max_per_artist,
            per_category_limit=per_category_limit,
        )

    def recommend_albums(
        self,
        profile: ListeningProfile,
        *,
        limit: int,
        include_unheard: bool,
        include_forgotten: bool,
        seed_limit: int,
        similar_per_artist: int,
        candidates_per_artist: int,
        max_per_artist: int | None = None,
        forgotten_skip_top: int = 25,
        candidate_skip_top: int = 3,
        per_category_limit: bool = False,
    ) -> list[Recommendation]:
        candidates: dict[tuple[str, str], Recommendation] = {}

        if include_forgotten:
            for index, album in enumerate(profile.top_albums, 1):
                if index <= forgotten_skip_top:
                    continue
                artist = str(album.get("artist") or "")
                title = str(album.get("album") or "")
                key = album_key(artist, title)
                if not all(key) or key in profile.recent_albums:
                    continue
                score = 1.9 + _rank_weight(index, len(profile.top_albums)) + _playcount_weight(album)
                self._add_candidate(
                    candidates,
                    key,
                    Recommendation(
                        kind="albums",
                        title=title,
                        artist=artist,
                        album=title,
                        category="forgotten",
                        score=score,
                        reason="A top album that did not appear in the recent scrobbles checked.",
                        url=str(album.get("url") or ""),
                    ),
                )

        if include_unheard:
            for artist in self._candidate_artist_pool(profile, seed_limit, similar_per_artist):
                albums = self._call(
                    f"top albums for {artist.name}",
                    self.client.get_artist_top_albums,
                    artist.name,
                    limit=candidates_per_artist,
                )
                for index, album in enumerate(albums, 1):
                    if index <= candidate_skip_top:
                        continue
                    album_artist = str(album.get("artist") or artist.name)
                    title = str(album.get("album") or "")
                    key = album_key(album_artist, title)
                    if not all(key) or key in profile.known_albums:
                        continue
                    novelty = 0.25 if artist_key(album_artist) not in profile.known_artists else 0.0
                    score = artist.weight + _rank_weight(index, len(albums)) + novelty
                    self._add_candidate(
                        candidates,
                        key,
                        Recommendation(
                            kind="albums",
                            title=title,
                            artist=album_artist,
                            album=title,
                            category="unheard",
                            score=score,
                            reason=artist.reason,
                            url=str(album.get("url") or ""),
                        ),
                    )

        return _top_recommendations(
            candidates,
            limit,
            max_per_artist=max_per_artist,
            per_category_limit=per_category_limit,
        )

    def _seed_artists(self, profile: ListeningProfile, limit: int) -> list[ArtistSeed]:
        seeds: dict[str, ArtistSeed] = {}
        total = max(len(profile.top_artists), 1)

        for index, artist in enumerate(profile.top_artists[: limit * 2], 1):
            name = str(artist.get("name") or "")
            key = artist_key(name)
            if not key:
                continue
            weight = 0.9 + _rank_weight(index, total)
            seeds[key] = ArtistSeed(name=name, weight=weight, reason=f"Based on your history with {name}.")

        for key, count in profile.recent_artist_counts.most_common(limit * 2):
            if not key:
                continue
            display_name = _display_artist_name(profile, key)
            weight = 0.65 + min(math.log1p(count) / 3.0, 0.8)
            current = seeds.get(key)
            if current is None or weight > current.weight:
                seeds[key] = ArtistSeed(
                    name=display_name,
                    weight=weight,
                    reason=f"Based on recent plays of {display_name}.",
                )

        return sorted(seeds.values(), key=lambda seed: seed.weight, reverse=True)[:limit]

    def _candidate_artist_pool(
        self, profile: ListeningProfile, seed_limit: int, similar_per_artist: int
    ) -> list[ArtistSeed]:
        pool: dict[str, ArtistSeed] = {}

        for seed in self._seed_artists(profile, seed_limit):
            key = artist_key(seed.name)
            pool[key] = seed
            similar = self._call(
                f"similar artists for {seed.name}",
                self.client.get_similar_artists,
                seed.name,
                limit=similar_per_artist,
            )
            for artist in similar:
                name = str(artist.get("name") or "")
                sim_key = artist_key(name)
                if not sim_key:
                    continue
                match = float(artist.get("match") or 0.0)
                weight = 0.45 + (seed.weight * 0.35) + (max(match, 0.1) * 0.35)
                candidate = ArtistSeed(
                    name=name,
                    weight=weight,
                    reason=f"Found through listeners of {seed.name}.",
                )
                current = pool.get(sim_key)
                if current is None or candidate.weight > current.weight:
                    pool[sim_key] = candidate

        return sorted(pool.values(), key=lambda seed: seed.weight, reverse=True)

    def _filter_played_unheard(
        self,
        user: str,
        recommendations: list[Recommendation],
        kind: Kind,
    ) -> list[Recommendation]:
        filtered: list[Recommendation] = []

        for item in recommendations:
            if item.category != "unheard":
                filtered.append(item)
                continue

            playcount = self._user_playcount(user, item, kind)
            if playcount is None:
                filtered.append(item)
                continue
            if playcount > 0:
                continue

            if "No plays found" not in item.reason:
                item.reason = f"{item.reason} No plays found in your Last.fm history."
            filtered.append(item)

        return filtered

    def _user_playcount(self, user: str, item: Recommendation, kind: Kind) -> int | None:
        try:
            if kind == "tracks":
                if not item.artist or not item.title:
                    return None
                return self.client.get_track_user_playcount(user, item.artist, item.title)
            if kind == "albums":
                if not item.artist or not item.title:
                    return None
                return self.client.get_album_user_playcount(user, item.artist, item.title)
            if not item.artist:
                return None
            return self.client.get_artist_user_playcount(user, item.artist)
        except LastFmError as exc:
            self.warnings.append(f"Could not verify whether {item.title} was already played: {exc}")
            return None

    def _call(self, label: str, func: Callable[..., list[dict[str, Any]]], *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        try:
            return func(*args, **kwargs)
        except LastFmError as exc:
            self.warnings.append(f"Skipped {label}: {exc}")
            return []

    @staticmethod
    def _add_candidate(
        candidates: dict[Any, Recommendation],
        key: Any,
        candidate: Recommendation,
    ) -> None:
        existing = candidates.get(key)
        if existing is None or candidate.score > existing.score:
            candidates[key] = candidate
            return
        if candidate.reason and candidate.reason not in existing.reason:
            existing.reason = f"{existing.reason} Also: {candidate.reason}"
            existing.score = max(existing.score, candidate.score)


def _rank_weight(index: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return max(0.0, (total - index + 1) / total)


def _playcount_weight(item: dict[str, Any]) -> float:
    playcount = int(item.get("playcount") or 0)
    if playcount <= 0:
        return 0.0
    return min(math.log1p(playcount) / 6.0, 1.2)


def _display_artist_name(profile: ListeningProfile, normalized_key: str) -> str:
    for item in profile.recent_tracks_raw:
        artist = str(item.get("artist") or "")
        if normalize_name(artist) == normalized_key:
            return artist
    for item in profile.top_artists:
        artist = str(item.get("name") or "")
        if normalize_name(artist) == normalized_key:
            return artist
    return normalized_key


def _top_recommendations(
    candidates: dict[Any, Recommendation],
    limit: int,
    *,
    max_per_artist: int | None = None,
    per_category_limit: bool = False,
) -> list[Recommendation]:
    sorted_items = sorted(
        candidates.values(),
        key=lambda item: (item.score, item.category == "forgotten", item.title.casefold()),
        reverse=True,
    )
    return _select_recommendations(
        sorted_items,
        limit,
        max_per_artist=max_per_artist,
        per_category_limit=per_category_limit,
    )


def _select_recommendations(
    recommendations: list[Recommendation],
    limit: int,
    *,
    max_per_artist: int | None = None,
    per_category_limit: bool = False,
) -> list[Recommendation]:
    limit = max(limit, 0)
    if not per_category_limit:
        return _select_with_artist_cap(recommendations, limit, max_per_artist=max_per_artist)

    forgotten = [item for item in recommendations if item.category == "forgotten"]
    unheard = [item for item in recommendations if item.category == "unheard"]
    return _select_with_artist_cap(
        forgotten,
        limit,
        max_per_artist=max_per_artist,
    ) + _select_with_artist_cap(
        unheard,
        limit,
        max_per_artist=max_per_artist,
    )


def _select_with_artist_cap(
    recommendations: list[Recommendation],
    limit: int,
    *,
    max_per_artist: int | None = None,
) -> list[Recommendation]:
    if max_per_artist is None or max_per_artist < 1:
        return recommendations[:limit]

    picked: list[Recommendation] = []
    overflow: list[Recommendation] = []
    artist_counts: Counter[str] = Counter()

    for item in recommendations:
        key = artist_key(item.artist)
        if key and artist_counts[key] >= max_per_artist:
            overflow.append(item)
            continue
        picked.append(item)
        if key:
            artist_counts[key] += 1
        if len(picked) >= limit:
            return picked

    for item in overflow:
        picked.append(item)
        if len(picked) >= limit:
            break

    return picked
