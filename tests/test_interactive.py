from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lastfm_recommender import interactive
from lastfm_recommender.models import Recommendation


class FakeClient:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key


class FakeEngine:
    last_call: tuple[str, dict[str, object]] | None = None

    def __init__(self, client: FakeClient) -> None:
        self.client = client
        self.warnings: list[str] = []

    def recommend(self, username: str, **kwargs: object) -> list[Recommendation]:
        self.__class__.last_call = (username, kwargs)
        return [
            Recommendation(
                kind="tracks",
                title="Prompted Song",
                artist="Prompted Artist",
                category="unheard",
                score=1.0,
                reason="test",
            )
        ]


class InteractiveTests(unittest.TestCase):
    def test_prompted_run_uses_answers_without_network(self):
        answers = iter(["test-api-key", "n", "listener", "", "", "", "2", "n", "n"])

        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(interactive, "LastFmClient", FakeClient):
                    with patch.object(interactive, "RecommendationEngine", FakeEngine):
                        with patch.object(interactive, "print_table", lambda recommendations: None):
                            result = interactive.run(
                                Path(directory),
                                input_func=lambda prompt: next(answers),
                                print_func=lambda *args, **kwargs: None,
                            )

        self.assertEqual(result, 0)
        self.assertEqual(FakeEngine.last_call[0], "listener")
        self.assertEqual(
            FakeEngine.last_call[1],
            {
                "kind": "tracks",
                "limit": 2,
                "mode": "both",
                "period": "overall",
                "verify_new": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
