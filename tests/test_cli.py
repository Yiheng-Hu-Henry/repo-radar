from __future__ import annotations

import unittest
from unittest import mock

from reporadar.cli import force_utf8_stdio, normalize_repo


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


class ForceUtf8StdioTestCase(unittest.TestCase):
    """Windows 上 stdout 被重定向时会用 ANSI 代码页，★ 和中文会炸。"""

    def test_reconfigures_both_streams(self) -> None:
        fake_out = mock.MagicMock()
        fake_err = mock.MagicMock()
        with mock.patch("sys.stdout", fake_out), mock.patch("sys.stderr", fake_err):
            force_utf8_stdio()

        for stream in (fake_out, fake_err):
            stream.reconfigure.assert_called_once()
            kwargs = stream.reconfigure.call_args.kwargs
            self.assertEqual(kwargs["encoding"], "utf-8")
            self.assertEqual(kwargs["errors"], "replace")

    def test_stream_without_reconfigure_is_ignored(self) -> None:
        # 有些包装流（如 pytest 的 capture）没有 reconfigure，不能因此崩掉。
        with mock.patch("sys.stdout", object()):
            force_utf8_stdio()

    def test_only_utf8_can_encode_the_report_glyphs(self) -> None:
        # 用真实的 ANSI 代码页编码会抛异常，这正是不修就失败的原因。
        text = "★ 报告 ██████ 满分"
        with self.assertRaises(UnicodeEncodeError):
            text.encode("cp1252")
        self.assertEqual(text.encode("utf-8").decode("utf-8"), text)


if __name__ == "__main__":
    unittest.main()
