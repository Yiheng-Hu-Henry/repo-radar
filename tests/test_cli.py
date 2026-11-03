from __future__ import annotations

import unittest

from reporadar.cli import normalize_repo


class NormalizeRepoTestCase(unittest.TestCase):
    def test_plain(self) -> None:
        self.assertEqual(normalize_repo("owner/repo"), "owner/repo")

    def test_https(self) -> None:
        self.assertEqual(
            normalize_repo("https://github.com/Yiheng-Hu-Henry/clipnest"),
            "Yiheng-Hu-Henry/clipnest",
        )

    def test_with_git_suffix_and_slash(self) -> None:
        self.assertEqual(
            normalize_repo("https://github.com/owner/repo.git/"), "owner/repo"
        )

    def test_ssh(self) -> None:
        self.assertEqual(normalize_repo("git@github.com:owner/repo.git"), "owner/repo")

    def test_whitespace(self) -> None:
        self.assertEqual(normalize_repo("  owner/repo  "), "owner/repo")

    def test_invalid(self) -> None:
        for value in ("just-one-part", "a/b/c", "", "/"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    normalize_repo(value)


if __name__ == "__main__":
    unittest.main()
