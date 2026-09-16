# Week 03 - Contract Net with LLM Contractors

Student ID: 26620029
GitHub: ddolcom

## Setup

```bash
pip install anthropic   # or: pip install openai

export ANTHROPIC_API_KEY=<your key>              # Anthropic, or:
export OPENAI_BASE_URL=https://openrouter.ai/api/v1
export OPENAI_API_KEY=<your key>                 # OpenAI-compatible / OpenRouter
export AGENT_MODEL=<model id>                    # optional, defaults per provider
export AGENT_TEMPERATURE=0.7                     # optional, default 0.7
```

No key is stored anywhere in this submission; it must be set in the
environment before running.

## Run

```bash
python run_week03.py --condition baseline --runs 3
python run_week03.py --condition homogeneous --runs 3
python run_week03.py --condition overconfident --runs 3

# or all nine runs at once:
python run_week03.py --all
```

Each run appends one row to `results.csv` and writes one log file to
`logs/<condition>_run_<NN>.log`.

## Check

```bash
python ../../../scripts/check_week03.py .
```

(Run from `submissions/26620029/week-03/`, or point the checker at the
full path from the repository root.)

## Conditions

- `baseline` -- three contractors, three different specialist prompts (calculator / analyst / writer).
- `homogeneous` -- same three contractors, all given the identical generalist prompt.
- `overconfident` -- baseline, except Contractor A (calculator) is told to always bid with confidence >= 95.

## Files

- `contract_net.py` -- the contract net: contractors, manager, bid parsing, scoring.
- `run_week03.py` -- CLI runner, writes `results.csv` and `logs/`.
- `tasks.json` -- 6 tasks, `gold` in `{calculator, analyst, writer}`.
- `results.csv` -- one row per run.
- `logs/` -- one console capture per run.
- `REPORT.md` -- setup, results, Smith 1980 comparison, interpretation.
