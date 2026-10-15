"""Draft spec.json (the wording of Jev's questions) from the API alone.

TypeSafe's function-calling cookbook: the structure of the questions comes from
the type hints, the wording from spec.json, and "an LLM can write it for you
from the signatures". This script builds that prompt from the source of
smart_home_api.py, so the LLM sees only the API, never the dataset, and the
wording can't be tuned to the test commands.

The shape of spec.json is a JSON Schema generated from the API (spec_schema):
every function, argument and option is a required key, nothing else is allowed.
Claude (MODEL) returns the spec as its reply, constrained by structured outputs
(output_config.format, type "json_schema"), so the API guarantees the reply is
valid JSON that matches that schema.

If the API can't be used (no SDK, no credentials, an API error, a refusal or a
truncated reply), the script falls back to writing the prompt to spec_prompt.txt
and copying it to the clipboard, to paste into a fresh Claude chat in the browser.

Run:
  python generate_spec.py                  ask Claude, or fall back to the prompt file
  python generate_spec.py --prompt-only    just write spec_prompt.txt (and copy it)
  python generate_spec.py --check FILE     check a JSON reply pasted from the browser
                                           and write spec.json
Then run build_questions.py.
"""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path

import jsonschema

import smart_home_api
from build_questions import SPEC_PATH, check_spec, closed_sets
from smart_home_api import NO_CALL, TOOLS

MODEL = "claude-opus-5-5"
EFFORT = "high"
PROMPT_PATH = Path(__file__).with_name("spec_prompt.txt")
REPLY_PATH = Path(__file__).with_name("spec_reply.json")  # raw JSON reply, kept for the record
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

PROMPT = """\
You are writing the wording for Jev, a decision model from TypeSafe that fills
function calls for a voice assistant. Jev generates no text. For every command
it receives the command text plus a set of questions, and for each question it
picks one of the options you describe (Choice) or gives the probability of yes
(Noul). Your wording is the only thing Jev knows about the API: it never sees
parameter names, question ids or this prompt.

## The API

```python
{source}
```

## How Jev reads your wording

- The command is a raw voice transcript: lowercase, no punctuation, sometimes
  with a wake word or filler, often indirect rather than a direct instruction.
- Jev reads each question and option literally and makes a quick judgement,
  like a person glancing at the words. It understands paraphrase on its own:
  you do not need to list the ways users might phrase something.
- What Jev needs from an option is its scope: a precise, self-contained
  definition of what that value is. When each option is defined exactly,
  options that sit close together separate naturally, without one having to
  mention or deny another.
- Extra words cost accuracy. Long lists of phrasings, exclusions ("Not ...")
  and references to other options blur the scope and make options overlap.

## What to write

Follow the style of TypeSafe's function-calling cookbook: short, plain, lower
case phrases, no full stops, no colons, no lists of phrasings, no "Not ..."
clauses, and no option that mentions another option.

- "router.question": one short question saying who is speaking and to what
  kind of assistant, and asking what they want it to do.
- function "description": what the function does, as a short verb phrase of
  about 4 to 10 words. Name the device the way users do; one alternative name
  (a brand or nickname) is fine.
- "router.{no_call}": a short phrase for commands that need no function, such
  as a question or small talk.
- "question" per argument: a short, specific question about what the user
  wants, never using the parameter name. When there are only a few options,
  it can name them ("does the user want ..., ... or ...?").
- "options": a noun phrase of about 3 to 12 words defining what the value is.
  Give the core meaning precisely; at most one alternative name for the same
  thing ("a candlestick or OHLC chart"). Word sibling options in parallel, so
  the difference is in the definitions themselves ("a fast one" / "a slow
  one"). Use null when the name alone is already a precise definition (a
  colour like "red", a room like "kitchen").
- "stated", only for arguments with a default: a yes/no question asking
  whether the user says anything about that argument at all. If not, the
  default is used. This question is where examples belong: end it with "such
  as ..." and two to four typical values, including the one meaning "all",
  when there is one. "true" and "false" are short phrases saying what yes and
  no mean; "true" is always the yes case.
- When several functions share an argument type, keep its options consistent,
  adapting each line to what that device acts on (a room for one device may
  mean all of its units for another).
- Plain British English.

Before writing, think about how users really ask for each value and which
values are easiest to confuse, then choose the few words that define each
value's scope exactly. Put that thinking into the definitions, not into lists.

## Example, for a different API (a car assistant)

```python
def windows(
    action: Literal["open", "close", "vent"],
    seat: Optional[Literal["driver", "passenger", "rear left", "rear right", "all"]] = None,
) -> str:
    \"\"\"Open or close the car windows.\"\"\"
```

Too little, which gives Jev nothing to go on:

  "vent": "Vent mode."
  "all": "All seats."

Too much, which blurs the scope:

  "vent": "Open it only a little for air: crack it, a bit of fresh air, it's
           stuffy in here. Not fully open like the open option."

The style to follow:

{example}

## Your output

{output}
"""

# Style example from an unrelated domain, so the prompt never hints at the
# smart-home test commands. Worded like the cookbook's spec.json.
EXAMPLE = {
    "router": {
        "question": "What is the driver asking the car assistant to do?",
        NO_CALL: "something other than a car function, such as a question or small talk",
    },
    "functions": {"windows": {
        "description": "open or close the car windows",
        "arguments": {
            "action": {
                "question": "Does the driver want the window opened, closed or opened slightly?",
                "options": {
                    "open": "the window opened all the way",
                    "close": "the window shut",
                    "vent": "the window opened slightly, for a little fresh air",
                },
            },
            "seat": {
                "question": "Which window does the driver mean?",
                "stated": {
                    "question": "Does the driver say which window, such as their own, "
                                "the passenger's, a back one or all of them?",
                    "true": "names a window or all the windows",
                    "false": "does not say which window",
                },
                "options": {
                    "driver": "the driver's own window",
                    "passenger": "the front passenger's window",
                    "rear left": "the back window on the left",
                    "rear right": "the back window on the right",
                    "all": "every window in the car",
                },
            },
        },
    }},
}
# The API enforces the schema, so the prompt only names the output.
OUTPUT_STRUCTURED = "Reply with the complete spec as JSON."
OUTPUT_JSON = "Return only JSON that matches this JSON Schema:\n\n{schema}"


def _object(properties: dict) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def spec_schema() -> dict:
    """JSON Schema of spec.json, derived from the API's functions and options."""
    text = {"type": "string"}
    text_or_null = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    functions = {}
    for name, fn in TOOLS.items():
        arguments = {}
        for arg, (options, optional) in closed_sets(fn).items():
            entry = {"question": text}
            if optional:
                entry["stated"] = _object({"question": text, "true": text, "false": text})
            entry["options"] = _object({option: text_or_null for option in options})
            arguments[arg] = _object(entry)
        functions[name] = _object({"description": text, "arguments": _object(arguments)})
    return _object({
        "router": _object({"question": text, NO_CALL: text}),
        "functions": _object(functions),
    })


def build_prompt(output: str) -> str:
    return PROMPT.format(source=inspect.getsource(smart_home_api).strip(),
                         no_call=NO_CALL, output=output,
                         example=json.dumps(EXAMPLE, indent=2))


def ask_claude() -> dict:
    """Ask Claude for the spec; structured outputs make the API enforce the schema."""
    import anthropic
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE)  # ANTHROPIC_API_KEY in env
    client = anthropic.Anthropic()
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        thinking={"type": "adaptive"},
        output_config={
            "effort": EFFORT,
            # Constrained decoding: the text reply is valid JSON matching spec_schema().
            "format": {"type": "json_schema", "schema": spec_schema()},
        },
        # If a safety classifier declines, the API reruns the request on a fallback model.
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": build_prompt(OUTPUT_STRUCTURED)}],
    ) as stream:
        response = stream.get_final_message()
    # A refusal or a max_tokens cut can leave the JSON incomplete, so only end_turn counts.
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"no complete spec (stop_reason={response.stop_reason!r})")
    text = "".join(b.text for b in response.content if b.type == "text")
    return json.loads(text)


def save_spec(spec: dict, source: str) -> None:
    SPEC_PATH.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {SPEC_PATH.name} ({source})")


def write_prompt() -> None:
    prompt = build_prompt(OUTPUT_JSON.format(schema=json.dumps(spec_schema(), indent=2)))
    PROMPT_PATH.write_text(prompt)
    subprocess.run(["pbcopy"], input=prompt.encode(), check=False)
    print(f"Prompt written to {PROMPT_PATH.name} and copied to the clipboard. Paste it into a "
          f"fresh Claude chat, save the JSON reply to a file, then run:\n"
          f"  python generate_spec.py --check <reply file>")


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        # A pasted reply has no schema guarantee, so it's checked here: the same JSON
        # Schema that structured outputs enforce, then the options against the API.
        spec = json.loads(Path(sys.argv[2]).read_text())
        errors = list(jsonschema.Draft202012Validator(spec_schema()).iter_errors(spec))
        if errors:
            for error in errors:
                print(f"  {'.'.join(map(str, error.path)) or '<root>'}: {error.message}")
            sys.exit(f"{sys.argv[2]} does not match the spec schema ({len(errors)} errors)")
        check_spec(spec)
        save_spec(spec, source=f"checked against the schema and the API, from {sys.argv[2]}")
        return
    if sys.argv[1:] == ["--prompt-only"]:
        write_prompt()
        return

    try:
        spec = ask_claude()
    except ImportError as error:
        print(f"Claude API unavailable ({error.name} not installed); falling back to the prompt file.")
        write_prompt()
        return
    except Exception as error:  # no credentials, API or network error, refusal, truncation
        print(f"Claude API call failed ({type(error).__name__}: {error}); "
              f"falling back to the prompt file.")
        write_prompt()
        return

    REPLY_PATH.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n")
    save_spec(spec, source=f"drafted by {MODEL} via structured outputs, from smart_home_api.py only")


if __name__ == "__main__":
    main()
