"""Jev as a smart-home function caller.

One request per command with every question in questions.json at once
(speculative fan-out, as in TypeSafe's function-calling cookbook). The code
then assembles the call from the answers that apply:

  1. __tool__ picks the function (or no_call).
  2. Required arguments take the chosen option of fn.arg.
  3. Optional arguments take fn.arg only if the "stated" check fn.arg? says the
     command mentions them (P(yes) >= that check's cut-off); otherwise the API
     default. Each check uses stated_cutoffs[check] if set, else stated_cutoff.
  4. The call's confidence is its least certain judgement: the Choice
     confidence of each choice read, |2p - 1| for each stated check read.
  5. Confidence gate: below `threshold`, ask "did you mean ...?" (clarify)
     instead of acting.

stated_cutoff defaults to 0.5; jev/tune.py tunes chosen checks on the dev rows
only (by default the room checks) and stores them as stated_cutoffs in
jev/config.json. The threshold defaults to 0 (gate off);
evaluation/report.py sweeps it from 0.5 to 1 to show the trade-off.

Run (from smart_home/):
  python -m jev.assistant --split dev   (calls Jev for rows not cached yet,
                                         then writes results/jev/dev.jsonl)
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
from typesafe_sdk import RetryPolicy, TypeSafeClient

from common.api import NO_CALL, TOOLS
from common.paths import COMMANDS_CSV, JEV_CONFIG_PATH, QUESTIONS_PATH, ROOT, load_env, system_results
from common.schema import DEFAULTS, closed_sets
from jev.build_questions import ROUTE

SYSTEM = "jev"
RESULTS_DIR = system_results(SYSTEM)
RAW_PATH = RESULTS_DIR / "raw.json"

MODEL = "jev-1.13.0"  # pinned so answers don't change mid-test
DEFAULT_CONFIG = {"model": MODEL, "stated_cutoff": 0.5, "stated_cutoffs": {}, "threshold": 0.0}


@dataclass
class Call:
    function: str
    args: dict
    confidence: float
    weakest: str  # question id of the least certain judgement
    judgements: dict = field(default_factory=dict)  # question id -> confidence
    clarify: bool = False

    def __str__(self) -> str:
        return NO_CALL if self.function == NO_CALL else TOOLS[self.function](**self.args)


def load_config() -> dict:
    if JEV_CONFIG_PATH.exists():
        return DEFAULT_CONFIG | json.loads(JEV_CONFIG_PATH.read_text())
    return dict(DEFAULT_CONFIG)


def assemble(answers: dict, stated_cutoff: float, threshold: float,
             stated_cutoffs: dict[str, float] | None = None) -> Call:
    """Build the function call from Jev's raw answers ({question id: answer dict}).

    stated_cutoffs overrides the cut-off for specific checks, e.g. {"lights.room?": 0.25}.
    """
    stated_cutoffs = stated_cutoffs or {}
    route = answers[ROUTE]
    judgements = {ROUTE: route["confidence"]}
    function = route["choice"]
    args = {}
    if function != NO_CALL:
        for arg, (_, optional) in closed_sets(TOOLS[function]).items():
            qid = f"{function}.{arg}"
            if optional:
                p = answers[f"{qid}?"]["noul"]
                judgements[f"{qid}?"] = abs(2 * p - 1)
                if p < stated_cutoffs.get(f"{qid}?", stated_cutoff):
                    args[arg] = DEFAULTS[function][arg]
                    continue
            args[arg] = answers[qid]["choice"]
            judgements[qid] = answers[qid]["confidence"]
    weakest = min(judgements, key=judgements.get)
    confidence = judgements[weakest]
    return Call(function, args, confidence, weakest, judgements, clarify=confidence < threshold)


class JevAssistant:
    def __init__(self, model: str = MODEL):
        load_env()  # TYPESAFE_API_KEY
        self.model = model
        self.questions = json.loads(QUESTIONS_PATH.read_text())
        self.client = TypeSafeClient(model=model, retry=RetryPolicy(max_retries=3))

    def ask(self, command: str) -> dict:
        """Send one command; return the raw answers with latency and token usage."""
        start = time.perf_counter()
        response = self.client.system_one(state=command, questions=self.questions, model=self.model)
        latency = time.perf_counter() - start
        dumped = response.model_dump(mode="json")
        return {
            "utt": command,
            "model": response.model,
            "answers": dumped["answers"],
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "latency_s": round(latency, 4),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def warm_up(self) -> None:
        """Open the connection first, so the first timed request isn't a cold start."""
        self.client.system_one(state="hello", questions={"w": {"type": "noul", "instructions": "Is this a greeting?"}},
                               model=self.model)


def load_raw() -> dict:
    return json.loads(RAW_PATH.read_text()) if RAW_PATH.exists() else {}


def run(commands: pd.DataFrame) -> dict:
    """Ask Jev about every command not cached yet. The cache is saved after each request."""
    raw = load_raw()
    todo = commands[~commands["id"].astype(str).isin(raw)]
    if len(todo):
        jev = JevAssistant()
        jev.warm_up()
        for i, row in enumerate(todo.itertuples(), 1):
            raw[str(row.id)] = jev.ask(row.utt)
            RAW_PATH.write_text(json.dumps(raw, indent=1))
            print(f"  [{i}/{len(todo)}] {raw[str(row.id)]['latency_s'] * 1000:6.0f} ms  {row.utt}")
    print(f"{len(commands) - len(todo)} cached, {len(todo)} requested")
    return raw


def predictions(commands: pd.DataFrame, raw: dict, config: dict) -> list[dict]:
    """Records in the shared format read by evaluate.py."""
    records = []
    for row in commands.itertuples():
        r = raw[str(row.id)]
        call = assemble(r["answers"], config["stated_cutoff"], config["threshold"], config.get("stated_cutoffs"))
        records.append({
            "id": row.id, "split": row.split, "system": SYSTEM, "model": r["model"],
            "function": call.function, "args": call.args, "call": str(call),
            "clarify": call.clarify, "confidence": round(call.confidence, 4), "weakest": call.weakest,
            "latency_s": r["latency_s"], "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"], "invalid": False, "error": None,
        })
    return records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    split = parser.parse_args().split

    commands = pd.read_csv(COMMANDS_CSV)
    if split != "all":
        commands = commands[commands["split"] == split]
    raw = run(commands)
    config = load_config()
    out = RESULTS_DIR / f"{split}.jsonl"
    out.write_text("".join(json.dumps(p) + "\n" for p in predictions(commands, raw, config)))
    print(f"Wrote {out.relative_to(ROOT)} (cut-offs {config['stated_cutoffs']}, others {config['stated_cutoff']}; "
          f"threshold {config['threshold']})")


if __name__ == "__main__":
    main()
