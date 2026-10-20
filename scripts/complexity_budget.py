"""Fail if any function's cyclomatic complexity (radon) exceeds the budget in docs/CODE_QUALITY.md."""

import json
import subprocess
import sys

BUDGET = 15


def main(paths: list[str]) -> int:
    out = subprocess.run([sys.executable, "-m", "radon", "cc", "-j", *paths], capture_output=True, text=True,
                         check=True).stdout
    over = [f"{path}:{b['lineno']} {b['name']} ({b['complexity']})"
            for path, blocks in json.loads(out).items() for b in blocks if b["complexity"] > BUDGET]
    print("\n".join(over) if over else f"ok: every function at or below {BUDGET}")
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["nbatotals", "tests"]))
