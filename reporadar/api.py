"""GitHub REST API 封装。

只用 ``urllib``，不引第三方库。四个端点拼出一份完整的 `Snapshot`：

    /repos/{full_name}
    /repos/{full_name}/commits
    /repos/{full_name}/issues
    /repos/{full_name}/releases
    /repos/{full_name}/readme

未认证时 GitHub 限流是每小时 60 次，一次体检要 5 次请求，所以最多查 12 个
仓库就会被卡住。带上 token 后上限是 5000 次/小时。
"""

from __future__ import annotations

import json
import os
import statistics
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    IssueStats,
    ReadmeInfo,
    ReleaseInfo,
    RepoInfo,
    Snapshot,
    parse_time,
)

API_ROOT = "https://api.github.com"
DEFAULT_TIMEOUT = 20.0


class GitHubError(RuntimeError):
    """调用 GitHub 失败。"""


class NotFound(GitHubError):
    """仓库或资源不存在。"""


class RateLimited(GitHubError):
    """触发了 API 限流。"""


class GitHubClient:
    def __init__(
        self,
        token: Optional[str] = None,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        api_root: str = API_ROOT,
    ) -> None:
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        self.timeout = timeout
        self.api_root = api_root.rstrip("/")
        self.rate_limit_remaining: Optional[int] = None

    # ------------------------------------------------------------------ 基础

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repo-radar",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get(
        self, path: str, params: Optional[Dict[str, Any]] = None
    ) -> Tuple[Any, Dict[str, str]]:
        """GET 一个 API 路径，返回 ``(数据, 响应头)``。"""
        url = f"{self.api_root}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers=self._headers())
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8") or "null")
                self.rate_limit_remaining = _int_header(
                    response.headers.get("X-RateLimit-Remaining")
                )
                return payload, dict(response.headers)
        except urllib.error.HTTPError as error:
            remaining = error.headers.get("X-RateLimit-Remaining") if error.headers else None
            if remaining == "0":
                raise RateLimited(
                    "GitHub API 已限流。设置 GITHUB_TOKEN 可以把上限从 60 次/小时提到 5000 次。"
                ) from error
            if error.code == 404:
                raise NotFound(f"找不到资源：{path}") from error
            if error.code in (403, 429):
                raise RateLimited(f"请求被拒绝（HTTP {error.code}）：{path}") from error
            raise GitHubError(f"HTTP {error.code} {error.reason}：{path}") from error
        except urllib.error.URLError as error:
            raise GitHubError(f"网络异常：{error.reason}") from error

    # ------------------------------------------------------------------ 采集

    def fetch_repo(self, full_name: str) -> RepoInfo:
        data, _ = self.get(f"/repos/{full_name}")
        if not isinstance(data, dict):
            raise GitHubError(f"返回格式异常：{full_name}")
        return repo_from_json(data)

    def fetch_commits(self, full_name: str, days: int = 90) -> List[Dict[str, Any]]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        data, _ = self.get(
            f"/repos/{full_name}/commits", {"since": since, "per_page": 100}
        )
        return data if isinstance(data, list) else []

    def fetch_issues(self, full_name: str, pages: int = 2) -> List[Dict[str, Any]]:
        """拉最近若干页 issue（含 PR），足够算比例与中位关闭时长。"""
        collected: List[Dict[str, Any]] = []
        for page in range(1, pages + 1):
            data, _ = self.get(
                f"/repos/{full_name}/issues",
                {"state": "all", "per_page": 100, "page": page, "sort": "updated"},
            )
            if not isinstance(data, list) or not data:
                break
            collected.extend(data)
            if len(data) < 100:
                break
        return collected

    def fetch_release(self, full_name: str) -> ReleaseInfo:
        try:
            data, _ = self.get(f"/repos/{full_name}/releases", {"per_page": 1})
        except NotFound:
            return ReleaseInfo()
        if not isinstance(data, list) or not data:
            return ReleaseInfo()
        latest = data[0]
        return ReleaseInfo(
            tag=latest.get("tag_name"),
            published_at=parse_time(latest.get("published_at") or latest.get("created_at")),
        )

    def fetch_readme(self, full_name: str) -> ReadmeInfo:
        try:
            data, _ = self.get(f"/repos/{full_name}/readme")
        except NotFound:
            return ReadmeInfo(present=False)
        if not isinstance(data, dict):
            return ReadmeInfo(present=False)
        size = data.get("size")
        # size 是字节数；GitHub 对超过 1MB 的文件不返回内容，退化成用 size 估算
        if isinstance(size, int) and size > 0:
            return ReadmeInfo(present=True, chars=size)
        content = data.get("content") or ""
        return ReadmeInfo(present=True, chars=int(len(content) * 0.75))

    def collect(self, full_name: str) -> Snapshot:
        """采集一个仓库的全部事实。

        先单独取仓库本体（顺便确认它存在），再把其余四个资源并行拉取 —— 从
        国内访问 GitHub 时单次往返经常要几秒，串行五个请求会明显拖时间。
        """
        repo = self.fetch_repo(full_name)
        with ThreadPoolExecutor(max_workers=4) as pool:
            commits_future = pool.submit(self.fetch_commits, full_name, 90)
            issues_future = pool.submit(self.fetch_issues, full_name)
            release_future = pool.submit(self.fetch_release, full_name)
            readme_future = pool.submit(self.fetch_readme, full_name)

            commits = commits_future.result()
            issues_raw = issues_future.result()
            release = release_future.result()
            readme = readme_future.result()

        return build_snapshot(repo, commits, issues_raw, release, readme)


# ---------------------------------------------------------------------- 解析


def repo_from_json(data: Dict[str, Any]) -> RepoInfo:
    license_info = data.get("license") or {}
    return RepoInfo(
        full_name=str(data.get("full_name") or ""),
        description=data.get("description"),
        stars=int(data.get("stargazers_count") or 0),
        forks=int(data.get("forks_count") or 0),
        watchers=int(data.get("subscribers_count") or data.get("watchers_count") or 0),
        open_issues_count=int(data.get("open_issues_count") or 0),
        language=data.get("language"),
        license_name=(license_info.get("spdx_id") if isinstance(license_info, dict) else None),
        topics=tuple(data.get("topics") or ()),
        created_at=parse_time(data.get("created_at")),
        pushed_at=parse_time(data.get("pushed_at")),
        archived=bool(data.get("archived")),
        size_kb=int(data.get("size") or 0),
        homepage=data.get("homepage") or None,
    )


def _is_pull(item: Dict[str, Any]) -> bool:
    return "pull_request" in item


def build_issue_stats(items: List[Dict[str, Any]]) -> IssueStats:
    open_issues = closed_issues = open_pulls = closed_pulls = 0
    close_durations: List[float] = []
    pull_durations: List[float] = []

    for item in items:
        is_pr = _is_pull(item)
        state = item.get("state")
        if is_pr:
            if state == "open":
                open_pulls += 1
            else:
                closed_pulls += 1
        else:
            if state == "open":
                open_issues += 1
            else:
                closed_issues += 1

        if state == "closed":
            created = parse_time(item.get("created_at"))
            closed = parse_time(item.get("closed_at"))
            if created and closed:
                duration = (closed - created).total_seconds() / 86400.0
                (pull_durations if is_pr else close_durations).append(duration)

    median = statistics.median(close_durations) if close_durations else None
    median_pull = statistics.median(pull_durations) if pull_durations else None
    return IssueStats(
        open_issues=open_issues,
        closed_issues=closed_issues,
        open_pulls=open_pulls,
        closed_pulls=closed_pulls,
        median_close_days=round(median, 2) if median is not None else None,
        median_pull_days=round(median_pull, 2) if median_pull is not None else None,
    )


def build_snapshot(
    repo: RepoInfo,
    commits: List[Dict[str, Any]],
    issues: List[Dict[str, Any]],
    release: ReleaseInfo,
    readme: ReadmeInfo,
    *,
    now: Optional[datetime] = None,
) -> Snapshot:
    current = now or datetime.now(timezone.utc)
    cutoff_30 = current - timedelta(days=30)

    commit_dates = []
    for item in commits:
        commit = item.get("commit") or {}
        author = commit.get("author") or {}
        stamp = parse_time(author.get("date")) or parse_time(
            (commit.get("committer") or {}).get("date")
        )
        if stamp is not None:
            commit_dates.append(stamp)

    return Snapshot(
        repo=repo,
        issues=build_issue_stats(issues),
        release=release,
        readme=readme,
        commits_90d=len(commits),
        commits_30d=sum(1 for stamp in commit_dates if stamp >= cutoff_30),
        last_commit_at=max(commit_dates) if commit_dates else repo.pushed_at,
        now=current,
    )


def _int_header(value: Optional[str]) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
