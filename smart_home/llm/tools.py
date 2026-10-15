"""Tool declarations and system instruction for the LLM baseline, from jev/spec.json.

Standard native function calling, not Jev's fan-out: the model sees the five
functions as tools and either calls one or replies in text (= no call). It gets
the same wording Jev gets, placed where an LLM expects it:

  spec.json                          LLM request
  functions.<fn>.description     ->  tool description (verbatim)
  arguments.<arg>.question       ->  parameter description (verbatim) ...
  arguments.<arg>.options        ->  ... plus one line per described option;
                                     the option names become the JSON-schema enum
  router.question / no_call      ->  system instruction
  arguments.<arg>.stated         ->  not used: optional parameters (left out of
                                     "required") are the LLM's own way to say
                                     "only if mentioned"; the API default applies

Enums and required/optional come from the typed API (common/schema.py), the
same source as Jev's questions.

Run (from smart_home/):  python -m llm.tools   (writes llm/tools.json for review)
"""

from __future__ import annotations

import json

from common.api import TOOLS
from common.paths import LLM_TOOLS_PATH, ROOT, SPEC_PATH
from common.schema import OPTIONS
from jev.build_questions import check_spec

SYSTEM_INSTRUCTION = """\
You are the voice assistant of a smart home. {question} Answer by calling the \
one function that does it.
If it is {no_call}, do not call any function and reply in one short sentence.
Only fill an optional argument when the person says it; otherwise leave it out."""


def parameter_description(wording: dict) -> str:
    lines = [wording["question"]]
    lines += [f"{option}: {text}" for option, text in wording["options"].items() if text]
    return "\n".join(lines)


def build_tools(spec: dict) -> list[dict]:
    """One function declaration per API function (name, description, JSON-schema parameters)."""
    tools = []
    for name in TOOLS:
        wording = spec["functions"][name]
        properties, required = {}, []
        for arg, (options, optional) in OPTIONS[name].items():
            properties[arg] = {
                "type": "string",
                "enum": options,
                "description": parameter_description(wording["arguments"][arg]),
            }
            if not optional:
                required.append(arg)
        tools.append({
            "name": name,
            "description": wording["description"],
            "parameters": {"type": "object", "properties": properties, "required": required},
        })
    return tools


def system_instruction(spec: dict) -> str:
    router = spec["router"]
    return SYSTEM_INSTRUCTION.format(question=router["question"], no_call=router["no_call"])


def load() -> tuple[str, list[dict]]:
    spec = json.loads(SPEC_PATH.read_text())
    check_spec(spec)
    return system_instruction(spec), build_tools(spec)


def main() -> None:
    instruction, tools = load()
    LLM_TOOLS_PATH.write_text(json.dumps({"system_instruction": instruction, "tools": tools},
                                         indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {LLM_TOOLS_PATH.relative_to(ROOT)}: {len(tools)} tools\n")
    print(instruction, "\n")
    for tool in tools:
        params = tool["parameters"]
        args = ", ".join(a if a in params["required"] else f"{a}?" for a in params["properties"])
        print(f"  {tool['name']}({args})  {tool['description']}")


if __name__ == "__main__":
    main()
