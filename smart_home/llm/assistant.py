"""Gemini as a smart-home function caller: the LLM baseline.

Standard native function calling: one request per command with the system
instruction and the five tools from llm/tools.py (built from jev/spec.json).
The model either calls one function or replies in text, which counts as no call.

Settings:
  - MODEL, thinking at its lowest level (MINIMAL; it can't be switched off on 3.x)
  - function-calling mode VALIDATED: the model still chooses between a call and
    a text reply, but a call is constrained to the schema (enums), so what is
    measured is understanding, not JSON adherence
  - no temperature / top_p / top_k (deprecated on the newest Gemini models)
  - no tuning on dev: there is no knob to tune

Every answer is cached in results/llm/raw.json right away, so a failed run
resumes where it stopped. Latency is timed around the API call; one untimed
request first opens the connection (as for Jev).

Run (from smart_home/):
  python -m llm.assistant --ids 1570,1031,13124   smoke run: print the calls
  python -m llm.assistant --split dev             all dev rows -> results/llm/dev.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

import pandas as pd
from google import genai
from google.genai import types

from common.api import NO_CALL, TOOLS
from common.paths import COMMANDS_CSV, ROOT, load_env, system_results
from llm.tools import load as load_tools

SYSTEM = "llm"
MODEL = "gemini-3.5-flash-lite"
RESULTS_DIR = system_results(SYSTEM)
RAW_PATH = RESULTS_DIR / "raw.json"


class GeminiAssistant:
    def __init__(self, model: str = MODEL):
        load_env()  # GEMINI_API_KEY
        self.model = model
        instruction, tools = load_tools()
        self.client = genai.Client()
        self.config = types.GenerateContentConfig(
            system_instruction=instruction,
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(name=t["name"], description=t["description"],
                                          parameters_json_schema=t["parameters"])
                for t in tools])],
            tool_config=types.ToolConfig(function_calling_config=types.FunctionCallingConfig(
                mode=types.FunctionCallingConfigMode.VALIDATED)),
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    def ask(self, command: str) -> dict:
        """Send one command; return the calls/text with latency and token usage."""
        start = time.perf_counter()
        response = self.client.models.generate_content(model=self.model, contents=command, config=self.config)
        latency = time.perf_counter() - start

        candidate = response.candidates[0] if response.candidates else None
        parts = candidate.content.parts if candidate and candidate.content and candidate.content.parts else []
        calls = [{"name": p.function_call.name, "args": dict(p.function_call.args or {})}
                 for p in parts if p.function_call]
        text = "".join(p.text for p in parts if p.text and not p.thought).strip()
        usage = response.usage_metadata
        return {
            "utt": command,
            "model": response.model_version or self.model,
            "calls": calls,
            "text": text or None,
            "finish_reason": candidate.finish_reason.value if candidate and candidate.finish_reason else None,
            "input_tokens": usage.prompt_token_count or 0,
            "response_tokens": usage.candidates_token_count or 0,
            "thinking_tokens": usage.thoughts_token_count or 0,
            "latency_s": round(latency, 4),
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def warm_up(self) -> None:
        """Open the connection first, so the first timed request isn't a cold start (as for Jev)."""
        self.client.models.generate_content(model=self.model, contents="hello", config=self.config)


def load_raw() -> dict:
    return json.loads(RAW_PATH.read_text()) if RAW_PATH.exists() else {}


def run(commands: pd.DataFrame) -> dict:
    """Ask Gemini about every command not cached yet. The cache is saved after each request."""
    raw = load_raw()
    todo = commands[~commands["id"].astype(str).isin(raw)]
    if len(todo):
        llm = GeminiAssistant()
        llm.warm_up()
        for i, row in enumerate(todo.itertuples(), 1):
            raw[str(row.id)] = r = llm.ask(row.utt)
            RAW_PATH.write_text(json.dumps(raw, indent=1))
            shown = "; ".join(f"{c['name']}({c['args']})" for c in r["calls"]) or f"text: {r['text']}"
            print(f"  [{i}/{len(todo)}] {r['latency_s'] * 1000:6.0f} ms  {row.utt}  ->  {shown}")
    print(f"{len(commands) - len(todo)} cached, {len(todo)} requested")
    return raw


def to_record(row, r: dict) -> dict:
    """One raw answer in the shared format read by evaluation/evaluate.py."""
    calls = r["calls"]
    function = calls[0]["name"] if calls else NO_CALL
    args = calls[0]["args"] if calls else {}
    call = NO_CALL if not calls else f"{function}({', '.join(f'{k}=\"{v}\"' for k, v in args.items())})"
    return {
        "id": row.id, "split": row.split, "system": SYSTEM, "model": r["model"],
        "function": function, "args": args, "call": call, "text": r["text"],
        "clarify": False, "confidence": None, "weakest": None,
        "latency_s": r["latency_s"], "input_tokens": r["input_tokens"],
        # thinking tokens are billed as output
        "output_tokens": r["response_tokens"] + r["thinking_tokens"],
        "invalid": len(calls) > 1 or (bool(calls) and function not in TOOLS),
        "error": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--ids", help="comma-separated command ids: smoke run, prints the calls")
    a = parser.parse_args()

    commands = pd.read_csv(COMMANDS_CSV)
    if a.ids:
        commands = commands[commands["id"].astype(str).isin(a.ids.split(","))]
        raw = run(commands)
        for row in commands.itertuples():
            r = raw[str(row.id)]
            rec = to_record(row, r)
            print(f"\n{row.utt!r}\n  expected  {row.expected_call}\n  got       {rec['call']}"
                  f"{'  text: ' + r['text'] if r['text'] else ''}\n"
                  f"  {r['latency_s'] * 1000:.0f} ms, {r['input_tokens']} in, {r['response_tokens']} out "
                  f"+ {r['thinking_tokens']} thinking, finish {r['finish_reason']}, model {r['model']}")
        return

    if a.split != "all":
        commands = commands[commands["split"] == a.split]
    raw = run(commands)
    out = RESULTS_DIR / f"{a.split}.jsonl"
    out.write_text("".join(json.dumps(to_record(row, raw[str(row.id)])) + "\n" for row in commands.itertuples()))
    print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
