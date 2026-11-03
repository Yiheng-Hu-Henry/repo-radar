from __future__ import annotations

import json
import unittest

from reporadar.render import (
    bar,
    display_width,
    pad,
    render_facts,
    render_json,
    render_markdown,
    render_terminal,
)
from reporadar.score import rate
from tests.factories import make_repo, make_snapshot


class WidthTestCase(unittest.TestCase):
    def test_cjk_counts_double(self) -> None:
        self.assertEqual(display_width("中文"), 4)
        self.assertEqual(display_width("ab"), 2)
        self.assertEqual(display_width("中a"), 3)

    def test_pad_aligns(self) -> None:
        self.assertEqual(pad("中文", 6), "中文  ")
        self.assertEqual(pad("abcdef", 3), "abcdef")

    def test_bar_bounds(self) -> None:
        self.assertEqual(bar(0), "░" * 20)
        self.assertEqual(bar(100), "█" * 20)
        self.assertEqual(len(bar(37)), 20)


class RenderTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = make_snapshot()
        self.rating = rate(self.snapshot)

    def test_terminal_contains_everything(self) -> None:
        text = render_terminal(self.rating, render_facts(self.snapshot.repo, self.snapshot))
        self.assertIn("demo/repo", text)
        self.assertIn(str(self.rating.total), text)
        self.assertIn("建议", text)
        for metric in self.rating.metrics:
            self.assertIn(metric.label, text)

    def test_terminal_lines_are_aligned(self) -> None:
        text = render_terminal(self.rating)
        metric_lines = [line for line in text.splitlines() if "█" in line]
        self.assertTrue(metric_lines)
        # 分数列应落在同一显示列上
        columns = {
            display_width(line[: line.index("█")]) for line in metric_lines
        }
        self.assertEqual(len(columns), 1)

    def test_markdown_table(self) -> None:
        text = render_markdown([self.rating])
        self.assertIn("| 维度 | 分数 | 权重 | 说明 |", text)
        self.assertIn("**改进建议**", text)
        self.assertIn("demo/repo", text)

    def test_json_roundtrip(self) -> None:
        payload = json.loads(render_json([self.rating]))
        self.assertEqual(len(payload["repos"]), 1)
        repo = payload["repos"][0]
        self.assertEqual(repo["repo"], "demo/repo")
        self.assertEqual(len(repo["metrics"]), 6)
        self.assertEqual(repo["grade"], self.rating.grade)

    def test_facts(self) -> None:
        facts = render_facts(self.snapshot.repo, self.snapshot)
        self.assertIn("Python", facts)
        self.assertTrue(any(fact.startswith("★") for fact in facts))

    def test_multiple_repos_in_markdown(self) -> None:
        other = rate(make_snapshot(repo=make_repo(full_name="x/y")))
        text = render_markdown([self.rating, other])
        self.assertEqual(text.count("## "), 2)


if __name__ == "__main__":
    unittest.main()
