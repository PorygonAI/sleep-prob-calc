"""校验并发布睡姿 CSV 到 main；保留原脚本名以兼容现有调用。"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

CSV_NAME = "lapis_lakeside_sleep_styles.csv"
REQUIRED_COLUMNS = {
    "internalId", "pokemon_id", "level_order", "is_on_snorlax",
    "is_leader_exclusion", "spo",
}


def validate_csv(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if REQUIRED_COLUMNS - set(reader.fieldnames or []):
            raise ValueError("CSV 缺少概率计算所需字段。")
        rows = list(reader)
    if not rows:
        raise ValueError("CSV 中没有睡姿。")
    ids = set()
    for row in rows:
        internal_id = int(row["internalId"])
        if internal_id in ids:
            raise ValueError(f"CSV 睡姿重复：{internal_id}")
        ids.add(internal_id)
        if int(row["pokemon_id"]) <= 0 or int(row["spo"]) < 0 or not 0 <= int(row["level_order"]) <= 34:
            raise ValueError(f"CSV 数值无效：{internal_id}")
        for key in ("is_on_snorlax", "is_leader_exclusion"):
            if row[key].strip().lower() not in {"true", "false", "0", "1"}:
                raise ValueError(f"CSV 布尔值无效：{internal_id} / {key}")
    if not {280, 281, 282} <= {int(row["pokemon_id"]) for row in rows}:
        raise ValueError("CSV 缺少拉鲁拉丝、奇鲁莉安或沙奈朵的数据。")
    return len(rows)


def run_git(repo: Path, *arguments: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repo, check=True, text=True,
        encoding="utf-8", errors="replace", capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def check_repo(repo: Path) -> None:
    if run_git(repo, "branch", "--show-current", capture=True) != "main":
        raise RuntimeError("发布仓库必须处于 main 分支。")
    if run_git(repo, "diff", "--cached", "--name-only", capture=True):
        raise RuntimeError("暂存区已有改动，已停止以免混入本次提交。")


def commit_and_push(repo: Path, message: str) -> None:
    # 只提交 CSV，页面改动或其他工作区文件不会混入数据更新。
    run_git(repo, "add", "--", CSV_NAME)
    staged = run_git(repo, "diff", "--cached", "--name-only", capture=True)
    if staged and staged != CSV_NAME:
        raise RuntimeError("暂存区包含非目标文件。")
    if staged:
        run_git(repo, "commit", "-m", message)
    else:
        print("CSV 没有变化，无需创建新提交。")
    # 即使数据不变也推送，以便重试此前提交成功但推送失败的更新。
    run_git(repo, "push", "origin", "main")


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-csv", type=Path, default=script_dir / CSV_NAME)
    default_repo = script_dir if (script_dir / ".git").exists() else script_dir / ".publish" / "sleep-prob-calc"
    parser.add_argument("--repo-dir", type=Path, default=default_repo)
    parser.add_argument("--message", default="Update Lapis Lakeside sleep styles")
    parser.add_argument("--copy-only", action="store_true", help="只复制 CSV，不提交或推送。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repo = args.repo_dir.resolve()
        if not repo.is_dir():
            raise RuntimeError(f"仓库目录不存在：{repo}")
        count = validate_csv(args.source_csv)
        if not args.copy_only:
            check_repo(repo)
        target = repo / CSV_NAME
        if args.source_csv.resolve() != target:
            shutil.copyfile(args.source_csv, target)
        print(f"已复制并校验 {count} 条睡姿：{target}")
        if not args.copy_only:
            commit_and_push(repo, args.message)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
