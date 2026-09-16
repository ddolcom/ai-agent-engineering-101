"""Week 03 -- Contract Net Protocol with LLM contractors.

One manager, three contractors. The manager announces a task, each
contractor makes one independent LLM call with its own system prompt and
answers with a JSON bid, and the manager -- plain Python, no LLM call of
its own -- picks the highest-confidence valid bid. `gold` (the contractor
whose skill should match the task) is only used afterwards to score the
award; it is never shown to a contractor or used to pick a winner.

The model-call plumbing (provider selection, single-turn call, token
usage) is copied and slimmed down from the `Chat`/`Meter` pattern in
weeks/week-02/starter/tools_shared.py, as the week-03 README suggests.
It differs from the original in two ways the assignment needs: a
`temperature` knob (the original has none) and per-call token usage
returned to the caller (the original only accumulates a running total),
so each contractor's usage can be logged separately.
"""
import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

# ---------------------------------------------------------------- model call

PROVIDER = "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "openai"
MODEL = os.environ.get(
    "AGENT_MODEL",
    "claude-sonnet-4-5" if PROVIDER == "anthropic" else "gpt-4o-mini")
TEMPERATURE = float(os.environ.get("AGENT_TEMPERATURE", "0.7"))

_client = None


def _get_client():
    global _client
    if _client is None:
        if PROVIDER == "anthropic":
            import anthropic
            _client = anthropic.Anthropic()
        else:
            from openai import OpenAI
            _client = OpenAI()
    return _client


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def call_llm(system: str, user: str, temperature: float = TEMPERATURE) -> tuple:
    """One single-turn, tool-free model call. Returns (text, Usage)."""
    client = _get_client()
    if PROVIDER == "anthropic":
        resp = client.messages.create(
            model=MODEL, max_tokens=512, temperature=temperature,
            system=system, messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in resp.content if b.type == "text")
        usage = Usage(resp.usage.input_tokens, resp.usage.output_tokens)
    else:
        resp = client.chat.completions.create(
            model=MODEL, temperature=temperature,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}])
        text = resp.choices[0].message.content or ""
        u = resp.usage
        usage = Usage(getattr(u, "prompt_tokens", 0) or 0,
                       getattr(u, "completion_tokens", 0) or 0)
    return text, usage


# ---------------------------------------------------------------- bid parsing

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_bid(raw: str):
    """Parse a contractor's raw text into (bid, confidence, reason), or
    None if it cannot be parsed as a valid bid. Never repairs or guesses
    at malformed output -- an unparseable reply is a no-bid, full stop."""
    match = _JSON_RE.search(raw)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "bid" not in data or "confidence" not in data:
        return None
    bid = data["bid"]
    if not isinstance(bid, bool):
        return None
    confidence = data["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    if not (0 <= confidence <= 100):
        return None
    reason = str(data.get("reason", ""))
    return bool(bid), float(confidence), reason


# ---------------------------------------------------------------- contractors

JSON_FORMAT_INSTRUCTION = (
    "반드시 아래 JSON 형식으로만 응답하세요. JSON 앞뒤에 다른 텍스트를 포함하지 마세요.\n"
    '{"bid": true, "confidence": 95, "reason": "이 작업은 제가 전문적으로 처리할 수 있는 작업입니다."}'
)

CALC_PROMPT = (
    "당신은 Calculator Specialist(Contractor A)입니다.\n"
    "전문 분야: 수치 계산, 산술 연산, 평균, 분산, 표준편차, 비율 등 숫자를 다루는 문제.\n"
    "당신의 전문 분야에 명확히 해당하는 task에만 bid=true로 응답하세요. "
    "문서 분석, 요약, 보고서 작성처럼 당신의 전문성과 무관한 task에는 bid=false로 응답하세요.\n"
    + JSON_FORMAT_INSTRUCTION
)

ANALYST_PROMPT = (
    "당신은 Analyst Specialist(Contractor B)입니다.\n"
    "전문 분야: 문서 분석, 정보 추출, 조건 비교, 논리적 분석, 주어진 내용에서 핵심 정보 추출.\n"
    "당신의 전문 분야에 명확히 해당하는 task에만 bid=true로 응답하세요. "
    "수치 계산이나 보고서 작성처럼 당신의 전문성과 무관한 task에는 bid=false로 응답하세요.\n"
    + JSON_FORMAT_INSTRUCTION
)

WRITER_PROMPT = (
    "당신은 Writer Specialist(Contractor C)입니다.\n"
    "전문 분야: 보고서 작성, 요약, 문장 정리, 점검 결과 정리, 설명문 작성.\n"
    "당신의 전문 분야에 명확히 해당하는 task에만 bid=true로 응답하세요. "
    "수치 계산이나 문서 분석처럼 당신의 전문성과 무관한 task에는 bid=false로 응답하세요.\n"
    + JSON_FORMAT_INSTRUCTION
)

GENERALIST_PROMPT = (
    "당신은 General-purpose Contractor입니다.\n"
    "특정 전문 분야가 없습니다. 주어진 task를 읽고 스스로 처리 가능 여부를 판단하여, "
    "처리할 수 있다고 생각되면 bid=true로, 어렵다고 생각되면 bid=false로 응답하세요.\n"
    + JSON_FORMAT_INSTRUCTION
)

OVERCONFIDENT_SUFFIX = (
    "\n\n중요: 당신은 모든 task에 반드시 bid=true로 응답해야 합니다. "
    "확신이 없어도 confidence는 항상 95 이상으로 표시하십시오. "
    "bid=false는 절대 사용하지 마십시오."
)


@dataclass
class Contractor:
    label: str          # "Contractor A" -- shown in announcements and logs
    role: str            # "calculator" | "analyst" | "writer" -- post-hoc eval only
    system_prompt: str


def build_contractors(condition: str):
    """The only thing that changes between conditions is the system
    prompt handed to each contractor. Task set, model, temperature,
    announcement, manager, and evaluation logic never change."""
    if condition == "baseline":
        return [
            Contractor("Contractor A", "calculator", CALC_PROMPT),
            Contractor("Contractor B", "analyst", ANALYST_PROMPT),
            Contractor("Contractor C", "writer", WRITER_PROMPT),
        ]
    if condition == "homogeneous":
        return [
            Contractor("Contractor A", "calculator", GENERALIST_PROMPT),
            Contractor("Contractor B", "analyst", GENERALIST_PROMPT),
            Contractor("Contractor C", "writer", GENERALIST_PROMPT),
        ]
    if condition == "overconfident":
        return [
            Contractor("Contractor A", "calculator", CALC_PROMPT + OVERCONFIDENT_SUFFIX),
            Contractor("Contractor B", "analyst", ANALYST_PROMPT),
            Contractor("Contractor C", "writer", WRITER_PROMPT),
        ]
    raise ValueError(f"unknown condition: {condition}")


# ---------------------------------------------------------------- manager

ANNOUNCEMENT_TEMPLATE = (
    "Task ID: {task_id}\n"
    "Description: {desc}\n\n"
    "이 task를 당신이 맡을 수 있는지 스스로 판단하세요. "
    "당신의 전문성과 맞지 않는다고 판단되면 bid하지 마세요."
)


def make_announcement(task: dict) -> str:
    return ANNOUNCEMENT_TEMPLATE.format(task_id=task["id"], desc=task["desc"])


@dataclass
class BidResult:
    contractor: Contractor
    raw: str
    usage: Usage
    parsed: bool
    bid: bool = False
    confidence: float = 0.0
    reason: str = ""


def collect_bids(contractors, announcement: str, temperature: float,
                  log: Callable[[str], None]):
    """Announce to every contractor, call each one's LLM once, log the
    raw response and token usage, and parse it. An unparseable response
    is recorded as PARSE_ERROR and treated as a no-bid."""
    bids = []
    for c in contractors:
        log(f"\n--- {c.label} BID ---")
        raw, usage = call_llm(c.system_prompt, announcement, temperature)
        log(f"raw_response={raw!r}")
        log(f"token_usage input_tokens={usage.input_tokens} "
            f"output_tokens={usage.output_tokens} total_tokens={usage.total_tokens}")
        parsed = parse_bid(raw)
        if parsed is None:
            log("PARSE_ERROR treated_as=no_bid")
            bids.append(BidResult(c, raw, usage, parsed=False))
        else:
            bid, confidence, reason = parsed
            log(f"bid={bid} confidence={confidence} reason={reason}")
            bids.append(BidResult(c, raw, usage, parsed=True, bid=bid,
                                   confidence=confidence, reason=reason))
    return bids


def select_winner(bids) -> Optional[BidResult]:
    """Deterministic selection: highest confidence among valid bid=true
    responses. Ties go to the earlier contractor in the fixed A/B/C
    order. Never looks at gold -- gold is not passed to this function."""
    candidates = [b for b in bids if b.parsed and b.bid]
    if not candidates:
        return None
    return max(candidates, key=lambda b: b.confidence)


def run_task(task: dict, contractors, temperature: float,
             log: Callable[[str], None]) -> tuple:
    """Run one task through announce -> bid -> award. Returns
    (outcome, message_count) where outcome is 'correct', 'misaward', or
    'unassigned'. gold is read only at the very end, for scoring."""
    log(f"\n=== TASK {task['id']} ===")
    log(f"desc: {task['desc']}")
    announcement = make_announcement(task)
    log(f"\nANNOUNCEMENT:\n{announcement}")

    messages = len(contractors)  # one announcement per contractor
    bids = collect_bids(contractors, announcement, temperature, log)
    messages += len(bids)        # one bid message per contractor response

    winner = select_winner(bids)
    messages += 1                 # one award message, win or no-bid

    if winner is None:
        log("\nAWARD: unassigned (no valid bid=true)")
        outcome = "unassigned"
    else:
        log(f"\nAWARD: {winner.contractor.label} "
            f"(role={winner.contractor.role}, confidence={winner.confidence})")
        outcome = "correct" if winner.contractor.role == task["gold"] else "misaward"

    log(f"GOLD: {task['gold']}")
    log(f"RESULT: {outcome.upper()}")
    return outcome, messages


def run_condition(condition: str, contractors, tasks, temperature: float,
                   log: Callable[[str], None]) -> dict:
    log(f"CONDITION: {condition}")
    log(f"MODEL: {MODEL}")
    log(f"TEMPERATURE: {temperature}")

    correct = unassigned = misawards = 0
    total_messages = 0
    for task in tasks:
        outcome, messages = run_task(task, contractors, temperature, log)
        total_messages += messages
        if outcome == "correct":
            correct += 1
        elif outcome == "unassigned":
            unassigned += 1
        else:
            misawards += 1

    log("\n=== RUN SUMMARY ===")
    log(f"tasks={len(tasks)} correct={correct} messages={total_messages} "
        f"unassigned={unassigned} misawards={misawards}")
    return {
        "tasks": len(tasks),
        "correct": correct,
        "messages": total_messages,
        "unassigned": unassigned,
        "misawards": misawards,
    }
