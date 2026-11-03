"""输出渲染：终端报告、Markdown、JSON。

中文在终端里占两格，所以对齐必须按显示宽度算，不能用 ``len()``。
"""

from __future__ import annotations

import json
import unicodedata
from typing import Dict, List, Sequence

from .score import Rating, human_days

BAR_WIDTH = 20
RULE = "=" * 78


def char_width(char: str) -> int:
    """东亚宽字符按 2 列计算，其余（含 █ ░ 这类框线字符）按 1 列。"""
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 2
    return 1


def display_width(text: str) -> int:
    return sum(char_width(char) for char in text)


def pad(text: str, width: int) -> str:
    """右侧补空格到指定显示宽度（超长不截断）。"""
    return text + " " * max(0, width - display_width(text))


def bar(score: int, width: int = BAR_WIDTH) -> str:
    filled = int(round(width * max(0, min(100, score)) / 100))
    return "█" * filled + "░" * (width - filled)


def render_terminal(rating: Rating, snapshot_facts: Sequence[str] = ()) -> str:
    """单仓库的终端报告。"""
    lines: List[str] = [RULE]
    header = f" {rating.repo}"
    score_text = f"{rating.grade}  {rating.total}/100 "
    lines.append(pad(header, 78 - display_width(score_text)) + score_text)
    if snapshot_facts:
        lines.append(" " + " · ".join(snapshot_facts))
    lines.append(RULE)
    for metric in rating.metrics:
        label = pad(metric.label, 8)
        lines.append(
            f"  {label}{bar(metric.score)}  {str(metric.score).rjust(4)} {metric.detail}"
        )
    lines.append("-" * 78)
    lines.append("  建议")
    for item in rating.advice:
        lines.append(f"   · {item}")
    lines.append(RULE)
    return "\n".join(lines)


def render_facts(repo, snapshot) -> List[str]:
    """报告顶部那行事实摘要。"""
    facts = [repo.language or "未知语言"]
    facts.append(f"★ {repo.stars}")
    facts.append(f"fork {repo.forks}")
    if repo.archived:
        facts.append("已归档")
    facts.append(f"最近提交 {human_days(snapshot.days_since(snapshot.last_commit_at))}")
    if repo.created_at:
        facts.append(f"建于 {human_days(snapshot.days_since(repo.created_at))}")
    return facts


def render_markdown(ratings: Sequence[Rating]) -> str:
    blocks: List[str] = []
    for rating in ratings:
        blocks.append(f"## {rating.repo} — {rating.total}/100（{rating.grade}）")
        blocks.append("")
        blocks.append("| 维度 | 分数 | 权重 | 说明 |")
        blocks.append("| --- | ---: | ---: | --- |")
        for metric in rating.metrics:
            blocks.append(
                f"| {metric.label} | {metric.score} | {metric.weight:.0%} | {metric.detail} |"
            )
        blocks.append("")
        blocks.append("**改进建议**")
        blocks.append("")
        for item in rating.advice:
            blocks.append(f"- {item}")
        blocks.append("")
    return "\n".join(blocks).strip() + "\n"


def rating_to_dict(rating: Rating) -> Dict[str, object]:
    return {
        "repo": rating.repo,
        "total": rating.total,
        "grade": rating.grade,
        "metrics": [
            {
                "key": metric.key,
                "label": metric.label,
                "score": metric.score,
                "weight": metric.weight,
                "detail": metric.detail,
            }
            for metric in rating.metrics
        ],
        "advice": list(rating.advice),
    }


def render_json(ratings: Sequence[Rating]) -> str:
    payload = {"repos": [rating_to_dict(rating) for rating in ratings]}
    return json.dumps(payload, ensure_ascii=False, indent=2)
