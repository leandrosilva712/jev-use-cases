"""Generate Jev's questions from the typed API and the wording in spec.json.

Follows TypeSafe's function-calling cookbook:
  - closed_sets() reads each function's type hints and finds the arguments Jev
    can fill (Literal options); optional ones are those with a default.
  - spec.json holds the wording: a description per function, a question per
    argument, a line per option, and a "stated" yes/no check per optional
    argument (if the command doesn't mention it, the default stands).
  - Every command is sent with all the questions at once (speculative
    fan-out). The code later reads only the chosen function's answers.

Question ids:
  __tool__         choice  which function to call (or no_call)
  fn.arg           choice  the value of an argument
  fn.arg?          noul    does the command mention this optional argument?

Run:  python build_questions.py   (writes questions.json for review)
"""

from __future__ import annotations

import inspect
import json
import typing
from pathlib import Path

from smart_home_api import NO_CALL, TOOLS

SPEC_PATH = Path(__file__).with_name("spec.json")
QUESTIONS_PATH = Path(__file__).with_name("questions.json")
ROUTE = "__tool__"


def closed_sets(fn) -> dict[str, tuple[list[str], bool]]:
    """{argument: (options, optional)} for every Literal argument of fn."""
    hints = typing.get_type_hints(fn)
    params = inspect.signature(fn).parameters
    shapes = {}
    for name, hint in hints.items():
        if name == "return":
            continue
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        if typing.get_origin(hint) is typing.Union and len(args) == 1:
            hint = args[0]  # Optional[Literal[...]]
        if typing.get_origin(hint) is not typing.Literal:
            continue  # free values (numbers, text...) get no question
        optional = params[name].default is not inspect.Parameter.empty
        shapes[name] = (list(typing.get_args(hint)), optional)
    return shapes


def check_spec(spec: dict) -> None:
    """The spec must word every function, argument and option of the API, and nothing else."""
    assert set(spec["functions"]) == set(TOOLS), "spec functions differ from the API"
    for name, fn in TOOLS.items():
        arguments = spec["functions"][name]["arguments"]
        shapes = closed_sets(fn)
        assert set(arguments) == set(shapes), f"{name}: spec arguments differ from the API"
        for arg, (options, optional) in shapes.items():
            spec_options = arguments[arg]["options"]
            assert set(spec_options) == set(options), \
                f"{name}.{arg}: options {sorted(spec_options)} != API {sorted(options)}"
            assert ("stated" in arguments[arg]) == optional, \
                f"{name}.{arg}: optional arguments need a 'stated' check, required ones none"


def build_questions(spec: dict | None = None) -> dict:
    spec = spec or json.loads(SPEC_PATH.read_text())
    check_spec(spec)

    questions = {
        ROUTE: {
            "type": "choice",
            "instructions": spec["router"]["question"],
            "criteria": {name: spec["functions"][name]["description"] for name in TOOLS}
                        | {NO_CALL: spec["router"]["no_call"]},
        }
    }
    for name, fn in TOOLS.items():
        arguments = spec["functions"][name]["arguments"]
        for arg, (options, optional) in closed_sets(fn).items():
            wording = arguments[arg]
            questions[f"{name}.{arg}"] = {
                "type": "choice",
                "instructions": wording["question"],
                # API order, so option order is the same for every request
                "criteria": {option: wording["options"][option] for option in options},
            }
            if optional:
                stated = wording["stated"]
                questions[f"{name}.{arg}?"] = {
                    "type": "noul",
                    "instructions": stated["question"],
                    "criteria": {"true": stated["true"], "false": stated["false"]},
                }
    return questions


def main() -> None:
    questions = build_questions()
    QUESTIONS_PATH.write_text(json.dumps(questions, indent=2) + "\n")

    print(f"{len(questions)} questions per command, written to {QUESTIONS_PATH.name}:")
    for qid, q in questions.items():
        n = f"{len(q['criteria'])} options" if q["type"] == "choice" else "yes/no"
        print(f"  {qid:<16}{q['type']:<8}{n:<12}{q['instructions']}")
    chars = len(json.dumps(questions))
    print(f"\n~{chars // 4:,} tokens of questions per request (rough: 4 characters per token)")


if __name__ == "__main__":
    main()
