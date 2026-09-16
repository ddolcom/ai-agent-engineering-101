# Week 03 Report - Contract Net with LLM Contractors

## 1. Setup

- **Student ID**: 26620029 (GitHub: ddolcom)
- **Repository**: https://github.com/ddolcom/ai-agent-engineering-101, `submissions/26620029/week-03/`
- **Provider / model**: selected from the environment, same pattern as week 02 --
  `ANTHROPIC_API_KEY` set -> Anthropic SDK, model `claude-sonnet-4-5` unless
  `AGENT_MODEL` overrides it; otherwise the OpenAI-compatible SDK, using
  `OPENAI_API_KEY` (+ `OPENAI_BASE_URL` for OpenRouter). See `contract_net.py`,
  top of file.
- **Temperature**: `AGENT_TEMPERATURE` env var, default `0.7`, identical across
  all three conditions and all nine runs (`run_week03.py` passes the same
  value to every `run_condition` call).
- **API key**: never stored in source, `results.csv`, logs, or this report.
  `.gitignore` at the repository root already excludes `.env`.

### Contract net structure

- **Manager** (`contract_net.py`): plain deterministic Python. Builds the
  announcement, calls each contractor once, parses the three replies, and
  awards to the highest-confidence valid `bid=true` reply (ties broken by
  fixed A/B/C order). The manager never calls an LLM and never reads `gold`;
  `gold` is read only after the award, purely to score it.
- **Contractors**: three independent, single-turn, tool-free LLM calls (no
  multi-turn loop, no tool calling -- see `call_llm` in `contract_net.py`).
  Each contractor gets its own system prompt plus the same announcement text.

| Condition | Contractor A | Contractor B | Contractor C |
|---|---|---|---|
| baseline | Calculator specialist | Analyst specialist | Writer specialist |
| homogeneous | Generalist (same prompt) | Generalist (same prompt) | Generalist (same prompt) |
| overconfident | Calculator specialist + "always bid, confidence >= 95" | Analyst specialist | Writer specialist |

Full prompt text is in `contract_net.py` (`CALC_PROMPT`, `ANALYST_PROMPT`,
`WRITER_PROMPT`, `GENERALIST_PROMPT`, `OVERCONFIDENT_SUFFIX`). Only the
system prompt changes between conditions; `tasks.json`, the announcement
template, the model, the temperature, the manager, and the scoring logic
are shared by all three.

### Bid format

Every contractor is instructed to answer only with:

```json
{"bid": true, "confidence": 95, "reason": "..."}
```

A reply that does not contain a JSON object with a boolean `bid` and a
numeric `confidence` in `[0, 100]` is treated as a no-bid and logged as
`PARSE_ERROR` with the raw text kept (`parse_bid` in `contract_net.py`); it
is never repaired or guessed at.

- **Tasks**: `tasks.json`, 6 tasks, `gold` in `{calculator, analyst, writer}`,
  two tasks per gold value.
- **How to run**: see `README.md`. Short version: `pip install anthropic`
  (or `openai`), export the key, then `python run_week03.py --all` for all
  nine runs, or `--condition <name> --runs 3` per condition.

### Execution status

**No LLM API key is available in the session that produced this submission's
code**, so the nine real runs (`baseline` x3, `homogeneous` x3,
`overconfident` x3) have not been executed yet. Per the course's rule against
fabricated results, `results.csv` currently contains only the header row and
`logs/` is empty -- no invented numbers or logs have been written.

What has been verified without a real API key:

- `python -m py_compile contract_net.py run_week03.py` -- both files parse.
- `tasks.json` is valid JSON, 6 entries, all with `id`/`desc`/`gold`, 3
  distinct gold values.
- `results.csv` header matches the required columns exactly.
- The full announce -> bid -> parse -> award -> score pipeline was exercised
  end to end with a mocked `call_llm` (a local, non-committed script), for
  all three conditions, confirming: message counts are `tasks x 7` when
  every contractor answers, `correct + misaward + unassigned == tasks`
  always holds, a deliberately unparseable reply is logged as
  `PARSE_ERROR` and correctly excluded from bidding, and the manager's
  winner selection never inspects `gold`.

To finish this submission, run on a machine with an API key:

```bash
export ANTHROPIC_API_KEY=<key>     # or OPENAI_API_KEY (+ OPENAI_BASE_URL)
cd submissions/26620029/week-03
python run_week03.py --all
python ../../../scripts/check_week03.py .
```

then fill in Sections 2 and 4 below from the resulting `results.csv` and
`logs/`.

## 2. Results

*Pending real execution (see Section 1, Execution status). Once
`run_week03.py --all` has produced 9 real runs, this section reports:*

- *The full `results.csv` table (run, condition, tasks, correct, messages,
  unassigned, misawards, note).*
- *Per-condition aggregates: `accuracy = correct / tasks`,
  `misaward rate = misawards / tasks`, `unassigned rate = unassigned / tasks`,
  averaged across each condition's 3+ runs.*
- *Average token usage per contractor per condition, from the
  `token_usage input_tokens=... output_tokens=... total_tokens=...` lines in
  `logs/*.log` (token usage is not part of the official `results.csv`
  schema, per the assignment; it is reported here and in the logs only).*

| run | condition | tasks | correct | messages | unassigned | misawards | note |
|---|---|---|---|---|---|---|---|
| *(to be filled in from results.csv after real runs)* | | | | | | | |

## 3. Smith 1980 comparison

| Item | Smith 1980 distributed sensing setup | This LLM reproduction |
|---|---|---|
| Nodes | Autonomous problem-solving nodes on a network, each with local sensors/processing, communicating by message passing. | One deterministic Python manager process + three independent LLM contractor calls, no persistent node state between tasks. |
| How a bid is produced | A node evaluates the task announcement against its own local capability model with a fixed procedural rule (e.g. can it reach the required sensor region, does it have spare capacity) and computes a bid deterministically. | Each contractor's bid is generated by an LLM reading its system prompt and the announcement in a single turn, judging its own fitness in natural language and emitting a JSON bid; the "capability model" is a system prompt, not a formula. |
| What guarantees bid honesty | None built into the protocol itself; Smith notes bidding is cooperative and assumes nodes report accurately, since all nodes share the same overall goal. | Also nothing structural -- the manager cannot verify a contractor's self-assessment; unlike Smith's setting, a same-provider LLM can be told (via prompt only) to misrepresent confidence, as the `overconfident` condition deliberately does, and the manager has no way to detect this from the bid alone. |
| Allocation quality | Correctness of the announced task-to-node match, evaluated against the true capability requirements (e.g. the node whose sensor actually covers the target area). | Correctness measured against `gold`, the pre-declared best-fit contractor for each task, compared only after the award (never used to decide it). |
| Negotiation cost | Cost of the announce/bid/award message round trip across the network, counted in messages exchanged. | Cost is the same message-counting scheme (3 announcements + up to 3 bids + 1 award per task) plus, unlike 1980, LLM API cost: input/output tokens per contractor call, logged separately since the official `results.csv` schema has no token column. |
| Failure modes | Node overload, message loss, stale bids, no node bidding on an announced task. | No node bidding maps to `unassigned` (parse failure or explicit `bid=false` from everyone); "stale/wrong bid" maps to `misaward`; and a failure mode 1980 could not have, because it assumed a numeric bid computed by a fixed rule: a reply that is not valid JSON at all (`PARSE_ERROR`), which this protocol treats as a no-bid rather than crashing or guessing. |

Particular points of interest for this reproduction, to be grounded in log
evidence once the real runs exist:

- Contractors misjudging their own fit (bidding on tasks outside their
  stated specialty, or declining tasks they could plausibly do).
- Overconfidence: whether the `overconfident` contractor's fixed
  `confidence=95+` lets it win tasks a specialist contractor would have won
  in `baseline`.
- Unparseable JSON: how often, and under which condition/provider, a
  contractor's reply fails `parse_bid` and is logged as `PARSE_ERROR`.
- No-bid tasks (`unassigned`) and wrong awards (`misaward`), and whether
  either clusters in a particular condition.
- The added communication/LLM-call cost of judged bidding versus Smith's
  fixed-rule bid: 3 LLM calls per task regardless of outcome, so a task
  with two immediate no-bids still costs as much in calls as one with three
  competing bids.

## 4. Interpretation

*To be written from the actual `results.csv` and `logs/*.log` once the nine
runs have been executed with a real API key -- this project's rules forbid
writing this paragraph from invented numbers. The final version will avoid a
single "winner" declaration and instead describe, condition by condition,
which metric moved and why: in `baseline`, how well confidence-based
selection recovers the intended `gold` contractor when specialties are
real and distinct, with the specific log lines that show a specialist
correctly declining a wrong task; in `homogeneous`, whether removing the
specialty from the prompt (while keeping the same role labels for scoring)
collapses accuracy toward chance and raises misawards, since no contractor
has a real reason to prefer one task over another; in `overconfident`,
whether the one contractor forced to always bid at confidence >= 95 sweeps
tasks it has no real competence for, and by how much this raises
misawards relative to `baseline`, with example reasons quoted from that
contractor's log entries. It will also state plainly where judged bidding
helped -- e.g. correctly declining out-of-specialty tasks in `baseline` --
and where it broke, quoting `PARSE_ERROR` and `misaward` lines as evidence,
and note explicitly that Smith's original protocol has no mechanism to
detect either an LLM contractor inflating its confidence or a
non-numeric, unparseable bid, since it assumed bids were computed by a
fixed, inspectable rule rather than judged in natural language.*
