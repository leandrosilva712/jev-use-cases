# Smart-home PoC: Jev vs an LLM for tool calling

Background and plan: [JEV_PROJECT_CONTEXT.md](JEV_PROJECT_CONTEXT.md).

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
```

Every script runs as a module from this folder:

```bash
python -m dataset.download_massive
python -m dataset.generate_curated_dataset
python -m jev.generate_spec            # optional: redraft spec.json with Claude
python -m jev.build_questions
python -m jev.assistant --split dev
python -m jev.tune                     # room checks only; see TUNED_ARGUMENTS
python -m jev.assistant --split test
python -m llm.tools                    # writes llm/tools.json for review
python -m llm.assistant --split dev
python -m llm.assistant --split test
python -m evaluation.evaluate --split test
python -m evaluation.report            # results/report/report.md (no API calls)
```

API keys (`TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`, ...) are read from `.env` here or in the repo root.
