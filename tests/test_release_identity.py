import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("STACKARR_NO_SCHED", "true")

from stackarr import audiobridge, catalog_cache, ebookmeta, shelfmark
from stackarr.book_identity import _author_matches


class ReleaseIdentityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads((Path(__file__).parent / "fixtures" / "red_dwarf_releases.json").read_text())

    def tearDown(self):
        catalog_cache.clear()

    def test_real_audiobook_results_select_only_the_novel(self):
        releases = copy.deepcopy(self.fixture["audiobook"])
        chosen, count = audiobridge._choose_release(
            releases, "Red Dwarf", "Rob Grant, Doug Naylor", "audiobookbay",
            subtitle=self.fixture["metadata"]["subtitle"], narrator="Chris Barrie")
        self.assertEqual(1, count)
        self.assertEqual("Red Dwarf: Infinity Welcomes Careful Drivers", chosen["title"])
        self.assertEqual("Grant Naylor", chosen["extra"]["author"])

    def test_real_ebook_results_select_only_epub_copies_of_the_novel(self):
        with patch.object(shelfmark, "source", return_value="prowlarr"):
            accepted = [r for r in self.fixture["ebook"] if shelfmark._score_release(
                r, "Red Dwarf", "Rob Grant, Doug Naylor",
                subtitle=self.fixture["metadata"]["subtitle"]) is not None]
        self.assertEqual(3, len(accepted))
        self.assertEqual({"epub"}, {shelfmark._release_format(r) for r in accepted})
        self.assertEqual({"Red Dwarf 01 - Infinity Welcomes Careful Drivers - Grant Naylor (epub)",
                          "Red.Dwarf.01.-.Infinity.Welcomes.Careful.Drivers.-.Grant.Naylor.epub"},
                         {r["title"] for r in accepted})

    def test_verified_joint_alias_is_not_a_shared_surname_heuristic(self):
        self.assertTrue(_author_matches("Rob Grant, Doug Naylor", "Grant Naylor"))
        self.assertTrue(_author_matches("Grant Naylor", "Rob Grant and Doug Naylor"))
        self.assertFalse(_author_matches("Rob Grant", "Grant Naylor"))
        self.assertFalse(_author_matches("Brian Herbert, Kevin Anderson", "Herbert Anderson"))
        self.assertFalse(_author_matches("Frank Herbert", "Brian Herbert"))

    def test_joint_alias_never_authorizes_another_work(self):
        for title in ("Red Dwarf: Better Than Life", "Red Dwarf: Series V to VIII"):
            release = copy.deepcopy(self.fixture["audiobook"][5])
            release["title"] = title
            release["extra"]["title_raw"] = title + " - Grant Naylor"
            self.assertIsNone(audiobridge._score_release(
                release, "Red Dwarf", "Rob Grant, Doug Naylor", "audiobookbay",
                subtitle=self.fixture["metadata"]["subtitle"]))

    def test_ebook_subtitle_still_requires_author_format_protocol_and_exact_work(self):
        good = copy.deepcopy(self.fixture["ebook"][15])
        changes = [
            {"title": "Red Dwarf 02 - Better Than Life - Grant Naylor (epub)"},
            {"title": "Red Dwarf 01 - Infinity Welcomes Careful Drivers - Grant Naylor (mobi)"},
            {"title": "Red Dwarf 01 - Infinity Welcomes Careful Drivers - Grant Naylor (html)"},
            {"title": "Red Dwarf 01 - Infinity Welcomes Careful Drivers - Someone Else (epub)"},
            {"title": "Red Dwarf 01 - Infinity Welcomes Careful Drivers - Complete Collection - Grant Naylor (epub)"},
            {"protocol": "torrent"}, {"source": "audiobookbay"}, {"language": "es"},
            {"extra": {"author": "Someone Else"}},
        ]
        with patch.object(shelfmark, "source", return_value="prowlarr"):
            self.assertIsNotNone(shelfmark._score_release(
                good, "Red Dwarf", "Rob Grant, Doug Naylor", subtitle=self.fixture["metadata"]["subtitle"]))
            for change in changes:
                with self.subTest(change=change):
                    self.assertIsNone(shelfmark._score_release(
                        dict(good, **change), "Red Dwarf", "Rob Grant, Doug Naylor",
                        subtitle=self.fixture["metadata"]["subtitle"]))
            self.assertIsNone(shelfmark._score_release(good, "Red Dwarf", "Rob Grant, Doug Naylor"))

    def test_ebook_handoff_uses_validated_subtitle_and_one_search_one_queue(self):
        asin = "B000000001"
        catalog_cache.remember([dict(self.fixture["metadata"], asin=asin, format="audiobook")])
        response = Mock(ok=True, status_code=200)
        response.json.return_value = {"releases": self.fixture["ebook"]}
        queued = Mock(ok=True, status_code=200)
        queued.json.return_value = {"task_id": "ebook-task"}
        session = Mock()
        session.get.return_value = response
        session.post.return_value = queued
        with patch.object(shelfmark, "_session", return_value=session), patch.object(
            shelfmark, "source", return_value="prowlarr"
        ), patch.object(shelfmark, "url", return_value="http://shelfmark"), patch.object(
            audiobridge.audible, "by_asin", side_effect=AssertionError("metadata is cached")
        ):
            result = shelfmark.add_and_search("Red Dwarf", "Rob Grant, Doug Naylor", asin)
        self.assertTrue(result["ok"], result)
        session.get.assert_called_once()
        self.assertEqual("false", session.get.call_args.kwargs["params"]["expand_search"])
        session.post.assert_called_once()
        selected = session.post.call_args.kwargs["json"]
        self.assertIn("Infinity", selected["title"])
        self.assertEqual("epub", shelfmark._release_format(selected))
        self.assertEqual("audiobook", catalog_cache.get_item(asin)["format"])

    def test_ebook_id_lookup_requires_identity_title_and_author_agreement(self):
        book_id = "gb:example"
        metadata = dict(self.fixture["metadata"], id=book_id, asin="", format="ebook")
        with patch.object(ebookmeta, "by_id", return_value=metadata) as lookup:
            self.assertEqual(metadata["subtitle"], audiobridge._catalog_identity(
                "Red Dwarf", "Rob Grant, Doug Naylor", book_id, ebook=True)["subtitle"])
            audiobridge._catalog_identity("Red Dwarf", "Rob Grant, Doug Naylor", book_id, ebook=True)
        lookup.assert_called_once_with(book_id)
        self.assertEqual("ebook", catalog_cache.get_item(book_id)["format"])
        for change in ({"id": "gb:other"}, {"title": "Red Dwarf: Titan"}, {"author": "Someone Else"}):
            catalog_cache.clear()
            with patch.object(ebookmeta, "by_id", return_value=dict(metadata, **change)):
                self.assertEqual({}, audiobridge._catalog_identity(
                    "Red Dwarf", "Rob Grant, Doug Naylor", book_id, ebook=True))

    def test_ebook_lookup_failure_keeps_existing_exact_title_behavior(self):
        with patch.object(ebookmeta, "by_id", return_value=None):
            self.assertEqual({}, audiobridge._catalog_identity("Dune", "Frank Herbert", "gb:example", ebook=True))
        with patch.object(shelfmark, "source", return_value="prowlarr"):
            self.assertIsNotNone(shelfmark._score_release(
                {"title": "Dune - Frank Herbert - EPUB", "source": "prowlarr", "protocol": "nzb"},
                "Dune", "Frank Herbert"))

    def test_ebook_retry_excludes_failed_alias_releases(self):
        releases = self.fixture["ebook"]
        excluded = {r["title"] for r in releases if "Infinity" in r["title"]}
        with patch.object(shelfmark, "source", return_value="prowlarr"):
            chosen, count = shelfmark._choose_release(
                releases, "Red Dwarf", "Rob Grant, Doug Naylor", excluded_titles=excluded,
                subtitle=self.fixture["metadata"]["subtitle"])
        self.assertIsNone(chosen)
        self.assertEqual(0, count)


if __name__ == "__main__":
    unittest.main()
