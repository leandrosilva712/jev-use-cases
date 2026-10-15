"""The blog's results: Jev vs the LLM on the test commands, in four scenarios.

  1. Default cut-off      every "mentioned?" check at 0.5 (Jev's default), no confirmation
  2. Default cut-off      + asking "did you mean ...?" below a confidence
                            threshold, swept from 0.50 to 1.00 in steps of 0.05
  3. Tuned cut-off        the checks in jev.tune.TUNED_ARGUMENTS (the room checks)
                            tuned on the dev commands, the rest at 0.5, no confirmation
  4. Tuned cut-off        + the same threshold sweep

A cut-off is the P(yes) at which a "does the command mention X?" Noul counts
as yes. The threshold sweep is a what-if on the test commands, not a
tuning step: it shows how many calls would be made correctly, made wrongly, or
replaced by a question. The LLM (Gemini) has no cut-off and no confidence, so
it is the same in every scenario and has no gate.

Everything is computed from cached answers (results/jev/raw.json and
results/llm/test.jsonl): no API calls, and re-running gives the same files.

Writes results/report/:
  1_default_cutoff.md, 2_default_cutoff_gate.md, 3_tuned_cutoff.md,
  4_tuned_cutoff_gate.md, and report.md with all four
  jev_default-cutoff.jsonl, jev_tuned-cutoff.jsonl   Jev's predictions in each scenario
  <system>_..._mistakes.csv         the wrong calls behind each results table

Run (from smart_home/):  python -m evaluation.report
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from common.paths import COMMANDS_CSV, REPORT_DIR, RESULTS_DIR, ROOT
from evaluation.evaluate import fmt, gate_sweep, load, metrics, per_argument, per_function, score, \
    write_mistakes
from jev.assistant import MODEL as JEV_MODEL, RAW_PATH, load_raw, predictions
from jev.tune import DEFAULT_CUTOFF, STATED_CHECKS, cutoff_config, tune_cutoffs
from llm.assistant import MODEL as LLM_MODEL

SPLIT = "test"
THRESHOLDS = np.round(np.arange(0.50, 1.0001, 0.05), 2)
LLM_PATH = RESULTS_DIR / "llm" / f"{SPLIT}.jsonl"

JEV_SETUP = (f"Jev `{JEV_MODEL}`: one request per command with all 12 questions (speculative "
             "fan-out); the call is assembled from the answers that apply.")
LLM_SETUP = (f"LLM `{LLM_MODEL}`: native function calling, mode VALIDATED (calls constrained to "
             "the listed options), minimal thinking, no temperature; same wording as Jev "
             "(jev/spec.json). Not tuned, no cut-off, no confidence: identical in every scenario.")


def jev_scenario(commands: pd.DataFrame, raw: dict, cutoffs: dict[str, float], name: str,
                 out_dir: Path) -> pd.DataFrame:
    """Jev's test predictions at these per-check cut-offs (gate off), saved and scored."""
    records = predictions(commands, raw, cutoff_config(cutoffs))
    path = out_dir / f"jev_{name}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    s = score(commands, records)
    write_mistakes(s, path.with_name(f"{path.stem}_mistakes.csv"))
    return s


def describe_cutoffs(cutoffs: dict[str, float]) -> str:
    """'lights.room?, vacuum.room? at 0.25; lights.color?, coffee.drink? at 0.5 (default)'."""
    by_value: dict[float, list[str]] = {}
    for q in STATED_CHECKS:
        by_value.setdefault(cutoffs.get(q, DEFAULT_CUTOFF), []).append(q)
    return "; ".join(f"{', '.join(qs)} at {v}" + (" (default)" if v == DEFAULT_CUTOFF else " (tuned on dev)")
                     for v, qs in by_value.items())


def md(df: pd.DataFrame, **kwargs) -> str:
    return df.to_markdown(**kwargs)


def results_section(title: str, setup: list[str], jev: pd.DataFrame, llm: pd.DataFrame) -> str:
    jev_name, llm_name = f"Jev ({JEV_MODEL})", f"LLM ({llm['model'].iloc[0]})"
    table = pd.DataFrame({jev_name: {k: fmt(v) for k, v in metrics(jev).items()},
                          llm_name: {k: fmt(v) for k, v in metrics(llm).items()}})
    by_function = pd.concat([per_function(jev).rename("Jev"), per_function(llm).rename("LLM")], axis=1)
    by_argument = pd.concat([per_argument(jev).rename("Jev"), per_argument(llm).rename("LLM")], axis=1)
    mistakes = []
    for name, s in (("Jev", jev), ("LLM", llm)):
        wrong = s.loc[~s["call_ok"], ["utt", "expected_call", "call", "confidence", "weakest", "text"]]
        wrong = wrong.dropna(axis=1, how="all")
        mistakes.append(f"**{name}: {len(wrong)} wrong call{'' if len(wrong) == 1 else 's'}**\n\n"
                        + (md(wrong, index=False) if len(wrong) else "_none_"))
    return "\n\n".join([
        f"## {title}", "\n".join(f"- {line}" for line in setup),
        "### Results (test commands)", md(table),
        "### Right calls by function (%)", md(by_function.round(1)),
        "### Right arguments by argument (%), when the function is right", md(by_argument.round(1)),
        "### Wrong calls", *mistakes,
    ])


def gate_section(title: str, setup: list[str], jev: pd.DataFrame, llm: pd.DataFrame) -> str:
    sweep = gate_sweep(jev, THRESHOLDS)
    conf = jev["confidence"].astype(float)
    return "\n\n".join([
        f"## {title}", "\n".join(f"- {line}" for line in setup),
        f"### Jev with confirmation, by threshold ({len(jev)} test commands)", md(sweep, index=False),
        "\n".join([
            f"- Median call confidence: right calls {conf[jev['call_ok']].median():.2f}, "
            f"wrong calls {conf[~jev['call_ok']].median():.2f}.",
            f"- For reference, the LLM (no confidence, so no gate) acts on every command: "
            f"{int(llm['call_ok'].sum())} correctly, {int((~llm['call_ok']).sum())} wrongly.",
        ]),
    ])


def changed_rows(before: pd.DataFrame, after: pd.DataFrame) -> str:
    b, a = before.set_index("id"), after.set_index("id")
    ids = b.index[b["call_ok"] != a["call_ok"]]
    if not len(ids):
        return "No call changes between the default and the tuned cut-off."
    rows = pd.DataFrame({"command": b.loc[ids, "utt"], "expected": b.loc[ids, "expected_call"],
                         "default cut-off": b.loc[ids, "call"], "tuned cut-off": a.loc[ids, "call"]})
    return "Calls that change with the tuned cut-off:\n\n" + md(rows, index=False)


def build_report(raw: dict, out_dir: Path, source: str) -> dict[str, float]:
    """The four scenarios from Jev's cached answers `raw`, written to out_dir.

    `source` says where the answers come from (shown in the report header).
    Returns the tuned per-check cut-offs.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    commands = pd.read_csv(COMMANDS_CSV)
    dev, test = commands[commands["split"] == "dev"], commands[commands["split"] == SPLIT]
    missing = set(test["id"].astype(str)) - set(raw)
    if missing:
        raise SystemExit(f"{len(missing)} test rows not cached: run  python -m jev.assistant --split test")
    if not LLM_PATH.exists():
        raise SystemExit(f"{LLM_PATH.relative_to(ROOT)} missing: run  python -m llm.assistant --split test")

    llm = score(test, load(LLM_PATH))
    write_mistakes(llm, out_dir / f"llm_{SPLIT}_mistakes.csv")

    default = DEFAULT_CUTOFF
    tuned_cutoffs, sweeps = tune_cutoffs(dev, raw)
    jev_default = jev_scenario(test, raw, {}, "default-cutoff", out_dir)
    jev_tuned = jev_scenario(test, raw, tuned_cutoffs, "tuned-cutoff", out_dir)
    groups = ", ".join(f"{name} {s['cutoff']}" for name, s in sweeps.items())  # e.g. "room 0.25"

    gate_line = ("Confirmation: Jev asks \"did you mean ...?\" instead of acting when the call's "
                 "confidence (its least certain answer) is below the threshold. Swept on the test "
                 "commands as a what-if, not tuned.")
    tuning = [f"Tuning on the {len(dev)} dev commands (gate off). Checks are grouped by argument "
              "name and each group gets one cut-off: every value from 0.20 to 0.80, keep the most "
              f"right calls; ties go to the value closest to the default {default}. Checks not in a "
              f"group stay at {default}."]
    for name, sweep in sweeps.items():
        table = pd.DataFrame({"cut-off": [f"{c:.2f}" for c in sweep["dev_accuracy"]],
                              "right calls on dev": [f"{100 * a:.0f}%" for a in sweep["dev_accuracy"].values()]})
        tuning += [f"**Group `{name}`** ({', '.join(sweep['checks'])})",
                   md(table.set_index("cut-off").T, index=False), f"Chosen: **{sweep['cutoff']}**."]
    tuning = "\n\n".join(tuning + [f"Result: {describe_cutoffs(tuned_cutoffs)}."])

    sections = {
        "1_default_cutoff.md": results_section(
            f"1. Default cut-off ({default}), no confirmation",
            [JEV_SETUP, f"Cut-offs for \"does the command mention X?\": {describe_cutoffs({})}.",
             "Confirmation: off (every call is made).", LLM_SETUP],
            jev_default, llm),
        "2_default_cutoff_gate.md": gate_section(
            f"2. Default cut-off ({default}), asking \"did you mean ...?\" below a threshold",
            [f"Cut-off: {default} (default), as in scenario 1.", gate_line], jev_default, llm),
        "3_tuned_cutoff.md": results_section(
            f"3. Cut-off tuned on dev ({groups}), no confirmation",
            [JEV_SETUP, f"Cut-offs for \"does the command mention X?\": {describe_cutoffs(tuned_cutoffs)}.",
             "Confirmation: off (every call is made).", LLM_SETUP],
            jev_tuned, llm) + "\n\n### How the cut-off was tuned\n\n" + tuning
            + "\n\n" + changed_rows(jev_default, jev_tuned),
        "4_tuned_cutoff_gate.md": gate_section(
            f"4. Cut-off tuned on dev ({groups}), asking \"did you mean ...?\" below a threshold",
            [f"Cut-offs: {describe_cutoffs(tuned_cutoffs)}, as in scenario 3.", gate_line], jev_tuned, llm),
    }
    for name, text in sections.items():
        (out_dir / name).write_text(text + "\n")

    header = (f"# Jev vs LLM: smart-home function calling ({len(test)} test commands)\n\n"
              f"{source} LLM answers: {LLM_PATH.relative_to(ROOT)}. No API calls.\n")
    (out_dir / "report.md").write_text(header + "\n" + "\n\n".join(sections.values()) + "\n")

    print(f"Default cut-off {default}: Jev {jev_default['call_ok'].sum()}/{len(test)} right calls")
    print(f"Tuned cut-off ({groups}): Jev {jev_tuned['call_ok'].sum()}/{len(test)} right calls")
    print(f"LLM:                  {llm['call_ok'].sum()}/{len(test)} right calls")
    print(f"Wrote {out_dir.relative_to(ROOT)}/: {', '.join(sorted(p.name for p in out_dir.iterdir()))}")
    return tuned_cutoffs


def main() -> None:
    build_report(load_raw(), REPORT_DIR,
                 f"Generated by `python -m evaluation.report` from cached answers: Jev {RAW_PATH.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
