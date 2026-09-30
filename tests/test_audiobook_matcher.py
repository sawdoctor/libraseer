import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("STACKARR_NO_SCHED", "true")

from stackarr import audiobridge, catalog_cache


class AudiobookMatcherTests(unittest.TestCase):
    def tearDown(self):
        catalog_cache.clear()

    @staticmethod
    def release(title, author="Rob Grant, Doug Naylor", fmt="m4b", ref="release-1"):
        return {
            "title": title,
            "source": "audiobookbay",
            "protocol": "torrent",
            "format": fmt,
            "content_type": "audiobook",
            "source_id": ref,
            "extra": {"author": author, "title_raw": f"{title} - {author}"},
        }

    def score(self, release, title="Red Dwarf", author="Rob Grant, Doug Naylor", **kwargs):
        return audiobridge._score_release(
            release, title, author, source_name="audiobookbay", **kwargs
        )

    def test_red_dwarf_rejects_other_works_by_the_same_authors(self):
        for title in (
            "Red Dwarf: Series V to VIII",
            "Red Dwarf: Series I to IV: The BBC TV Soundtracks",
            "Red Dwarf: Titan",
            "Red Dwarf: Better Than Life",
            "Red Dwarf - The Complete Collection",
        ):
            with self.subTest(title=title):
                self.assertIsNone(self.score(self.release(title)))

    def test_exact_novel_wins_even_when_wrong_m4b_has_more_author_text(self):
        wrong = self.release("Red Dwarf: Series V to VIII", ref="soundtracks")
        novel = self.release("Red Dwarf", author="Rob Grant", fmt="mp3", ref="novel")
        chosen, count = audiobridge._choose_release(
            [wrong, novel], "Red Dwarf", "Rob Grant, Doug Naylor", source_name="audiobookbay"
        )
        self.assertEqual("novel", chosen["source_id"])
        self.assertEqual(1, count)

    def test_matching_is_whole_title_not_substring_or_shared_surname(self):
        cases = [
            ("It", "Stephen King", "It Ends With Us", "Colleen Hoover"),
            ("Dune", "Frank Herbert", "Dune Messiah", "Frank Herbert"),
            ("Dune", "Frank Herbert", "Dune", "Brian Herbert"),
            ("Mort", "Terry Pratchett", "Immortal", "Terry Pratchett"),
            ("The Martian", "Andy Weir", "The Martian", "Ray Bradbury"),
        ]
        for title, author, candidate, candidate_author in cases:
            with self.subTest(candidate=candidate, author=candidate_author):
                self.assertIsNone(self.score(self.release(candidate, candidate_author), title, author))

    def test_catalogue_subtitle_identifies_the_novel_without_admitting_soundtracks(self):
        subtitle = "Infinity Welcomes Careful Drivers"
        for title in ("Red Dwarf: Infinity Welcomes Careful Drivers", subtitle):
            with self.subTest(title=title):
                self.assertIsNotNone(self.score(self.release(title), subtitle=subtitle))
        self.assertIsNone(self.score(self.release("Red Dwarf: Series V to VIII"), subtitle=subtitle))

    def test_legitimate_metadata_noise_and_single_coauthor_are_supported(self):
        cases = [
            ("Red Dwarf (Unabridged) [M4B]", "Rob Grant"),
            ("Red Dwarf (1989) (64 kbps)", "R. Grant & Doug Naylor"),
            ("Rob Grant - Red Dwarf - MP3", "Rob Grant"),
        ]
        for title, author in cases:
            with self.subTest(title=title):
                self.assertIsNotNone(self.score(self.release(title, author)))

    def test_explicit_soundtracks_can_still_be_requested(self):
        title = "Red Dwarf: Series V to VIII"
        self.assertIsNotNone(self.score(self.release(title), title=title))

    def test_raw_title_cannot_hide_a_different_work(self):
        release = self.release("Red Dwarf")
        release["extra"]["title_raw"] = "Red Dwarf: Titan - Rob Grant"
        self.assertIsNone(self.score(release))

    def test_conflicting_structured_author_and_ebook_format_are_rejected(self):
        release = self.release("Red Dwarf")
        release["extra"]["author"] = "Someone Else"
        self.assertIsNone(self.score(release))
        self.assertIsNone(self.score(self.release("Red Dwarf EPUB", fmt="m4b")))

    def test_request_uses_cached_subtitle_and_makes_one_search_and_one_queue_call(self):
        asin = "B000000001"
        catalog_cache.remember([{
            "asin": asin, "title": "Red Dwarf", "author": "Rob Grant, Doug Naylor",
            "subtitle": "Infinity Welcomes Careful Drivers", "format": "audiobook",
        }])
        wrong = self.release("Red Dwarf: Series V to VIII", ref="soundtracks")
        novel = self.release("Infinity Welcomes Careful Drivers", ref="novel")
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"releases": [wrong, novel]}
        queued = Mock(ok=True, status_code=200)
        queued.json.return_value = {"task_id": "novel"}
        session = Mock()
        session.get.return_value = response
        session.post.return_value = queued
        with patch.object(audiobridge, "_session", return_value=session), patch.object(
            audiobridge, "source", return_value="audiobookbay"
        ), patch.object(audiobridge, "url", return_value="http://shelfmark"), patch(
            "stackarr.audible.by_asin", side_effect=AssertionError("unnecessary catalogue call")
        ):
            result = audiobridge.add_and_search("Red Dwarf", "Rob Grant, Doug Naylor", asin)
        self.assertTrue(result["ok"])
        self.assertEqual("novel", result["ref"])
        session.get.assert_called_once()
        self.assertEqual("false", session.get.call_args.kwargs["params"]["expand_search"])
        session.post.assert_called_once()
        self.assertEqual("novel", session.post.call_args.kwargs["json"]["source_id"])

    def test_wrong_only_results_queue_nothing(self):
        session = Mock()
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"releases": [self.release("Red Dwarf: Titan")]}
        session.get.return_value = response
        with patch.object(audiobridge, "_session", return_value=session), patch.object(
            audiobridge, "source", return_value="audiobookbay"
        ), patch.object(audiobridge, "url", return_value="http://shelfmark"):
            result = audiobridge.add_and_search("Red Dwarf", "Rob Grant, Doug Naylor")
        self.assertFalse(result["ok"])
        session.get.assert_called_once()
        session.post.assert_not_called()

    def test_retry_metadata_uses_one_asin_lookup_and_keeps_audiobook_cache_format(self):
        asin = "B000000001"
        metadata = {"asin": asin, "title": "Red Dwarf", "author": "Rob Grant",
                    "subtitle": "Infinity Welcomes Careful Drivers", "format": "Unabridged"}
        with patch.object(audiobridge.audible, "by_asin", return_value=metadata) as lookup:
            identity = audiobridge._catalog_identity("Red Dwarf", "Rob Grant, Doug Naylor", asin)
            again = audiobridge._catalog_identity("Red Dwarf", "Rob Grant, Doug Naylor", asin)
        lookup.assert_called_once_with(asin)
        self.assertEqual(metadata["subtitle"], identity["subtitle"])
        self.assertEqual(metadata["subtitle"], again["subtitle"])
        self.assertEqual("audiobook", catalog_cache.get_item(asin)["format"])

    def test_conflicting_catalogue_metadata_does_not_add_subtitle_aliases(self):
        for changes in ({"title": "Red Dwarf: Titan"}, {"author": "Someone Else"},
                        {"asin": "B000000002"}):
            with self.subTest(changes=changes):
                catalog_cache.clear()
                metadata = {"asin": "B000000001", "title": "Red Dwarf", "author": "Rob Grant",
                            "subtitle": "Infinity Welcomes Careful Drivers", **changes}
                with patch.object(audiobridge.audible, "by_asin", return_value=metadata):
                    self.assertEqual({}, audiobridge._catalog_identity("Red Dwarf", "Rob Grant", "B000000001"))
                self.assertIsNone(catalog_cache.get_item("B000000001"))

    def test_metadata_lookup_failure_keeps_exact_title_matching_available(self):
        with patch.object(audiobridge.audible, "by_asin", return_value=None):
            self.assertEqual({}, audiobridge._catalog_identity("Red Dwarf", "Rob Grant", "B000000001"))
        self.assertIsNotNone(self.score(self.release("Red Dwarf")))

    def test_invalid_asin_does_not_trigger_catalogue_requests(self):
        with patch.object(audiobridge.audible, "by_asin") as lookup:
            self.assertEqual({}, audiobridge._catalog_identity("Red Dwarf", "Rob Grant", "gb:123"))
        lookup.assert_not_called()

    def test_narrator_metadata_does_not_change_the_work_identity(self):
        novel = self.release("Red Dwarf (Read by Chris Barrie)")
        self.assertIsNotNone(self.score(novel, narrator="Chris Barrie"))
        wrong = self.release("Red Dwarf: Better Than Life (Read by Chris Barrie)")
        self.assertIsNone(self.score(wrong, narrator="Chris Barrie"))

    def test_generic_subtitle_cannot_match_an_unrelated_book(self):
        self.assertIsNone(self.score(self.release("A Novel of Friendship"), subtitle="A Novel of Friendship"))

    def test_numeric_book_title_is_preserved(self):
        self.assertIsNotNone(self.score(self.release("1984 (Unabridged)", "George Orwell"), "1984", "George Orwell"))

    def test_non_english_releases_are_still_rejected(self):
        release = self.release("Red Dwarf")
        release["language"] = "de"
        self.assertIsNone(self.score(release))

    def test_cancelled_status_is_descriptive_without_inventing_a_reason(self):
        with patch.object(audiobridge, "configured", return_value=True), patch.object(
            audiobridge, "_activity", return_value={"task": {"state": "cancelled", "status_message": None}}
        ):
            status = audiobridge.job_status("task")
        self.assertEqual("failed", status["status"])
        self.assertIn("cancelled", status["error"])
        self.assertNotIn("stalled", status["error"])

    def test_actual_download_error_is_preserved(self):
        message = "WebDAV file unavailable"
        with patch.object(audiobridge, "configured", return_value=True), patch.object(
            audiobridge, "_activity", return_value={"task": {"state": "error", "last_error_message": message}}
        ):
            self.assertEqual(message, audiobridge.job_status("task")["error"])


if __name__ == "__main__":
    unittest.main()
