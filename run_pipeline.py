"""抓取最新宝蓝湖畔 CSV 并发布到 GitHub；概率由网页计算。"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run_stage(name: str, command: list[str], cwd: Path) -> None:
    print(f"\n=== {name} ===", flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--message",
        default="Update Lapis Lakeside sleep styles",
        help="Git 提交信息。",
    )
    script_dir = Path(__file__).resolve().parent
    default_repo = script_dir if (script_dir / ".git").exists() else script_dir / ".publish" / "sleep-prob-calc"
    parser.add_argument("--repo-dir", type=Path, default=default_repo)
    parser.add_argument("--copy-only", action="store_true", help="爬取并复制 CSV，不提交或推送。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    python = sys.executable

    stages = [
        (
            "爬取宝蓝湖畔睡姿数据",
            [python, str(script_dir / "scrape_lapis_lakeside_spo.py")],
        ),
    ]
    publish_command = [
        python,
        str(script_dir / "publish_ralts_probability.py"),
        "--repo-dir",
        str(args.repo_dir.resolve()),
        "--message",
        args.message,
    ]
    if args.copy_only:
        publish_command.append("--copy-only")
    stages.append(("发布睡姿 CSV", publish_command))

    try:
        for name, command in stages:
            run_stage(name, command, script_dir)
    except subprocess.CalledProcessError as exc:
        print(
            f"流程在命令 {subprocess.list2cmdline(exc.cmd)} 处失败，"
            f"退出码：{exc.returncode}",
            file=sys.stderr,
        )
        return exc.returncode or 1

    print("\n完成。网页将使用最新 CSV 在浏览器中计算概率。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
