"""Generate the smart-home dataset with its answer key (steps 2b and 3).

Builds commands.csv from the MASSIVE en-US file in datasets/massive (run
download_massive.py first). Rows are picked, never edited: a command is kept
only if every argument it carries maps to a clear, closed option that Jev can
choose from. Each row gets the expected function call as its answer key.

Functions (each has at least one closed-set argument; options in FUNCTIONS):
  lights(action, room, color)   action: on / off / brighter / dimmer / color
  vacuum(room)                  MASSIVE has no "stop the vacuum" commands
  coffee(drink)                 espresso / cappuccino / latte / americano / regular
  plug(action)                  on / off
  speaker(action)               volume_up / volume_down / mute
  no_call                       unrelated commands

MASSIVE's iot test split has only 220 rows, so all partitions are used, with the
test partition preferred. All of MASSIVE is public, so the contamination caveat
applies either way.

Output columns: id, split (dev/test), partition, scenario, intent, utt, slots
(raw MASSIVE labels), function, expected_args (JSON, every argument filled in;
null or the API default when the command doesn't mention it) and expected_call
(readable form, defaults left out).

Run:  python generate_curated_dataset.py
"""

from __future__ import annotations

import inspect
import json
import random
import re
from collections import Counter
from pathlib import Path

import pandas as pd

from build_jev_questions import closed_sets
from smart_home_api import TOOLS

DATA_DIR = Path(__file__).parent / "datasets" / "massive"
SEED = 42
N_DEV = 50
N_TEST = 200

SLOT_PATTERN = re.compile(r"\[(\w+) : ([^\]]+)\]")
UNRELATED_SCENARIOS = ["weather", "news", "qa", "general", "datetime", "cooking"]

# How many commands to keep per (function, action). Total 250 with no_call.
QUOTAS = {
    ("lights", "off"): 30,
    ("lights", "on"): 12,
    ("lights", "brighter"): 18,
    ("lights", "dimmer"): 18,
    ("lights", "color"): 30,
    ("vacuum", "start"): 25,
    ("coffee", "make"): 25,
    ("plug", "off"): 14,
    ("plug", "on"): 13,
    ("speaker", "volume_up"): 12,
    ("speaker", "volume_down"): 12,
    ("speaker", "mute"): 11,
    ("no_call", "-"): 30,
}
# Share of each quota that should carry an explicit argument (room, colour, drink).
ARG_SHARE = 0.7

INTENT_TO_CALL = {
    "iot_hue_lightoff": ("lights", "off"),
    "iot_hue_lighton": ("lights", "on"),
    "iot_hue_lightup": ("lights", "brighter"),
    "iot_hue_lightdim": ("lights", "dimmer"),
    "iot_hue_lightchange": ("lights", "color"),
    "iot_cleaning": ("vacuum", "start"),
    "iot_coffee": ("coffee", "make"),
    "iot_wemo_off": ("plug", "off"),
    "iot_wemo_on": ("plug", "on"),
    "audio_volume_up": ("speaker", "volume_up"),
    "audio_volume_down": ("speaker", "volume_down"),
    "audio_volume_mute": ("speaker", "mute"),
}

# Raw MASSIVE value -> clear option. Values not listed here (e.g. "room",
# "my son's room", "carpets") make the row ambiguous, so it is dropped.
ROOMS = {
    "kitchen": "kitchen", "bedroom": "bedroom", "bed room": "bedroom",
    "bathroom": "bathroom", "living room": "living room", "garage": "garage",
    "porch": "porch", "office": "office", "patio": "patio", "balcony": "balcony",
    "hallway": "hallway", "hall": "hallway", "dining room": "dining room",
    "garden": "garden", "den": "den",
    "house": "all", "whole house": "all", "home": "all",
    "flat": "all", "apartment": "all",
}
COLORS = {"blue", "red", "green", "pink", "yellow", "orange", "white", "purple"}
DRINKS = {"espresso": "espresso", "cappuccino": "cappuccino", "capuccino": "cappuccino",
          "latte": "latte", "americano": "americano"}

# Commands that target the whole house without a house_place label
# ("switch on all the lights", "house lights blue") get room="all".
ALL_ROOMS_PATTERN = re.compile(r"\b(all|every)\b[\w\s]*\blights?\b|\b(house|home)\b")

# Target functions and the options of each argument come from the typed API
# (smart_home_api.py), shared with the Jev and LLM steps.
FUNCTIONS = {name: {arg: options for arg, (options, _) in closed_sets(fn).items()}
             for name, fn in TOOLS.items()}
# Value used when the command doesn't mention the argument: the API's default.
DEFAULTS = {name: {arg: p.default for arg, p in inspect.signature(fn).parameters.items()}
            for name, fn in TOOLS.items()}

# Free-value slots Jev can't fill (times, amounts, dates...): drop rows that have them.
FREE_SLOTS = {"time", "date", "change_amount", "general_frequency", "timeofday",
              "business_name", "business_type", "event_name", "song_name",
              "media_type", "player_setting", "place_name"}

# Words each function's commands must contain, so that noisy labels and
# off-topic devices (phone, wifi, tv...) are left out.
REQUIRED_WORDS = {
    "lights": r"\b(lights?|lamps?|lighting|bright\w*|dim\w*|darkness)\b",
    "vacuum": r"\b(vacuum\w*|roomba|hoover|cleaner|clean)\b",
    "coffee": r"\b(coffee|espresso|cappuccino|capuccino|latte|americano)\b",
    "plug": r"\b(plug|socket|wemo|outlet)\b",
    "speaker": r"\b(volume|mute|unmute|quiet|louder|loud|quieter|softer|silence|silent|hear)\b",
}
LIGHT_ACTION_WORDS = {
    "off": r"\b(off|out|shut|kill)\b",
    "on": r"\b(on|up)\b",
    "brighter": r"\b(bright\w*|more light|raise|increase|up)\b",
    "dimmer": r"\b(dim\w*|lower|down|decrease|darker|reduce)\b",
}

# Rows checked by hand and dropped: questions, compound or contradictory commands.
EXCLUDE_IDS = {
    "608",   # "unmute after" (labelled volume_up)
    "1510",  # "quiet mode on until i am home from work" (conditional)
    "3460",  # "quiet time" (vague)
    "2263",  # "show me the dim color" (vague)
    "1737",  # "lower the light of hall percent" (garbled)
    "5573",  # "set the brightness of lightness appropriately" (vague)
    "2836",  # "switch up the color of the lights" (labelled lightup, is a colour change)
    "2837",  # "change up the light colors at home" (same)
    "3428",  # "put the lights on the high setting" (on vs brighter)
    "1501",  # "all upstairs lights" (place not in the room options)
    "3464",  # "all the outdoor lights" (same)
    "678",   # "turn on the t. v. socket when i arrive home" (conditional)
    "2128",  # "color of light should be dimmed bright" (contradictory)
    "2233",  # "turn the lights on brighter" (on vs brighter)
}


def parse_slots(annot_utt: str) -> dict:
    return {name: value.strip().lower() for name, value in SLOT_PATTERN.findall(annot_utt)}


def arguments(function: str, action: str, slots: dict) -> dict | None:
    """Return the closed-set arguments of a command, or None if any are unclear."""
    if FREE_SLOTS & slots.keys():
        return None
    args = {}
    if "house_place" in slots:
        if function not in ("lights", "vacuum") or slots["house_place"] not in ROOMS:
            return None
        args["room"] = ROOMS[slots["house_place"]]
    if "color_type" in slots:
        if action != "color" or slots["color_type"] not in COLORS:
            return None
        args["color"] = slots["color_type"]
    if "coffee_type" in slots:
        if slots["coffee_type"] not in DRINKS:
            return None
        args["drink"] = DRINKS[slots["coffee_type"]]
    if function == "lights" and action == "color" and "color" not in args:
        return None  # "change the colour" with no colour is a clarify case, not a test row
    if function == "speaker" and "device_type" in slots:
        return None
    return args


def candidates(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for r in df.itertuples():
        if r.intent not in INTENT_TO_CALL or r.id in EXCLUDE_IDS:
            continue
        function, action = INTENT_TO_CALL[r.intent]
        utt = r.utt.lower()
        if re.search(r"\band\b", utt) or re.match(r"(how|what|did|is|are|why|when)\b", utt):
            continue
        if not re.search(REQUIRED_WORDS[function], utt):
            continue
        if function == "lights" and action in LIGHT_ACTION_WORDS \
                and not re.search(LIGHT_ACTION_WORDS[action], utt):
            continue
        slots = parse_slots(r.annot_utt)
        args = arguments(function, action, slots)
        if args is None:
            continue
        rows.append({"id": r.id, "partition": r.partition, "scenario": r.scenario,
                     "intent": r.intent, "function": function, "action": action,
                     "utt": r.utt, "slots": slots, "args": args, "has_arg": bool(args)})
    return pd.DataFrame(rows)


def answer_key(function: str, action: str, utt: str, args: dict) -> dict:
    """Every argument of the expected call, with defaults for the unmentioned ones."""
    if function == "no_call":
        return {}
    expected = {}
    for name in FUNCTIONS[function]:
        if name == "action":
            expected[name] = action
        elif name in args:
            expected[name] = args[name]
        elif name == "room" and ALL_ROOMS_PATTERN.search(utt.lower()):
            expected[name] = "all"
        else:
            expected[name] = DEFAULTS[function][name]
    for name, value in expected.items():
        assert value == DEFAULTS[function][name] or value in FUNCTIONS[function][name], \
            (utt, name, value)
    return expected


def format_call(function: str, args: dict) -> str:
    if function == "no_call":
        return "no_call"
    return TOOLS[function](**args)


def pick(pool: pd.DataFrame, n: int, rng: random.Random) -> pd.DataFrame:
    """Take n rows, ~ARG_SHARE of them with an explicit argument, test partition first."""
    rank = {"test": 0, "dev": 1, "train": 2}
    pool = pool.assign(_r=[rng.random() for _ in range(len(pool))],
                       _p=pool["partition"].map(rank))
    pool = pool.sort_values(["_p", "_r"])
    # One command per distinct utterance (MASSIVE has near-duplicate rows).
    pool = pool.drop_duplicates("utt")
    with_arg = pool[pool["has_arg"]]
    without = pool[~pool["has_arg"]]
    n_arg = min(len(with_arg), round(n * ARG_SHARE))
    chosen = pd.concat([with_arg.head(n_arg), without.head(n - n_arg)])
    if len(chosen) < n:  # top up from whichever side has rows left
        rest = pool.drop(chosen.index)
        chosen = pd.concat([chosen, rest.head(n - len(chosen))])
    if len(chosen) < n:
        print(f"  ! only {len(chosen)} usable rows for {pool.iloc[0][['function', 'action']].tolist()}")
    return chosen.drop(columns=["_r", "_p"])


def main() -> None:
    rng = random.Random(SEED)
    rows = [json.loads(line) for line in (DATA_DIR / "en-US.jsonl").open(encoding="utf-8")]
    df = pd.DataFrame(rows)

    pool = candidates(df)
    parts = []
    for (function, action), n in QUOTAS.items():
        if function == "no_call":
            continue
        parts.append(pick(pool[(pool["function"] == function) & (pool["action"] == action)], n, rng))

    # Unrelated commands: same sampling as step 2 (test split), so they stay comparable.
    test = df[df["partition"] == "test"]
    unrelated = test[test["scenario"].isin(UNRELATED_SCENARIOS)].sample(
        n=QUOTAS[("no_call", "-")], random_state=SEED)
    parts.append(pd.DataFrame({
        "id": unrelated["id"], "partition": "test", "scenario": unrelated["scenario"],
        "intent": "no_call", "function": "no_call", "action": "-",
        "utt": unrelated["utt"], "slots": [{} for _ in range(len(unrelated))],
        "args": [{} for _ in range(len(unrelated))], "has_arg": False}))

    commands = pd.concat(parts, ignore_index=True)

    # Stratified dev/test split: each (function, action) gets ~20% dev rows.
    commands = commands.sample(frac=1, random_state=SEED).reset_index(drop=True)
    commands["split"] = "test"
    share = N_DEV / len(commands)
    groups = commands.groupby(["function", "action"]).groups
    dev_counts = {k: round(len(ix) * share) for k, ix in groups.items()}
    # Fix rounding so the total is exactly N_DEV.
    biggest = sorted(groups, key=lambda k: -len(groups[k]))
    i = 0
    while sum(dev_counts.values()) != N_DEV:
        k = biggest[i % len(biggest)]
        dev_counts[k] += 1 if sum(dev_counts.values()) < N_DEV else -1
        i += 1
    for k, ix in groups.items():
        commands.loc[list(ix)[:dev_counts[k]], "split"] = "dev"

    commands = commands.sort_values(["split", "function", "action", "id"])  # "dev" < "test"
    keys = [answer_key(r.function, r.action, r.utt, r.args) for r in commands.itertuples()]
    commands["expected_call"] = [format_call(f, k) for f, k in zip(commands["function"], keys)]
    commands["expected_args"] = [json.dumps(k) for k in keys]
    commands["slots"] = commands["slots"].apply(json.dumps)
    commands = commands[["id", "split", "partition", "scenario", "intent", "utt", "slots",
                         "function", "expected_args", "expected_call"]]
    commands.to_csv("commands.csv", index=False)

    assert len(commands) == N_DEV + N_TEST, len(commands)
    print(f"Saved {len(commands)} commands to commands.csv "
          f"({(commands['split'] == 'dev').sum()} dev / {(commands['split'] == 'test').sum()} test)\n")
    print(pd.crosstab(commands["function"], commands["split"], margins=True), "\n")
    print("Source partitions:", Counter(commands["partition"]), "\n")
    print("Expected argument values:")
    values: dict[str, Counter] = {}
    for function, key in zip(commands["function"], keys):
        for name, value in key.items():
            values.setdefault(f"{function}.{name}", Counter())[value] += 1
    for name, counter in sorted(values.items()):
        print(f"  {name:<16} {sum(counter.values()):>3} | " + ", ".join(f"{v} ({n})" for v, n in counter.most_common()))


if __name__ == "__main__":
    main()
