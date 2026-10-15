"""Score function-calling predictions against the answer key in commands.csv.

Every system (Jev, the LLM baseline...) writes results/<system>/<split>.jsonl
with one record per command:
  id, system, model, function, args, clarify, latency_s, input_tokens,
  output_tokens, invalid, error
`function`/`args` are the call the system would make; `confidence` is Jev's
call confidence (none for the LLM).

Metrics, all on the same rows (metrics()):
  - right function, right call (function + every argument), right arguments
    given the right device, no_call on unrelated commands
  - invalid calls, latency (typical and slowest), tokens and cost per 1,000
    commands from the vendors' list prices
The confidence gate ("did you mean ...?" below a threshold) is evaluated
separately by gate_sweep(): acted correctly / acted wrongly / asked, per
threshold. evaluation/report.py builds the blog's four scenarios from these.

Run (from smart_home/):
  python -m evaluation.evaluate --split test            (every results/*/test.jsonl)
  python -m evaluation.evaluate results/jev/dev.jsonl   (specific files)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from common.api import NO_CALL, TOOLS
from common.paths import COMMANDS_CSV, RESULTS_DIR, ROOT
from common.schema import DEFAULTS, OPTIONS

# USD per token (input, output), list prices; matched by model-name prefix.
PRICING = {
    "jev-": (42 / 1e9, 0.0),                              # $42 per billion input, output free
    "gemini-3.5-flash-lite": (0.30 / 1e6, 2.50 / 1e6),  # paid tier; thinking tokens bill as output
}


def normalise(function: str, args: dict) -> tuple[dict, bool]:
    """Fill omitted optional arguments with the API default; flag calls the API would reject."""
    if function == NO_CALL:
        return {}, bool(args)
    if function not in TOOLS:
        return dict(args), True
    full, invalid = {}, set(args) - set(OPTIONS[function]) != set()
    for arg, (options, optional) in OPTIONS[function].items():
        if arg in args and args[arg] is not None:
            full[arg] = args[arg]
            invalid |= args[arg] not in options
        elif optional:
            full[arg] = DEFAULTS[function][arg]
        else:
            full[arg], invalid = None, True  # required argument missing
    return full, invalid


def price(model: str) -> tuple[float, float]:
    for prefix, rates in PRICING.items():
        if model.startswith(prefix):
            return rates
    raise KeyError(f"No price for model {model!r}: add it to PRICING")


def score(commands: pd.DataFrame, records: list[dict]) -> pd.DataFrame:
    """One row per command with the prediction and what it got right."""
    key = commands.set_index("id")
    rows = []
    for r in records:
        expected = key.loc[r["id"]]
        expected_args = json.loads(expected["expected_args"])
        args, invalid = normalise(r["function"], r.get("args") or {})
        invalid |= bool(r.get("invalid"))
        function_ok = r["function"] == expected["function"]
        rows.append({
            "id": r["id"], "utt": expected["utt"], "expected_call": expected["expected_call"],
            "expected_function": expected["function"], "function": r["function"], "args": args,
            "call": r.get("call"), "function_ok": function_ok,
            "args_ok": function_ok and not invalid and args == expected_args,
            "arg_hits": {a: args.get(a) == v for a, v in expected_args.items()} if function_ok else {},
            "clarify": bool(r.get("clarify")), "confidence": r.get("confidence"),
            "weakest": r.get("weakest"), "text": r.get("text"),
            "invalid": invalid, "error": r.get("error"),
            "latency_s": r["latency_s"], "input_tokens": r["input_tokens"] or 0,
            "output_tokens": r["output_tokens"] or 0, "model": r["model"],
        })
    scored = pd.DataFrame(rows)
    scored["call_ok"] = scored["args_ok"]  # right function and every argument right
    return scored


def metrics(s: pd.DataFrame) -> dict:
    device = s[s["expected_function"] != NO_CALL]
    unrelated = s[s["expected_function"] == NO_CALL]
    right_fn_device = device[device["function_ok"]]
    rate_in, rate_out = price(s["model"].iloc[0])
    cost = (s["input_tokens"] * rate_in + s["output_tokens"] * rate_out).mean() * 1000
    pct = lambda part, whole: 100 * len(part) / len(whole) if len(whole) else float("nan")
    return {
        "Commands": len(s),
        "Right function %": 100 * s["function_ok"].mean(),
        "Right call (function + args) %": 100 * s["call_ok"].mean(),
        "Right args, given right device %": 100 * right_fn_device["args_ok"].mean(),
        "Unrelated -> no_call %": 100 * unrelated["function_ok"].mean(),
        "Device command -> no_call %": pct(device[device["function"] == NO_CALL], device),
        "Invalid calls": int(s["invalid"].sum()),
        "Errors": int(s["error"].notna().sum()),
        "Latency p50 (ms)": 1000 * s["latency_s"].median(),
        "Latency p95 (ms)": 1000 * s["latency_s"].quantile(0.95),
        "Latency max (ms)": 1000 * s["latency_s"].max(),
        "Input tokens / command": s["input_tokens"].mean(),
        "Output tokens / command": s["output_tokens"].mean(),
        "Cost per 1,000 commands ($)": cost,
    }


def gate_sweep(s: pd.DataFrame, thresholds) -> pd.DataFrame:
    """What the confidence gate does at each threshold: below it, ask instead of acting.

    `s` is scored with the gate off (every call made). The first row is the gate off.
    """
    conf = s["confidence"].astype(float)
    ok = s["call_ok"]
    n_wrong = int((~ok).sum())
    rows = [{"threshold": "off", "acted correctly": int(ok.sum()), "acted wrongly": n_wrong,
             "asked (did you mean...?)": 0, "asked, call was right": 0, "asked, call was wrong": 0,
             "wrong calls caught": f"0 of {n_wrong}"}]
    for t in thresholds:
        ask = conf < t
        rows.append({
            "threshold": f"{t:.2f}",
            "acted correctly": int((~ask & ok).sum()),
            "acted wrongly": int((~ask & ~ok).sum()),
            "asked (did you mean...?)": int(ask.sum()),
            "asked, call was right": int((ask & ok).sum()),
            "asked, call was wrong": int((ask & ~ok).sum()),
            "wrong calls caught": f"{int((ask & ~ok).sum())} of {n_wrong}",
        })
    return pd.DataFrame(rows)


def per_function(s: pd.DataFrame) -> pd.Series:
    return (100 * s.groupby("expected_function")["call_ok"].mean()).rename("right call %")


def per_argument(s: pd.DataFrame) -> pd.Series:
    hits = [(f"{fn}.{a}", ok) for fn, h in zip(s["expected_function"], s["arg_hits"]) for a, ok in h.items()]
    return (100 * pd.DataFrame(hits, columns=["arg", "ok"]).groupby("arg")["ok"].mean()).rename("right %")


MISTAKE_COLUMNS = ["id", "utt", "expected_call", "call", "text", "confidence", "weakest", "invalid", "error"]


def write_mistakes(s: pd.DataFrame, out: Path) -> pd.DataFrame:
    mistakes = s.loc[~s["call_ok"], MISTAKE_COLUMNS]
    mistakes.to_csv(out, index=False)
    return mistakes


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def fmt(value) -> str:
    if isinstance(value, float):
        if pd.isna(value):
            return "–"
        return "0" if value == 0 else f"{value:.4f}" if abs(value) < 1 else f"{value:.1f}"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--split", default="test")
    a = parser.parse_args()
    files = [p.resolve() for p in a.files] or sorted(RESULTS_DIR.glob(f"*/{a.split}.jsonl"))
    if not files:
        raise SystemExit(f"No results/*/{a.split}.jsonl files yet")

    commands = pd.read_csv(COMMANDS_CSV)
    table, extra = {}, []
    for path in files:
        records = load(path)
        name = f"{records[0]['system']} ({records[0]['model']})"
        s = score(commands, records)
        table[name] = {k: fmt(v) for k, v in metrics(s).items()}
        extra.append(f"### {name}\n\n" + pd.concat([per_function(s)], axis=1).round(1).to_markdown()
                     + "\n\n" + per_argument(s).round(1).to_frame().to_markdown())
        write_mistakes(s, path.with_name(path.stem + "_mistakes.csv"))

    summary = pd.DataFrame(table)
    shown = [str(p.relative_to(RESULTS_DIR)) for p in files]
    report = f"## Results ({', '.join(shown)})\n\n" + summary.to_markdown() \
        + "\n\n" + "\n\n".join(extra) + "\n"
    print(report)
    tag = a.split if not a.files else "_".join(f"{p.parent.name}-{p.stem}" for p in files)
    out = RESULTS_DIR / f"summary_{tag}.md"
    out.write_text(report)
    print(f"Saved {out.relative_to(ROOT)}; mistakes in results/<system>/<split>_mistakes.csv")


if __name__ == "__main__":
    main()
