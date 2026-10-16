# Smart-home PoC: Jev vs an LLM for tool calling

A smart-home assistant API called by Jev (TypeSafe) and by Gemini 3.5 Flash-Lite with
native function calling, compared on 200 voice commands from Amazon's MASSIVE
dataset. This README walks through every step from a fresh clone to the final
report (`results/report/report.md`).

**You don't need to spend any API tokens.** Every model answer is already cached
in the repo (`results/jev/raw.json`, `results/llm/raw.json`). The scripts only call
an API for commands that are missing from the cache, so with the cache in place
every step below runs offline and gives the same numbers. Steps that would call an
API are marked ⚠.

## Folder layout

```
common/        shared by every step
  api.py         the typed smart-home API (functions + Literal options)
  schema.py      closed_sets(), OPTIONS, DEFAULTS read from the API's type hints
  paths.py       every file location
dataset/       building the commands and their answer key
  download_massive.py, generate_curated_dataset.py
  commands.csv   250 commands (50 dev / 200 test) with expected calls
  raw/           downloaded MASSIVE (git-ignored)
jev/           Jev side
  generate_spec.py -> spec.json -> build_questions.py -> questions.json
  assistant.py   asks Jev, assembles the call, confidence gate
  tune.py        tunes the "mentioned?" cut-off per argument (default: the room checks) on dev -> config.json
llm/           LLM baseline side (Gemini tool calling)
  tools.py       system instruction + tool declarations from jev/spec.json -> tools.json
  assistant.py   asks Gemini (VALIDATED mode, minimal thinking), cached
evaluation/    evaluate.py: scores any results/<system>/<split>.jsonl
  report.py      the blog's 4 scenarios (default/tuned cut-off, with/without "did you mean...?") -> results/report/
results/       <system>/raw cache, <split>.jsonl predictions, mistakes; summary_<split>.md; report/
old_version/   the first run, with the earlier wording of the room check (archived)
```

## 1. Set up the environment

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.11+ for you).

```bash
cd jev-use-cases
uv sync
```

This creates `.venv/` with the locked dependencies (`typesafe-sdk`, `google-genai`,
`anthropic`, `pandas`, …). All commands below run from the `smart_home/` folder, as
modules:

```bash
cd smart_home
uv run python -m <module>
```

**API keys** are only needed to make new requests. Put them in `.env`, either in
`smart_home/` or in the repo root (`.env` is git-ignored):

```bash
TYPESAFE_API_KEY=...   # Jev (jev.assistant)
GEMINI_API_KEY=...     # Gemini baseline (llm.assistant)
ANTHROPIC_API_KEY=...  # only for redrafting the spec (jev.generate_spec)
```

To reproduce the results from the cache you can leave them out.

## 2. Get the dataset

```bash
uv run python -m dataset.download_massive
```

Downloads Amazon's MASSIVE v1.1 (about 40 MB, CC BY 4.0) from its official S3
bucket, checks it against a pinned SHA-256, and extracts the English and Portuguese
files to `dataset/raw/massive/`. Re-running it reuses the files.

```bash
uv run python -m dataset.generate_curated_dataset
```

Builds `dataset/commands.csv`: 250 commands picked (never edited) from MASSIVE,
with the expected function call for each, split into 50 dev and 200 test. It's
deterministic, so the file comes out identical to the committed one. It prints the
split per function and the argument values.

## 3. Build the model inputs

Both models get their wording from `jev/spec.json` (already in the repo).

```bash
uv run python -m jev.build_questions   # -> jev/questions.json (Jev's 12 questions)
uv run python -m llm.tools             # -> llm/tools.json (Gemini's system instruction and 5 tools)
```

Both are offline and deterministic.

⚠ `jev.generate_spec` asks Claude to redraft `spec.json` from the API and
**overwrites it**. Skip it to reproduce the published results; it's only for
starting a new spec. `--prompt-only` writes the prompt without calling the API.

## 4. Jev: answers and tuning

```bash
uv run python -m jev.assistant --split dev
uv run python -m jev.tune
uv run python -m jev.assistant --split test
```

- `jev.assistant` reads the cached answers and turns them into predictions
  (`results/jev/dev.jsonl`, `test.jsonl`). With the cache it prints
  `50 cached, 0 requested` and `200 cached, 0 requested`. ⚠ Without the cache it
  sends one request per missing command to `jev-1.13.0` and saves each answer as
  it arrives.
- `jev.tune` picks the cut-off for the "was a room mentioned?" checks on the 50
  dev commands only (it chooses **0.25**), keeps the colour and drink checks at
  0.5, and writes `jev/config.json` and `results/jev/dev_mistakes.csv`.
- The test run uses that config. Run the tuning before it.

## 5. Gemini baseline

```bash
uv run python -m llm.assistant --split dev
uv run python -m llm.assistant --split test
```

Reads the cached Gemini answers (`gemini-3.5-flash-lite`, VALIDATED mode,
minimal thinking) and writes `results/llm/dev.jsonl` and `test.jsonl`. With the
cache it prints `0 requested`. ⚠ Without the cache it calls the Gemini API once
per missing command.

## 6. Results

```bash
uv run python -m evaluation.report
```

Writes the final report to `results/report/` with no API calls:

| File | Content |
|---|---|
| `report.md` | all four scenarios in one file |
| `1_default_cutoff.md` | Jev at the default cut-off (0.5) vs Gemini |
| `2_default_cutoff_gate.md` | the same, asking "did you mean…?" at thresholds 0.50 to 1.00 |
| `3_tuned_cutoff.md` | Jev with the room cut-off tuned on dev vs Gemini, plus how it was tuned |
| `4_tuned_cutoff_gate.md` | the same with the threshold sweep |
| `jev_*-cutoff.jsonl`, `*_mistakes.csv` | the predictions and wrong calls behind each table |

It prints the headline numbers. These are what you should get:

```
Default cut-off 0.5: Jev 195/200 right calls
Tuned cut-off (room 0.25): Jev 199/200 right calls
LLM:                  199/200 right calls
```

Optionally, for a single comparison table:

```bash
uv run python -m evaluation.evaluate --split test   # -> results/summary_test.md
```

## 7. Optional: the old wording

`old_version/` archives the first run, with the earlier wording of the room check:
its spec, questions, config, cached Jev answers and report (see
`old_version/README.md`). Its numbers are 195 right calls at the default cut-off
and 196 with the room cut-off tuned on dev (0.35). Nothing needs to be run for it.

## All steps in one go

```bash
cd jev-use-cases && uv sync && cd smart_home
uv run python -m dataset.download_massive
uv run python -m dataset.generate_curated_dataset
uv run python -m jev.build_questions
uv run python -m llm.tools
uv run python -m jev.assistant --split dev
uv run python -m jev.tune
uv run python -m jev.assistant --split test
uv run python -m llm.assistant --split dev
uv run python -m llm.assistant --split test
uv run python -m evaluation.report
```

## Checking that nothing was sent

Every runner prints how many commands came from the cache and how many it
requested. Look for `0 requested` in the output. The caches are only rewritten
when a new answer arrives, so this should also show no changes:

```bash
git status --short results/jev/raw.json results/llm/raw.json
```

## Starting from scratch (spends tokens)

To collect your own answers instead of using the cache, move the cache files aside
and rerun steps 4 to 6 with the API keys set:

```bash
mv results/jev/raw.json results/jev/raw.cached.json
mv results/llm/raw.json results/llm/raw.cached.json
```

That's 250 Jev requests (about 1,566 input tokens each, roughly $0.02 in total at
$42 per billion) and 250 Gemini requests (about 1,000 input and 17 output tokens
each, roughly $0.09 at list price). Latency and, occasionally, a borderline answer
can differ slightly from the published run.
