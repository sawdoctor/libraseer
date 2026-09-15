import os
import unittest

os.environ.setdefault("STACKARR_NO_SCHED", "true")

from stackarr import scheduler


class KavitaAvailabilityMatcherTests(unittest.TestCase):
    def test_real_world_and_collision_regressions(self):
        cases = [
            # Real Kavita rows from the live library.
            (
                "Dune",
                "Frank Herbert",
                "Masterworks - [SF Masterworks 071] - Dune - Frank Herbert",
                True,
            ),
            (
                "Dune",
                "Frank Herbert",
                "Dune Messiah by Frank Herbert EPUB",
                False,
            ),
            (
                "A Wrinkle in Time",
                "Madeleine L Engle",
                "Madeleine L'Engle - [Time 01] - A Wrinkle in Time (Puffin) (retail)",
                True,
            ),

            # Collision protection must remain strict for short titles.
            (
                "Dune",
                "Frank Herbert",
                "Dune (Messiah) (retail) - Frank Herbert",
                False,
            ),
            (
                "Dune",
                "Frank Herbert",
                "Dune - Messiah - Frank Herbert - EPUB",
                False,
            ),
            (
                "Dune",
                "Frank Herbert",
                "Frank Herbert - Dune - Dune Encyclopedia (pdf)",
                False,
            ),
            (
                "The Bell Jar",
                "Sylvia Plath",
                "The Bell Jar (A Biography) - Sylvia Plath",
                False,
            ),

            # Normal publisher / format noise is still accepted.
            (
                "Dune",
                "Frank Herbert",
                "Dune - Ace Books - Frank Herbert - EPUB",
                True,
            ),
            (
                "Dune",
                "Frank Herbert",
                "Dune (epub) - Frank Herbert",
                True,
            ),
        ]

        for title, author, library_title, expected in cases:
            with self.subTest(library_title=library_title):
                self.assertEqual(
                    expected,
                    scheduler._kavita_filename_match(
                        title,
                        author,
                        library_title,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
