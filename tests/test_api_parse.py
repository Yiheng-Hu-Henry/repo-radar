from __future__ import annotations

import unittest
from datetime import timedelta, timezone

from reporadar.api import build_issue_stats, build_snapshot, repo_from_json
from reporadar.models import ReadmeInfo, ReleaseInfo, parse_time
from tests.factories import NOW, make_repo


class ParseTimeTestCase(unittest.TestCase):
    def test_z_suffix(self) -> None:
        parsed = parse_time("2026-10-22T18:56:00Z")
        assert parsed is not None
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.tzinfo, timezone.utc)

    def test_offset(self) -> None:
        parsed = parse_time("2026-10-22T18:56:00+08:00")
        assert parsed is not None
        self.assertEqual(parsed.hour, 10)

    def test_invalid(self) -> None:
        self.assertIsNone(parse_time("not a date"))
        self.assertIsNone(parse_time(None))
        self.assertIsNone(parse_time(""))


class RepoFromJsonTestCase(unittest.TestCase):
    def test_fields(self) -> None:
        info = repo_from_json(
            {
                "full_name": "a/b",
                "description": "desc",
                "stargazers_count": 7,
                "forks_count": 2,
                "subscribers_count": 1,
                "open_issues_count": 4,
                "language": "Go",
                "license": {"spdx_id": "Apache-2.0"},
                "topics": ["x"],
                "created_at": "2025-01-01T00:00:00Z",
                "pushed_at": "2026-01-01T00:00:00Z",
                "archived": True,
                "size": 99,
            }
        )
        self.assertEqual(info.full_name, "a/b")
        self.assertEqual(info.stars, 7)
        self.assertEqual(info.license_name, "Apache-2.0")
        self.assertEqual(info.topics, ("x",))
        self.assertTrue(info.archived)

    def test_missing_fields(self) -> None:
        info = repo_from_json({"full_name": "a/b"})
        self.assertEqual(info.stars, 0)
        self.assertIsNone(info.license_name)
        self.assertEqual(info.topics, ())


class IssueStatsTestCase(unittest.TestCase):
    def test_separates_issues_and_pulls(self) -> None:
        items = [
            {"state": "open", "created_at": "2026-01-01T00:00:00Z"},
            {
                "state": "closed",
                "created_at": "2026-01-01T00:00:00Z",
                "closed_at": "2026-01-03T00:00:00Z",
            },
            {"state": "open", "pull_request": {"url": "x"}},
            {
                "state": "closed",
                "pull_request": {"url": "x"},
                "created_at": "2026-01-01T00:00:00Z",
                "closed_at": "2026-01-02T00:00:00Z",
            },
        ]
        stats = build_issue_stats(items)
        self.assertEqual(stats.open_issues, 1)
        self.assertEqual(stats.closed_issues, 1)
        self.assertEqual(stats.open_pulls, 1)
        self.assertEqual(stats.closed_pulls, 1)
        self.assertAlmostEqual(stats.median_close_days or 0, 2.0, places=2)
        self.assertAlmostEqual(stats.median_pull_days or 0, 1.0, places=2)

    def test_empty(self) -> None:
        stats = build_issue_stats([])
        self.assertEqual(stats.total_issues, 0)
        self.assertIsNone(stats.closed_ratio)
        self.assertIsNone(stats.median_close_days)

    def test_closed_ratio(self) -> None:
        stats = build_issue_stats(
            [{"state": "closed"}, {"state": "closed"}, {"state": "open"}]
        )
        self.assertAlmostEqual(stats.closed_ratio or 0, 2 / 3)


class BuildSnapshotTestCase(unittest.TestCase):
    def test_counts_commits_by_window(self) -> None:
        def commit(days_ago: int) -> dict:
            stamp = (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
            return {"commit": {"author": {"date": stamp}}}

        commits = [commit(1), commit(10), commit(40), commit(80)]
        snapshot = build_snapshot(
            make_repo(),
            commits,
            [],
            ReleaseInfo(),
            ReadmeInfo(),
            now=NOW,
        )
        self.assertEqual(snapshot.commits_90d, 4)
        self.assertEqual(snapshot.commits_30d, 2)
        assert snapshot.last_commit_at is not None
        self.assertLess(snapshot.days_since(snapshot.last_commit_at) or 99, 2)

    def test_falls_back_to_pushed_at(self) -> None:
        repo = make_repo(pushed_at=NOW - timedelta(days=5))
        snapshot = build_snapshot(repo, [], [], ReleaseInfo(), ReadmeInfo(), now=NOW)
        self.assertEqual(snapshot.last_commit_at, repo.pushed_at)
        self.assertAlmostEqual(snapshot.days_since(snapshot.last_commit_at) or 0, 5.0)


if __name__ == "__main__":
    unittest.main()
