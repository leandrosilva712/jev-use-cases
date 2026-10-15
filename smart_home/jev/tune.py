"""Tune the cut-offs of chosen "mentioned?" checks on the dev rows only (no API calls).

A cut-off is the P(yes) at which a "does the command mention X?" Noul counts as
yes, so the argument is filled in; below it the API default stands. There are
four such checks: lights.room?, vacuum.room?, lights.color?, coffee.drink?.

TUNED_ARGUMENTS says which checks are tuned, by argument name: all checks for
that argument form one group ("room" -> lights.room? and vacuum.room?). Each
group gets one cut-off of its own, picked for the most right calls on dev with
the confidence gate off (ties go to the value closest to the 0.5 default);
every check not in a group keeps 0.5. Groups are tuned in order, each with the
previous groups' values in place.

The standard is to tune only the room checks: with the current wording Jev
underrates "a room was mentioned" for whole-home requests ("house lights",
"the flat"), while the colour and drink checks are never borderline
(no answer between 0.2 and 0.5 on any command), so tuning them changes nothing.
To tune another argument too, add it to TUNED_ARGUMENTS, e.g. ("room", "color").

Writes jev/config.json (the per-check cut-offs jev.assistant uses) and
results/jev/dev_mistakes.csv (the dev mistakes at the tuned cut-offs).

Run (from smart_home/):
  python -m jev.assistant --split dev   (fills the cache)
  python -m jev.tune
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from common.paths import COMMANDS_CSV, JEV_CONFIG_PATH, ROOT
from common.schema import OPTIONS
from evaluation.evaluate import score, write_mistakes
from jev.assistant import DEFAULT_CONFIG, MODEL, RESULTS_DIR, load_raw, predictions

CUTOFFS = np.round(np.arange(0.20, 0.801, 0.05), 2)
DEFAULT_CUTOFF = DEFAULT_CONFIG["stated_cutoff"]

# Every "mentioned?" check: one per optional argument, named "<function>.<argument>?".
STATED_CHECKS = tuple(f"{fn}.{arg}?" for fn, shapes in OPTIONS.items()
                      for arg, (_, optional) in shapes.items() if optional)

# Checks are grouped by argument name: every "*.room?" check shares one cut-off.
# Add "color" or "drink" here to tune those checks too (each as its own group).
TUNED_ARGUMENTS = ("room",)
TUNE_GROUPS = {arg: tuple(q for q in STATED_CHECKS if q.endswith(f".{arg}?")) for arg in TUNED_ARGUMENTS}


def cutoff_config(stated_cutoffs: dict[str, float]) -> dict:
    """Gate-off config: these per-check cut-offs, the default for every other check."""
    return {"stated_cutoff": DEFAULT_CUTOFF, "threshold": 0.0, "stated_cutoffs": dict(stated_cutoffs)}


def tune_cutoffs(dev: pd.DataFrame, raw: dict, groups: dict[str, tuple[str, ...]] = TUNE_GROUPS
                 ) -> tuple[dict[str, float], dict[str, dict]]:
    """({check: cut-off} for the tuned checks, {group: {checks, cutoff, dev accuracy per cut-off}})."""
    missing = set(dev["id"].astype(str)) - set(raw)
    if missing:
        raise SystemExit(f"{len(missing)} dev rows not cached: run  python -m jev.assistant --split dev")
    cutoffs, sweeps = {}, {}
    for name, checks in groups.items():
        unknown = set(checks) - set(STATED_CHECKS)
        assert not unknown, f"group {name}: unknown checks {unknown}; choose from {STATED_CHECKS}"
        accuracy = {}
        for c in CUTOFFS:
            s = score(dev, predictions(dev, raw, cutoff_config(cutoffs | {q: float(c) for q in checks})))
            accuracy[float(c)] = float(s["call_ok"].mean())
        best = max(accuracy.values())
        chosen = min((c for c, a in accuracy.items() if a == best), key=lambda c: abs(c - DEFAULT_CUTOFF))
        cutoffs |= {q: chosen for q in checks}
        sweeps[name] = {"checks": list(checks), "cutoff": chosen, "dev_accuracy": accuracy}
    return cutoffs, sweeps


def main() -> None:
    commands = pd.read_csv(COMMANDS_CSV)
    dev = commands[commands["split"] == "dev"]
    raw = load_raw()
    cutoffs, sweeps = tune_cutoffs(dev, raw)
    for name, sweep in sweeps.items():
        print(f"group {name} ({', '.join(sweep['checks'])}) -> right calls on dev (gate off)")
        print("  " + "  ".join(f"{c:.2f}:{100 * a:.0f}%" for c, a in sweep["dev_accuracy"].items()))
        print(f"  chosen {sweep['cutoff']} (ties: closest to {DEFAULT_CUTOFF})\n")
    untuned = [q for q in STATED_CHECKS if q not in cutoffs]
    print(f"Not tuned, kept at {DEFAULT_CUTOFF}: {', '.join(untuned) or 'none'}\n")
    save_tuning(dev, raw, cutoffs, sweeps, JEV_CONFIG_PATH, RESULTS_DIR / "dev_mistakes.csv")


def save_tuning(dev: pd.DataFrame, raw: dict, cutoffs: dict[str, float], sweeps: dict[str, dict],
                config_path: Path, mistakes_path: Path) -> None:
    """Write the config (per-check cut-offs) and the dev mistakes at those cut-offs."""
    config = {
        "model": MODEL, "stated_cutoff": DEFAULT_CUTOFF, "stated_cutoffs": cutoffs,
        "tuned": {name: {"checks": s["checks"], "cutoff": s["cutoff"],
                         "dev_right_calls": round(s["dev_accuracy"][s["cutoff"]], 4)}
                  for name, s in sweeps.items()},
        "tuned_on": f"dev ({len(dev)} rows)",
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Saved {config_path.relative_to(ROOT)}: stated_cutoffs {cutoffs}, others {DEFAULT_CUTOFF}")

    mistakes = write_mistakes(score(dev, predictions(dev, raw, cutoff_config(cutoffs))), mistakes_path)
    print(f"\nDev mistakes at the tuned cut-offs ({len(mistakes)}), saved to {mistakes_path.relative_to(ROOT)}:")
    print(mistakes[["utt", "expected_call", "call", "confidence", "weakest"]].to_string(index=False))


if __name__ == "__main__":
    main()
