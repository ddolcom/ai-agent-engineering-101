#!/usr/bin/env python3
"""Week 03 runner -- executes contract net conditions and records results.

Usage:
  python run_week03.py --condition baseline --runs 3
  python run_week03.py --condition homogeneous --runs 3
  python run_week03.py --condition overconfident --runs 3
  python run_week03.py --all                       # 3 runs x 3 conditions

Requires an LLM API key in the environment (never hardcoded):
  ANTHROPIC_API_KEY                        -> Anthropic SDK
  OPENAI_API_KEY (+ optional OPENAI_BASE_URL)  -> OpenAI-compatible SDK
  AGENT_MODEL, AGENT_TEMPERATURE           optional overrides

Each run appends one row to results.csv and writes one log file under
logs/. A run that raises is still recorded, with blank counts and the
error in the note column, per the assignment's crashed-run rule.
"""
import argparse
import csv
import json
import traceback
from pathlib import Path

import contract_net as cn

HERE = Path(__file__).resolve().parent
TASKS_FILE = HERE / "tasks.json"
RESULTS_FILE = HERE / "results.csv"
LOGS_DIR = HERE / "logs"
CONDITIONS = ("baseline", "homogeneous", "overconfident")
HEADER = ["run", "condition", "tasks", "correct", "messages", "unassigned", "misawards", "note"]


def load_tasks():
    return json.loads(TASKS_FILE.read_text(encoding="utf-8"))


def next_run_number() -> int:
    if not RESULTS_FILE.exists():
        return 1
    with RESULTS_FILE.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    data = [r for r in rows[1:] if any(c.strip() for c in r)]
    return len(data) + 1


def append_result(row: dict) -> None:
    exists = RESULTS_FILE.exists()
    with RESULTS_FILE.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def run_once(condition: str, run_number: int, run_index: int, tasks, temperature) -> dict:
    LOGS_DIR.mkdir(exist_ok=True)
    log_path = LOGS_DIR / f"{condition}_run_{run_index:02d}.log"
    lines = [f"RUN {run_number}"]

    def log(msg: str = "") -> None:
        lines.append(str(msg))

    contractors = cn.build_contractors(condition)
    try:
        metrics = cn.run_condition(condition, contractors, tasks, temperature, log)
        row = {"run": run_number, "condition": condition, "note": "", **metrics}
    except Exception as e:
        log(f"\nCRASH: {type(e).__name__}: {e}")
        log(traceback.format_exc())
        row = {"run": run_number, "condition": condition, "tasks": "",
               "correct": "", "messages": "", "unassigned": "", "misawards": "",
               "note": f"{type(e).__name__}: {e}"}
    finally:
        log_path.write_text("\n".join(lines), encoding="utf-8")

    append_result(row)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--condition", choices=CONDITIONS)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--all", action="store_true", help="run all 3 conditions")
    parser.add_argument("--temperature", type=float, default=cn.TEMPERATURE)
    args = parser.parse_args()

    if not args.all and not args.condition:
        parser.error("specify --condition <name> or --all")

    tasks = load_tasks()
    plan = ([(c, r) for c in CONDITIONS for r in range(1, args.runs + 1)] if args.all
            else [(args.condition, r) for r in range(1, args.runs + 1)])

    for condition, idx in plan:
        run_number = next_run_number()
        row = run_once(condition, run_number, idx, tasks, args.temperature)
        print(f"run {run_number} [{condition} #{idx}]: {row}")


if __name__ == "__main__":
    main()
