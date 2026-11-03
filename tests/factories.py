from __future__ import annotations

from datetime import datetime, timedelta, timezone

from reporadar.models import (
    IssueStats,
    ReadmeInfo,
    ReleaseInfo,
    RepoInfo,
    Snapshot,
)

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=timezone.utc)


def make_repo(**overrides) -> RepoInfo:
    base = dict(
        full_name="demo/repo",
        description="一个用来演示的仓库",
        stars=42,
        forks=5,
        watchers=3,
        open_issues_count=3,
        language="Python",
        license_name="MIT",
        topics=("cli", "tooling"),
        created_at=NOW - timedelta(days=400),
        pushed_at=NOW - timedelta(days=2),
        archived=False,
        size_kb=512,
        homepage=None,
    )
    base.update(overrides)
    return RepoInfo(**base)


def make_snapshot(**overrides) -> Snapshot:
    defaults = dict(
        repo=make_repo(),
        issues=IssueStats(
            open_issues=3,
            closed_issues=17,
            open_pulls=1,
            closed_pulls=9,
            median_close_days=1.5,
            median_pull_days=2.0,
        ),
        release=ReleaseInfo(tag="v0.1.0", published_at=NOW - timedelta(days=10)),
        readme=ReadmeInfo(present=True, chars=4000),
        commits_90d=12,
        commits_30d=4,
        last_commit_at=NOW - timedelta(days=2),
        now=NOW,
    )
    defaults.update(overrides)
    return Snapshot(**defaults)
