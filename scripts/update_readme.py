#!/usr/bin/env python3
"""
pre-push 훅에서 호출. README.md의 동적 섹션(뱃지, 마지막 업데이트, 커밋 수)을 갱신한다.
"""
import subprocess
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
README = ROOT / "README.md"

KST = timezone(timedelta(hours=9))


def _run(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, cwd=ROOT, text=True).strip()


def _commits() -> int:
    return int(_run("git rev-list --count HEAD"))


def _last_commit_msg() -> str:
    return _run("git log -1 --pretty=%s")


def _file_count() -> dict:
    counts = {}
    for pattern, label in [("core/*.py", "core"), ("strategies/*.py", "strategies")]:
        result = _run(f"ls {ROOT}/{pattern} 2>/dev/null | wc -l")
        counts[label] = result.strip()
    return counts


def update():
    if not README.exists():
        print("[update_readme] README.md 없음 — 건너뜀")
        return

    content = README.read_text(encoding="utf-8")
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    commits = _commits()
    last_msg = _last_commit_msg()

    # <!-- DYNAMIC:last_updated --> ... <!-- /DYNAMIC -->
    content = re.sub(
        r"<!-- DYNAMIC:last_updated -->.*?<!-- /DYNAMIC -->",
        f"<!-- DYNAMIC:last_updated -->{now}<!-- /DYNAMIC -->",
        content, flags=re.DOTALL
    )

    # <!-- DYNAMIC:commit_count --> ... <!-- /DYNAMIC -->
    content = re.sub(
        r"<!-- DYNAMIC:commit_count -->.*?<!-- /DYNAMIC -->",
        f"<!-- DYNAMIC:commit_count -->{commits}<!-- /DYNAMIC -->",
        content, flags=re.DOTALL
    )

    # <!-- DYNAMIC:last_commit --> ... <!-- /DYNAMIC -->
    content = re.sub(
        r"<!-- DYNAMIC:last_commit -->.*?<!-- /DYNAMIC -->",
        f"<!-- DYNAMIC:last_commit -->{last_msg}<!-- /DYNAMIC -->",
        content, flags=re.DOTALL
    )

    README.write_text(content, encoding="utf-8")
    print(f"[update_readme] 업데이트 완료 — 커밋 {commits}개, {now}")


if __name__ == "__main__":
    update()
