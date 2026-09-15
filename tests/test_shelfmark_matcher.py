import os
import unittest

os.environ.setdefault("STACKARR_NO_SCHED", "true")

from stackarr import shelfmark


class ShelfmarkReleaseMatcherTests(unittest.TestCase):
    def setUp(self):
        self._original_source = shelfmark.source
        shelfmark.source = lambda: "prowlarr"

    def tearDown(self):
        shelfmark.source = self._original_source

    @staticmethod
    def release(title: str, fmt: str = "epub", source_id: str = "") -> dict:
        return {
            "title": title,
            "source": "prowlarr",
            "protocol": "nzb",
            "format": fmt,
            "source_id": source_id,
        }

    def test_accept_reject_regressions(self):
        cases = [
            # Real-world genuine candidate from the live 450-result Dune search.
            ("Dune", "Frank Herbert",
             "Masterworks - [SF Masterworks 071] - Dune - Frank Herbert (epub)", True),

            # Real-world false positives exposed by the same search.
            ("Dune", "Frank Herbert",
             "Brian Herbert & Kevin J Anderson - Dune - Legends, Heroes, Schools (epub)", False),
            ("Dune", "Frank Herbert",
             "Brian Herbert &amp; Kevin J Anderson - Dune - Legends, Heroes, Schools (epub)", False),
            ("Dune", "Frank Herbert",
             "Frank Herbert - Dune - Dune Encyclopedia (pdf)", False),

            # Genuine noisy Dune releases.
            ("Dune", "Frank Herbert", "Dune - Frank Herbert - EPUB", True),
            ("Dune", "Frank Herbert", "Frank Herbert - Dune - Retail EPUB", True),
            ("Dune", "Frank Herbert", "Dune.1965.Frank.Herbert.EPUB-GROUP", True),
            ("Dune", "Frank Herbert", "Dune - F Herbert - EPUB", True),
            ("Dune", "Frank Herbert", "Penguin - Dune - Frank Herbert - EPUB - RANDOMGROUP", True),
            ("Dune", "Frank Herbert", "Dune - Ace Books - Frank Herbert - EPUB", True),
            ("Dune", "Frank Herbert", "Dune - 40th Anniversary Edition - Frank Herbert - EPUB", True),
            ("Dune", "Frank Herbert", "Dune - EPUB", True),

            # Different works containing the requested title.
            ("Dune", "Frank Herbert", "Dune Messiah - Frank Herbert - EPUB", False),
            ("Dune", "Frank Herbert", "Dune - Messiah - Frank Herbert - EPUB", False),
            ("Dune", "Frank Herbert", "Children of Dune - Frank Herbert - EPUB", False),
            ("Dune", "Frank Herbert", "The Making of Dune - Frank Herbert - EPUB", False),

            # Other short-title collisions.
            ("Mort", "Terry Pratchett", "Mort - Terry Pratchett - EPUB", True),
            ("Mort", "Terry Pratchett", "Mort Castle - Strangers - EPUB", False),
            ("It", "Stephen King", "It - Stephen King - EPUB - FLT", True),
            ("It", "Stephen King", "It Ends With Us - Colleen Hoover - EPUB", False),

            # Multi-word titles and publisher/edition noise.
            ("The Bell Jar", "Sylvia Plath", "The Bell Jar - Sylvia Plath - EPUB", True),
            ("The Bell Jar", "Sylvia Plath", "The Bell Jar - Penguin Classics - Sylvia Plath - EPUB", True),
            ("The Bell Jar", "Sylvia Plath", "The Bell Jar - A Biography - Sylvia Plath - EPUB", False),
            ("The Stand", "Stephen King", "The Stand Complete and Uncut Edition - Stephen King - EPUB", True),
            ("Ready Player One", "Ernest Cline", "Ready Player One - Ernest Cline - Retail EPUB", True),
            ("A Wrinkle in Time", "Madeleine L Engle", "A Wrinkle in Time - Madeleine L Engle - EPUB", True),

            # Packs and audiobook formats must not masquerade as one ebook.
            ("Dune", "Frank Herbert", "Dune - Frank Herbert - Complete Collection - EPUB", False),
            ("Dune", "Frank Herbert", "Dune - Frank Herbert - MP3", False),
            ("Dune", "Frank Herbert", "Dune - Frank Herbert - M4B", False),
        ]

        for title, author, candidate, expected in cases:
            with self.subTest(candidate=candidate):
                score = shelfmark._score_release(
                    self.release(candidate),
                    title,
                    author,
                )
                accepted = score is not None and score >= 0
                self.assertEqual(expected, accepted, msg=f"score={score!r}")

    def test_real_dune_candidate_set_selects_only_requested_book(self):
        releases = [
            self.release(
                "Masterworks - [SF Masterworks 071] - Dune - Frank Herbert (epub)",
                source_id="good",
            ),
            self.release(
                "Brian Herbert &amp; Kevin J Anderson - Dune - Legends, Heroes, Schools (epub)",
                source_id="wrong-author-html",
            ),
            self.release(
                "Brian Herbert & Kevin J Anderson - Dune - Legends, Heroes, Schools (epub)",
                source_id="wrong-author",
            ),
            self.release(
                "Frank Herbert - Dune - Dune Encyclopedia (pdf)",
                fmt="pdf",
                source_id="encyclopedia-1",
            ),
            self.release(
                "Frank Herbert - Dune - Dune Encyclopedia (pdf)",
                fmt="pdf",
                source_id="encyclopedia-2",
            ),
        ]

        chosen, candidate_count = shelfmark._choose_release(
            releases,
            "Dune",
            "Frank Herbert",
        )

        self.assertIsNotNone(chosen)
        self.assertEqual(1, candidate_count)
        self.assertEqual("good", chosen.get("source_id"))
        self.assertEqual(
            "Masterworks - [SF Masterworks 071] - Dune - Frank Herbert (epub)",
            chosen.get("title"),
        )

    def test_core_safety_filters_still_apply(self):
        wrong_source = self.release("Dune - Frank Herbert - EPUB")
        wrong_source["source"] = "torbox"
        self.assertIsNone(shelfmark._score_release(wrong_source, "Dune", "Frank Herbert"))

        wrong_protocol = self.release("Dune - Frank Herbert - EPUB")
        wrong_protocol["protocol"] = "torrent"
        self.assertIsNone(shelfmark._score_release(wrong_protocol, "Dune", "Frank Herbert"))

        foreign = self.release("Dune - Frank Herbert - French EPUB")
        self.assertIsNone(shelfmark._score_release(foreign, "Dune", "Frank Herbert"))


if __name__ == "__main__":
    unittest.main()
