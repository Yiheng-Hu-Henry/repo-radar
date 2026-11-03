"""数据模型：把 GitHub 的原始 JSON 收敛成一组不可变对象。

所有指标计算都只依赖这里的结构，不再碰网络，因此可以离线测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Tuple


def parse_time(value: Optional[str]) -> Optional[datetime]:
    """解析 GitHub 的 ISO 8601 时间（形如 ``2026-10-22T18:56:00Z``）。"""
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class RepoInfo:
    full_name: str
    description: Optional[str] = None
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    open_issues_count: int = 0
    language: Optional[str] = None
    license_name: Optional[str] = None
    topics: Tuple[str, ...] = ()
    created_at: Optional[datetime] = None
    pushed_at: Optional[datetime] = None
    archived: bool = False
    size_kb: int = 0
    homepage: Optional[str] = None


@dataclass(frozen=True)
class IssueStats:
    """issues 端点同时返回 issue 和 PR，需要分开统计。"""

    open_issues: int = 0
    closed_issues: int = 0
    open_pulls: int = 0
    closed_pulls: int = 0
    median_close_days: Optional[float] = None
    median_pull_days: Optional[float] = None

    @property
    def total_issues(self) -> int:
        return self.open_issues + self.closed_issues

    @property
    def closed_ratio(self) -> Optional[float]:
        if self.total_issues == 0:
            return None
        return self.closed_issues / self.total_issues


@dataclass(frozen=True)
class ReleaseInfo:
    tag: Optional[str] = None
    published_at: Optional[datetime] = None


@dataclass(frozen=True)
class ReadmeInfo:
    present: bool = False
    chars: int = 0


@dataclass(frozen=True)
class Snapshot:
    """一次体检采集到的全部事实。"""

    repo: RepoInfo
    issues: IssueStats = field(default_factory=IssueStats)
    release: ReleaseInfo = field(default_factory=ReleaseInfo)
    readme: ReadmeInfo = field(default_factory=ReadmeInfo)
    commits_90d: int = 0
    commits_30d: int = 0
    last_commit_at: Optional[datetime] = None
    now: Optional[datetime] = None

    @property
    def reference_time(self) -> datetime:
        return self.now or datetime.now(timezone.utc)

    def days_since(self, moment: Optional[datetime]) -> Optional[float]:
        if moment is None:
            return None
        delta = self.reference_time - moment
        return delta.total_seconds() / 86400.0
