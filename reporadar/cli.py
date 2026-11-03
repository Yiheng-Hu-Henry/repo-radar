"""命令行入口。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from . import __version__
from .api import GitHubClient, GitHubError, NotFound, RateLimited
from .render import render_facts, render_json, render_markdown, render_terminal
from .score import Rating, rate


def normalize_repo(value: str) -> str:
    """接受 ``owner/repo``、``https://github.com/owner/repo`` 或带 .git 的写法。"""
    text = value.strip().rstrip("/")
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    if text.endswith(".git"):
        text = text[: -len(".git")]
    parts = [piece for piece in text.split("/") if piece]
    if len(parts) != 2:
        raise ValueError(f"不是合法的仓库标识：{value}（应为 owner/repo）")
    return f"{parts[0]}/{parts[1]}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporadar",
        description="给 GitHub 仓库做一次体检：活跃度、issue、文档、发布、PR 五个维度打分。",
    )
    parser.add_argument("--version", action="version", version=f"reporadar {__version__}")

    sub = parser.add_subparsers(dest="command")

    check = sub.add_parser("check", help="体检一个或多个仓库")
    check.add_argument("repos", nargs="+", help="owner/repo，可给多个")
    check.add_argument("--json", action="store_true", help="输出 JSON")
    check.add_argument("--md", metavar="FILE", help="同时写出 Markdown 报告")
    check.add_argument("--token", help="GitHub token（默认读 GITHUB_TOKEN / GH_TOKEN）")
    check.add_argument("--timeout", type=float, default=20.0, help="单请求超时（秒）")
    check.add_argument(
        "--pages", type=int, default=2, help="issue 列表拉取页数（每页 100 条）"
    )
    check.set_defaults(func=cmd_check)

    return parser


def cmd_check(args: argparse.Namespace) -> int:
    try:
        targets = [normalize_repo(value) for value in args.repos]
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    client = GitHubClient(token=args.token, timeout=args.timeout)
    ratings: List[Rating] = []
    facts: dict = {}
    failures = 0

    for full_name in targets:
        try:
            snapshot = client.collect(full_name)
        except NotFound:
            print(f"× {full_name}：仓库不存在或没有访问权限", file=sys.stderr)
            failures += 1
            continue
        except RateLimited as error:
            print(f"× {full_name}：{error}", file=sys.stderr)
            failures += 1
            continue
        except GitHubError as error:
            print(f"× {full_name}：{error}", file=sys.stderr)
            failures += 1
            continue

        rating = rate(snapshot)
        ratings.append(rating)
        facts[rating.repo] = render_facts(snapshot.repo, snapshot)

    if not ratings:
        return 1 if failures else 0

    if args.json:
        print(render_json(ratings))
    else:
        for index, rating in enumerate(ratings):
            if index:
                print()
            print(render_terminal(rating, facts.get(rating.repo, [])))

    if args.md:
        target = Path(args.md)
        target.write_text(render_markdown(ratings), encoding="utf-8")
        print(f"\n已写出 Markdown：{target}", file=sys.stderr)

    if len(ratings) > 1:
        print()
        print("汇总")
        for rating in sorted(ratings, key=lambda item: item.total, reverse=True):
            print(f"  {rating.total:>3}  {rating.grade}  {rating.repo}")

    return 1 if failures else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
