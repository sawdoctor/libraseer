import unittest
from unittest.mock import patch

from stackarr import catalog_cache


class CatalogCacheTests(unittest.TestCase):
    def setUp(self):
        catalog_cache.clear()

    def tearDown(self):
        catalog_cache.clear()

    def test_query_results_are_copied_and_reused(self):
        books = [{
            "asin": "B001",
            "title": "Dune",
            "author": "Frank Herbert",
            "format": "audiobook",
        }]
        catalog_cache.set_query("dune", ["audiobook"], 12, books)
        cached = catalog_cache.get_query("DUNE", ["audiobook"], 12)
        self.assertEqual(books, cached)
        cached[0]["title"] = "changed"
        self.assertEqual("Dune", catalog_cache.get_query("dune", ["audiobook"], 12)[0]["title"])

    def test_suggestions_respect_active_format(self):
        catalog_cache.remember([
            {"asin": "A1", "title": "Dune", "author": "Frank Herbert", "format": "audiobook"},
            {"asin": "E1", "title": "Dune", "author": "Frank Herbert", "format": "ebook"},
        ])
        results = catalog_cache.suggest("frank dune", ["ebook"])
        self.assertEqual(["E1"], [item["asin"] for item in results])

    def test_expired_entries_are_not_returned(self):
        with patch.object(catalog_cache.time, "monotonic", return_value=10):
            catalog_cache.set_query("dune", ["ebook"], 12, [{"asin": "E1"}])
        with patch.object(catalog_cache.time, "monotonic", return_value=10 + catalog_cache.QUERY_TTL + 1):
            self.assertIsNone(catalog_cache.get_query("dune", ["ebook"], 12))


if __name__ == "__main__":
    unittest.main()
