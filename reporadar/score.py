"""评分。

六个维度各 0~100，加权得到总分。分数只是把事实压成一个方便比较的数字，
真正有用的是每个维度的 ``detail`` 和最后的 ``advice`` —— 所以任何扣分都
必须能说清楚为什么扣。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .models import Snapshot

WEIGHTS = {
    "activity": 0.25,
    "community": 0.15,
    "issues": 0.20,
    "docs": 0.20,
    "release": 0.10,
    "pulls": 0.10,
}

GRADE_CUTOFFS = ((85, "A"), (70, "B"), (55, "C"), (40, "D"), (0, "E"))


def clamp(value: float, low: int = 0, high: int = 100) -> int:
    return int(max(low, min(high, round(value))))


def human_days(days: Optional[float]) -> str:
    """把天数渲染成「今天 / 12 天前 / 3.2 个月前」。用于描述某个时间点。"""
    if days is None:
        return "从未"
    if days < 1:
        return "今天"
    if days < 30:
        return f"{days:.0f} 天前"
    if days < 365:
        return f"{days / 30:.1f} 个月前"
    return f"{days / 365:.1f} 年前"


def human_duration(days: Optional[float]) -> str:
    """把天数渲染成一段时长（「7 天」「1.2 个月」）。用于描述耗时。"""
    if days is None:
        return "未知"
    if days < 1:
        return "1 天内"
    if days < 30:
        return f"{days:.0f} 天"
    if days < 365:
        return f"{days / 30:.1f} 个月"
    return f"{days / 365:.1f} 年"


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    score: int
    weight: float
    detail: str


@dataclass(frozen=True)
class Rating:
    repo: str
    total: int
    grade: str
    metrics: Tuple[Metric, ...]
    advice: Tuple[str, ...]


# --------------------------------------------------------------------- 维度


def score_activity(snapshot: Snapshot) -> Tuple[int, str]:
    days = snapshot.days_since(snapshot.last_commit_at)
    if days is None:
        return 10, "没有可读取的提交记录"

    if days <= 7:
        base = 100
    elif days <= 30:
        base = 88
    elif days <= 90:
        base = 72
    elif days <= 180:
        base = 55
    elif days <= 365:
        base = 32
    else:
        base = 12

    if snapshot.commits_90d >= 30:
        base = min(100, base + 6)
    elif snapshot.commits_90d <= 1 and days > 30:
        base = max(0, base - 10)

    detail = f"最近提交 {human_days(days)}，近 90 天 {snapshot.commits_90d} 次提交"
    return clamp(base), detail


def score_community(snapshot: Snapshot) -> Tuple[int, str]:
    repo = snapshot.repo
    if repo.stars <= 0:
        return 5, f"还没有 star（fork {repo.forks}）"
    base = 15 + 21 * math.log10(repo.stars + 1)
    detail = f"★ {repo.stars} · fork {repo.forks} · watch {repo.watchers}"
    return clamp(base), detail


def score_issues(snapshot: Snapshot) -> Tuple[int, str]:
    stats = snapshot.issues
    if stats.total_issues == 0:
        return 60, "还没有 issue，判断不了响应能力"

    ratio = stats.closed_ratio or 0.0
    base = 40 + 60 * ratio

    if stats.median_close_days is not None:
        if stats.median_close_days <= 3:
            base += 8
        elif stats.median_close_days <= 14:
            base += 4
        elif stats.median_close_days > 90:
            base -= 12

    if stats.open_issues > 50 and ratio < 0.5:
        base -= 12

    detail = (
        f"关闭率 {ratio:.0%}（采样 {stats.total_issues} 条），"
        f"中位 {human_duration(stats.median_close_days)}关闭"
    )
    return clamp(base), detail


def score_docs(snapshot: Snapshot) -> Tuple[int, str]:
    repo = snapshot.repo
    points = 0
    missing: List[str] = []

    if repo.description:
        points += 12
    else:
        missing.append("仓库简介")

    if snapshot.readme.present:
        points += 38
        if snapshot.readme.chars >= 1500:
            points += 10
        else:
            missing.append("更完整的 README")
    else:
        missing.append("README")

    if repo.license_name:
        points += 22
    else:
        missing.append("LICENSE")

    if repo.topics:
        points += 10
    else:
        missing.append("topics")

    if repo.homepage:
        points += 8

    detail = "缺少 " + "、".join(missing) if missing else "简介 / README / LICENSE / topics 齐全"
    return clamp(points), detail


def score_release(snapshot: Snapshot) -> Tuple[int, str]:
    days = snapshot.days_since(snapshot.release.published_at)
    if days is None:
        return 25, "没有发布过 release"
    if days <= 90:
        base = 100
    elif days <= 180:
        base = 85
    elif days <= 365:
        base = 65
    else:
        base = 40
    tag = snapshot.release.tag or "（无 tag）"
    return clamp(base), f"最近发布 {human_days(days)}（{tag}）"


def score_pulls(snapshot: Snapshot) -> Tuple[int, str]:
    stats = snapshot.issues
    if stats.open_pulls == 0 and stats.closed_pulls == 0:
        return 60, "还没有 PR"
    if stats.median_pull_days is None:
        return 55, f"{stats.open_pulls} 个 PR 尚未处理"

    days = stats.median_pull_days
    if days <= 2:
        base = 100
    elif days <= 7:
        base = 85
    elif days <= 30:
        base = 65
    else:
        base = 40

    if stats.open_pulls > 10:
        base -= 8

    detail = f"PR 中位 {human_duration(days)}关闭，待处理 {stats.open_pulls} 个"
    return clamp(base), detail


# --------------------------------------------------------------------- 汇总


def grade_of(total: int) -> str:
    for cutoff, grade in GRADE_CUTOFFS:
        if total >= cutoff:
            return grade
    return "E"


def build_advice(snapshot: Snapshot, metrics: Tuple[Metric, ...]) -> Tuple[str, ...]:
    by_key = {metric.key: metric for metric in metrics}
    advice: List[str] = []

    if snapshot.repo.archived:
        advice.append("仓库已归档，分数只作历史参考；要继续维护请先取消归档。")

    docs = by_key["docs"]
    if docs.score < 60:
        advice.append(f"补齐文档：{docs.detail}。README 至少写清用途、安装、最小示例。")

    if by_key["activity"].score < 60:
        advice.append(
            "近三个月提交偏少。哪怕只是更新依赖或补一条 changelog，也能让访客判断项目还活着。"
        )

    issues = by_key["issues"]
    if issues.score < 60:
        advice.append(
            f"issue 维护偏弱（{issues.detail}）。先给每条 issue 打标签，或把不打算做的直接关闭并说明理由。"
        )

    if by_key["release"].score < 60:
        advice.append("还没有像样的版本发布。打一个 v0.1.0 的 tag，别人引用时才有坐标。")

    if by_key["community"].score < 40:
        advice.append("补上 topics 和社交预览图，能被搜索到比 star 数量更重要。")

    if by_key["pulls"].score < 55:
        advice.append("有 PR 长时间悬着。哪怕回一句「这周看」，也比沉默好。")

    if not advice:
        advice.append("六个维度都比较均衡，保持现在的节奏即可。")

    return tuple(advice[:4])


def rate(snapshot: Snapshot) -> Rating:
    """对一份快照打分。"""
    pairs = (
        ("activity", "活跃度", score_activity(snapshot)),
        ("community", "社区", score_community(snapshot)),
        ("issues", "issue", score_issues(snapshot)),
        ("docs", "文档", score_docs(snapshot)),
        ("release", "发布", score_release(snapshot)),
        ("pulls", "PR", score_pulls(snapshot)),
    )
    metrics = tuple(
        Metric(key=key, label=label, score=score, weight=WEIGHTS[key], detail=detail)
        for key, label, (score, detail) in pairs
    )
    total = int(round(sum(metric.score * metric.weight for metric in metrics)))
    return Rating(
        repo=snapshot.repo.full_name,
        total=total,
        grade=grade_of(total),
        metrics=metrics,
        advice=build_advice(snapshot, metrics),
    )
