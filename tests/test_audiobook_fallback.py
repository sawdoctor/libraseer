import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("STACKARR_NO_SCHED", "true")

from stackarr import audiobridge


class AudiobookFallbackTests(unittest.TestCase):
    @staticmethod
    def release(source="audiobookbay", protocol="torrent"):
        return {
            "title": "Project Hail Mary - Andy Weir - M4B",
            "source": source,
            "protocol": protocol,
            "format": "m4b",
            "content_type": "audiobook",
            "source_id": "release-1",
        }

    def test_primary_accepts_torrent_and_rejects_nzb(self):
        with patch.object(audiobridge, "source", return_value="audiobookbay"):
            self.assertIsNotNone(audiobridge._score_release(
                self.release(), "Project Hail Mary", "Andy Weir"
            ))
            self.assertIsNone(audiobridge._score_release(
                self.release(protocol="nzb"), "Project Hail Mary", "Andy Weir"
            ))

    def test_explicit_prowlarr_fallback_accepts_only_nzb(self):
        self.assertIsNotNone(audiobridge._score_release(
            self.release(source="prowlarr", protocol="nzb"),
            "Project Hail Mary",
            "Andy Weir",
            source_name="prowlarr",
        ))
        self.assertIsNone(audiobridge._score_release(
            self.release(source="prowlarr", protocol="torrent"),
            "Project Hail Mary",
            "Andy Weir",
            source_name="prowlarr",
        ))

    def test_fallback_search_is_single_source_and_never_auto_expands(self):
        response = Mock()
        response.status_code = 200
        response.ok = True
        response.json.return_value = {"releases": []}
        session = Mock()
        session.get.return_value = response

        with patch.object(audiobridge, "url", return_value="http://shelfmark"):
            audiobridge._search_once(
                session,
                "Project Hail Mary",
                "Andy Weir",
                source_name="prowlarr",
            )

        params = session.get.call_args.kwargs["params"]
        self.assertEqual("prowlarr", params["source"])
        self.assertEqual("false", params["expand_search"])
        self.assertEqual("audiobook", params["content_type"])


if __name__ == "__main__":
    unittest.main()
