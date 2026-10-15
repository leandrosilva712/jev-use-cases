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
  tune.py        tunes stated_cutoff / threshold on dev -> config.json
llm/           LLM baseline side (Gemini tool calling)
evaluation/    evaluate.py: scores any results/<system>/<split>.jsonl
results/       <system>/raw cache, <split>.jsonl predictions, mistakes; summary_<split>.md
```

Every script runs as a module from this folder:

```bash
python -m dataset.download_massive
python -m dataset.generate_curated_dataset
python -m jev.generate_spec            # optional: redraft spec.json with Claude
python -m jev.build_questions
python -m jev.assistant --split dev
python -m jev.tune
python -m jev.assistant --split test
python -m evaluation.evaluate --split test
```

API keys (`TYPESAFE_API_KEY`, `ANTHROPIC_API_KEY`, ...) are read from `.env` here or in the repo root.
