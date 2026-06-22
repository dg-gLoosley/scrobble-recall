from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from lastfm_recommender.models import Recommendation, normalize_name
from lastfm_recommender.recommender import RecommendationEngine, _top_recommendations
from lastfm_recommender.utils import save_recommendations


class FakeClient:
    def get_recent_tracks(self, user, **kwargs):
        return [
            {"artist": "Newer Artist", "track": "Current Song", "album": "Current Album"},
            {"artist": "Known Artist", "track": "Known Song", "album": "Known Album"},
        ]

    def get_user_top_artists(self, user, **kwargs):
        return [
            {"name": "Old Favorite", "playcount": 100, "url": "https://example.test/old"},
            {"name": "Known Artist", "playcount": 80, "url": "https://example.test/known"},
        ]

    def get_user_top_tracks(self, user, **kwargs):
        return [
            {
                "artist": "Old Favorite",
                "track": "Old Song",
                "playcount": 50,
                "url": "https://example.test/old-song",
            },
            {
                "artist": "Known Artist",
                "track": "Known Song",
                "playcount": 30,
                "url": "https://example.test/known-song",
            },
            {
                "artist": "Deep Favorite",
                "track": "Deep Song",
                "playcount": 20,
                "url": "https://example.test/deep-song",
            },
        ]

    def get_user_top_albums(self, user, **kwargs):
        return [
            {
                "artist": "Old Favorite",
                "album": "Old Album",
                "playcount": 25,
                "url": "https://example.test/old-album",
            }
        ]

    def get_similar_artists(self, artist, **kwargs):
        return [
            {"name": "Fresh Artist", "match": 0.9, "url": "https://example.test/fresh"},
            {"name": "Known Artist", "match": 0.8, "url": "https://example.test/known"},
        ]

    def get_artist_top_tracks(self, artist, **kwargs):
        if artist == "Fresh Artist":
            return [
                {
                    "artist": "Fresh Artist",
                    "track": "Fresh Song",
                    "playcount": 0,
                    "url": "https://example.test/fresh-song",
                },
                {
                    "artist": "Fresh Artist",
                    "track": "Fresh Unknown",
                    "playcount": 0,
                    "url": "https://example.test/fresh-unknown",
                },
            ]
        return [
            {
                "artist": artist,
                "track": "New Seed Song",
                "playcount": 0,
                "url": "https://example.test/new-seed-song",
            }
        ]

    def get_track_user_playcount(self, user, artist, track):
        if (artist, track) == ("Fresh Artist", "Fresh Song"):
            return 1
        return 0

    def get_album_user_playcount(self, user, artist, album):
        return 0

    def get_artist_user_playcount(self, user, artist):
        return 0

    def get_artist_top_albums(self, artist, **kwargs):
        if artist == "Fresh Artist":
            return [
                {
                    "artist": "Fresh Artist",
                    "album": "Fresh Album",
                    "playcount": 0,
                    "url": "https://example.test/fresh-album",
                }
            ]
        return []

    def get_similar_tracks(self, artist, track, **kwargs):
        return [
            {
                "artist": "Fresh Artist",
                "track": "Similar Song",
                "match": 0.75,
                "url": "https://example.test/similar-song",
            }
        ]


class RecommenderTests(unittest.TestCase):
    def test_normalizes_names(self):
        self.assertEqual(normalize_name("  The   Knife "), "the knife")

    def test_artist_recommendations_include_forgotten_and_unheard(self):
        engine = RecommendationEngine(FakeClient())
        profile = engine.build_profile("listener")

        results = engine.recommend_artists(
            profile,
            limit=10,
            include_unheard=True,
            include_forgotten=True,
            seed_limit=2,
            similar_per_artist=2,
            forgotten_skip_top=0,
        )

        labels = {(item.category, item.artist) for item in results}
        self.assertIn(("forgotten", "Old Favorite"), labels)
        self.assertIn(("unheard", "Fresh Artist"), labels)
        self.assertNotIn(("unheard", "Known Artist"), labels)

    def test_track_recommendations_skip_similar_tracks_by_default(self):
        engine = RecommendationEngine(FakeClient())
        profile = engine.build_profile("listener")

        results = engine.recommend_tracks(
            profile,
            limit=10,
            include_unheard=True,
            include_forgotten=True,
            seed_limit=2,
            similar_per_artist=1,
            candidates_per_artist=2,
            forgotten_skip_top=0,
            candidate_skip_top=0,
        )

        labels = {(item.category, item.artist, item.title) for item in results}
        self.assertIn(("forgotten", "Old Favorite", "Old Song"), labels)
        self.assertIn(("unheard", "Fresh Artist", "Fresh Song"), labels)
        self.assertNotIn(("unheard", "Fresh Artist", "Similar Song"), labels)
        self.assertNotIn(("unheard", "Known Artist", "Known Song"), labels)

    def test_track_recommendations_can_opt_into_similar_tracks(self):
        engine = RecommendationEngine(FakeClient())
        profile = engine.build_profile("listener")

        results = engine.recommend_tracks(
            profile,
            limit=10,
            include_unheard=True,
            include_forgotten=True,
            seed_limit=2,
            similar_per_artist=1,
            candidates_per_artist=2,
            similar_track_seeds=2,
            forgotten_skip_top=0,
            candidate_skip_top=0,
        )

        labels = {(item.category, item.artist, item.title) for item in results}
        self.assertIn(("unheard", "Fresh Artist", "Similar Song"), labels)

    def test_album_recommendations_include_forgotten_and_unheard(self):
        engine = RecommendationEngine(FakeClient())
        profile = engine.build_profile("listener")

        results = engine.recommend_albums(
            profile,
            limit=10,
            include_unheard=True,
            include_forgotten=True,
            seed_limit=2,
            similar_per_artist=1,
            candidates_per_artist=2,
            forgotten_skip_top=0,
            candidate_skip_top=0,
        )

        labels = {(item.category, item.artist, item.title) for item in results}
        self.assertIn(("forgotten", "Old Favorite", "Old Album"), labels)
        self.assertIn(("unheard", "Fresh Artist", "Fresh Album"), labels)

    def test_high_level_limit_is_per_category_when_mode_is_both(self):
        engine = RecommendationEngine(FakeClient())

        results = engine.recommend(
            "listener",
            kind="tracks",
            mode="both",
            limit=1,
            seed_limit=2,
            similar_per_artist=1,
            candidates_per_artist=2,
            forgotten_skip_top=0,
            candidate_skip_top=0,
            verify_new=False,
        )

        self.assertEqual(len(results), 2)
        self.assertEqual([item.category for item in results], ["forgotten", "unheard"])

    def test_high_level_new_tracks_are_verified_against_user_playcount(self):
        engine = RecommendationEngine(FakeClient())

        results = engine.recommend(
            "listener",
            kind="tracks",
            mode="unheard",
            limit=5,
            seed_limit=2,
            similar_per_artist=1,
            candidates_per_artist=2,
            forgotten_skip_top=0,
            candidate_skip_top=0,
            verify_new=True,
        )

        labels = {(item.artist, item.title) for item in results}
        self.assertNotIn(("Fresh Artist", "Fresh Song"), labels)
        self.assertIn(("Fresh Artist", "Fresh Unknown"), labels)

    def test_forgotten_skip_top_avoids_most_obvious_favorites(self):
        engine = RecommendationEngine(FakeClient())
        profile = engine.build_profile("listener")

        results = engine.recommend_tracks(
            profile,
            limit=10,
            include_unheard=False,
            include_forgotten=True,
            seed_limit=2,
            similar_per_artist=1,
            candidates_per_artist=2,
            forgotten_skip_top=1,
            candidate_skip_top=0,
        )

        labels = {(item.artist, item.title) for item in results}
        self.assertNotIn(("Old Favorite", "Old Song"), labels)
        self.assertIn(("Deep Favorite", "Deep Song"), labels)

    def test_top_recommendations_can_limit_artist_repetition(self):
        candidates = {
            "a": Recommendation(
                kind="tracks",
                title="First",
                artist="Same Artist",
                category="unheard",
                score=10,
                reason="test",
            ),
            "b": Recommendation(
                kind="tracks",
                title="Second",
                artist="Same Artist",
                category="unheard",
                score=9,
                reason="test",
            ),
            "c": Recommendation(
                kind="tracks",
                title="Other",
                artist="Other Artist",
                category="unheard",
                score=5,
                reason="test",
            ),
        }

        results = _top_recommendations(candidates, limit=2, max_per_artist=1)

        self.assertEqual([item.title for item in results], ["First", "Other"])

    def test_save_recommendations_writes_csv_and_json(self):
        recommendations = [
            Recommendation(
                kind="tracks",
                title="Export Song",
                artist="Export Artist",
                category="unheard",
                score=1.2345,
                reason="test export",
                url="https://example.test/export",
            )
        ]

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            csv_path = folder / "recommendations.csv"
            json_path = folder / "recommendations.json"

            save_recommendations(recommendations, csv_path)
            save_recommendations(recommendations, json_path)

            self.assertIn("Export Song", csv_path.read_text(encoding="utf-8"))
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload[0]["title"], "Export Song")


if __name__ == "__main__":
    unittest.main()
