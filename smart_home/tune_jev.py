"""Tune Jev's two knobs on the dev rows only, from the cached answers (no API calls).

  1. stated_cutoff: P(yes) at which a "does the command mention X?" check counts
     as yes. Picked for the most right calls (ties: closest to 0.5).
  2. threshold: confidence below which Jev asks "did you mean ...?" instead of
     acting. Picked to maximise  right actions - WRONG_COST x wrong actions;
     asking costs 0. With WRONG_COST = 1, acting wrongly undoes one right
     action. Ties go to the lower threshold (fewer questions to the user).

Writes jev_config.json, which jev_assistant.py uses for the test run.

Run:  python jev_assistant.py --split dev   (fills the cache)
      python tune_jev.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from evaluate import score
from jev_assistant import CONFIG_PATH, HERE, MODEL, load_raw, predictions

WRONG_COST = 1.0
CUTOFFS = np.round(np.arange(0.20, 0.801, 0.05), 2)
THRESHOLDS = np.round(np.arange(0.0, 0.951, 0.025), 3)


def main() -> None:
    commands = pd.read_csv(HERE / "commands.csv")
    dev = commands[commands["split"] == "dev"]
    raw = load_raw()
    missing = set(dev["id"].astype(str)) - set(raw)
    if missing:
        raise SystemExit(f"{len(missing)} dev rows not cached: run  python jev_assistant.py --split dev")

    def scored(cutoff: float, threshold: float) -> pd.DataFrame:
        config = {"stated_cutoff": cutoff, "threshold": threshold}
        return score(dev, predictions(dev, raw, config))

    # 1. stated_cutoff, before any gate
    accuracy = {c: scored(c, 0.0)["call_ok"].mean() for c in CUTOFFS}
    best = max(accuracy.values())
    cutoff = float(min((c for c in CUTOFFS if accuracy[c] == best), key=lambda c: abs(c - 0.5)))
    print("stated_cutoff -> right calls on dev (no gate)")
    print("  " + "  ".join(f"{c:.2f}:{100 * a:.0f}%" for c, a in accuracy.items()))
    print(f"  chosen {cutoff}\n")

    # 2. threshold, with that cutoff
    s = scored(cutoff, 0.0)
    rows = []
    for t in THRESHOLDS:
        act = s["confidence"] >= t
        right, wrong = (act & s["call_ok"]).sum(), (act & ~s["call_ok"]).sum()
        rows.append({"threshold": t, "acted right": right, "acted wrong": wrong,
                     "clarify": (~act).sum(), "clarify were wrong": (~act & ~s["call_ok"]).sum(),
                     "utility": right - WRONG_COST * wrong})
    sweep = pd.DataFrame(rows)
    threshold = float(sweep.loc[sweep["utility"].idxmax(), "threshold"])  # first max = lowest
    print(f"threshold sweep on {len(dev)} dev rows (utility = right - {WRONG_COST} x wrong)")
    print(sweep[sweep["threshold"].isin(THRESHOLDS[::2]) | (sweep["threshold"] == threshold)]
          .to_string(index=False))
    print(f"  chosen {threshold}\n")

    chosen = sweep[sweep["threshold"] == threshold].iloc[0]
    config = {
        "model": MODEL, "stated_cutoff": cutoff, "threshold": threshold,
        "tuned_on": f"dev ({len(dev)} rows)", "wrong_cost": WRONG_COST,
        "dev_right_calls_no_gate": round(float(accuracy[cutoff]), 4),
        "dev_after_gate": {k: int(chosen[k]) for k in ("acted right", "acted wrong", "clarify")},
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Saved {CONFIG_PATH.name}: {config}")

    weak = s[~s["call_ok"]][["utt", "expected_call", "call", "confidence"]]
    print(f"\nDev mistakes before the gate ({len(weak)}):")
    print(weak.sort_values("confidence").to_string(index=False))


if __name__ == "__main__":
    main()
