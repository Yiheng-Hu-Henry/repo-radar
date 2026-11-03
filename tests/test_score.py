from __future__ import annotations

import unittest
from datetime import timedelta

from reporadar.models import IssueStats, ReadmeInfo, ReleaseInfo
from reporadar.score import (
    WEIGHTS,
    grade_of,
    rate,
    score_activity,
    score_community,
    score_docs,
    score_issues,
    score_pulls,
    score_release,
)
from tests.factories import NOW, make_repo, make_snapshot


class ActivityTestCase(unittest.TestCase):
    def test_today_is_full_score(self) -> None:
        snapshot = make_snapshot(last_commit_at=NOW, commits_90d=8)
        score, detail = score_activity(snapshot)
        self.assertEqual(score, 100)
        self.assertIn("今天", detail)

    def test_old_repo_decays(self) -> None:
        snapshot = make_snapshot(last_commit_at=NOW - timedelta(days=200), commits_90d=0)
        score, _ = score_activity(snapshot)
        self.assertLess(score, 60)

    def test_very_old(self) -> None:
        # 很久没提交 + 近 90 天零提交，两层惩罚叠加
        snapshot = make_snapshot(last_commit_at=NOW - timedelta(days=800), commits_90d=0)
        score, _ = score_activity(snapshot)
        self.assertEqual(score, 2)

    def test_no_commits(self) -> None:
        snapshot = make_snapshot(last_commit_at=None, commits_90d=0)
        score, detail = score_activity(snapshot)
        self.assertEqual(score, 10)
        self.assertIn("没有", detail)


class CommunityTestCase(unittest.TestCase):
    def test_zero_stars(self) -> None:
        score, detail = score_community(make_snapshot(repo=make_repo(stars=0)))
        self.assertEqual(score, 5)
        self.assertIn("star", detail)

    def test_monotonic(self) -> None:
        scores = [
            score_community(make_snapshot(repo=make_repo(stars=value)))[0]
            for value in (1, 10, 100, 1000, 10000)
        ]
        self.assertEqual(scores, sorted(scores))
        self.assertGreater(scores[-1], 90)


class IssuesTestCase(unittest.TestCase):
    def test_no_issue_is_neutral(self) -> None:
        snapshot = make_snapshot(issues=IssueStats())
        score, detail = score_issues(snapshot)
        self.assertEqual(score, 60)
        self.assertIn("还没有", detail)

    def test_high_close_ratio_scores_high(self) -> None:
        snapshot = make_snapshot(
            issues=IssueStats(open_issues=1, closed_issues=49, median_close_days=1.0)
        )
        score, _ = score_issues(snapshot)
        self.assertGreaterEqual(score, 95)

    def test_low_close_ratio_scores_low(self) -> None:
        snapshot = make_snapshot(
            issues=IssueStats(open_issues=80, closed_issues=5, median_close_days=200.0)
        )
        score, _ = score_issues(snapshot)
        self.assertLess(score, 40)

    def test_backlog_penalty(self) -> None:
        base = make_snapshot(issues=IssueStats(open_issues=3, closed_issues=7))
        backlogged = make_snapshot(issues=IssueStats(open_issues=80, closed_issues=7))
        self.assertLess(score_issues(backlogged)[0], score_issues(base)[0])


class DocsTestCase(unittest.TestCase):
    def test_complete_docs(self) -> None:
        score, detail = score_docs(make_snapshot())
        self.assertGreaterEqual(score, 90)
        self.assertIn("齐全", detail)

    def test_missing_everything(self) -> None:
        snapshot = make_snapshot(
            repo=make_repo(description=None, license_name=None, topics=()),
            readme=ReadmeInfo(present=False),
        )
        score, detail = score_docs(snapshot)
        self.assertEqual(score, 0)
        for word in ("README", "LICENSE", "topics"):
            self.assertIn(word, detail)

    def test_short_readme_flagged(self) -> None:
        snapshot = make_snapshot(readme=ReadmeInfo(present=True, chars=100))
        score, detail = score_docs(snapshot)
        self.assertLess(score, 90)
        self.assertIn("更完整", detail)


class ReleaseTestCase(unittest.TestCase):
    def test_no_release(self) -> None:
        score, _ = score_release(make_snapshot(release=ReleaseInfo()))
        self.assertEqual(score, 25)

    def test_recent_release(self) -> None:
        score, detail = score_release(make_snapshot())
        self.assertEqual(score, 100)
        self.assertIn("v0.1.0", detail)

    def test_stale_release(self) -> None:
        snapshot = make_snapshot(
            release=ReleaseInfo(tag="v0.0.1", published_at=NOW - timedelta(days=500))
        )
        self.assertEqual(score_release(snapshot)[0], 40)


class PullsTestCase(unittest.TestCase):
    def test_no_pulls(self) -> None:
        score, _ = score_pulls(make_snapshot(issues=IssueStats()))
        self.assertEqual(score, 60)

    def test_fast_merge(self) -> None:
        snapshot = make_snapshot(
            issues=IssueStats(closed_pulls=10, median_pull_days=1.0)
        )
        self.assertEqual(score_pulls(snapshot)[0], 100)

    def test_slow_merge(self) -> None:
        snapshot = make_snapshot(
            issues=IssueStats(closed_pulls=10, median_pull_days=90.0)
        )
        self.assertLess(score_pulls(snapshot)[0], 50)

    def test_open_pulls_only(self) -> None:
        snapshot = make_snapshot(issues=IssueStats(open_pulls=4))
        score, detail = score_pulls(snapshot)
        self.assertEqual(score, 55)
        self.assertIn("4", detail)


class GradeTestCase(unittest.TestCase):
    def test_cutoffs(self) -> None:
        self.assertEqual(grade_of(100), "A")
        self.assertEqual(grade_of(85), "A")
        self.assertEqual(grade_of(84), "B")
        self.assertEqual(grade_of(70), "B")
        self.assertEqual(grade_of(55), "C")
        self.assertEqual(grade_of(40), "D")
        self.assertEqual(grade_of(0), "E")


class RateTestCase(unittest.TestCase):
    def test_weights_sum_to_one(self) -> None:
        self.assertAlmostEqual(sum(WEIGHTS.values()), 1.0, places=6)

    def test_total_matches_weighted_sum(self) -> None:
        rating = rate(make_snapshot())
        expected = round(sum(metric.score * metric.weight for metric in rating.metrics))
        self.assertEqual(rating.total, expected)
        self.assertEqual(len(rating.metrics), 6)

    def test_bounds(self) -> None:
        healthy = rate(make_snapshot())
        self.assertGreater(healthy.total, 60)

        dead = rate(
            make_snapshot(
                repo=make_repo(
                    stars=0,
                    description=None,
                    license_name=None,
                    topics=(),
                    pushed_at=NOW - timedelta(days=900),
                ),
                issues=IssueStats(open_issues=40, closed_issues=2, median_close_days=300.0),
                release=ReleaseInfo(),
                readme=ReadmeInfo(present=False),
                commits_90d=0,
                commits_30d=0,
                last_commit_at=NOW - timedelta(days=900),
            )
        )
        self.assertLess(dead.total, healthy.total)
        self.assertIn(dead.grade, ("D", "E"))

    def test_advice_is_actionable(self) -> None:
        rating = rate(
            make_snapshot(
                repo=make_repo(description=None, license_name=None, topics=()),
                readme=ReadmeInfo(present=False),
            )
        )
        text = " ".join(rating.advice)
        self.assertIn("README", text)

    def test_advice_mentions_archived(self) -> None:
        rating = rate(make_snapshot(repo=make_repo(archived=True)))
        self.assertTrue(any("归档" in item for item in rating.advice))

    def test_advice_capped(self) -> None:
        rating = rate(
            make_snapshot(
                repo=make_repo(stars=0, description=None, license_name=None, topics=()),
                issues=IssueStats(open_issues=90, closed_issues=1, median_close_days=400.0),
                release=ReleaseInfo(),
                readme=ReadmeInfo(present=False),
                last_commit_at=NOW - timedelta(days=700),
                commits_90d=0,
            )
        )
        self.assertLessEqual(len(rating.advice), 4)


if __name__ == "__main__":
    unittest.main()
