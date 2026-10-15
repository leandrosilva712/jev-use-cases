# Old version: Jev with the first wording of the room check (archived)

The first Jev run, kept as a sidenote for the blog. The current version
(`jev/spec.json`, `results/`) differs only in the wording of the two
"was a room mentioned?" checks. Everything else is identical: the API, the
other 10 questions, the dataset, the Jev model (`jev-1.13.0`), the scoring.
The LLM baseline was not affected: those checks are not part of its tools, so
its results (`results/llm/`) are shared by both versions.

## What changed in the wording

`lights.room?` (Noul)

| | Old (this folder) | Current |
|---|---|---|
| question | Does the user say which room's lights, such as the kitchen, the bedroom, the porch or the whole house? | Does the user say where the lights are, either a room such as the kitchen, the bedroom or the porch, or everywhere, such as all the lights or the whole home? |
| true | names a room or the whole house | names a room, or asks for all the lights or the whole home |
| false | does not say which room | says nothing about a room or the whole home, only the lights |

`vacuum.room?` (Noul)

| | Old (this folder) | Current |
|---|---|---|
| question | Does the user say where to vacuum, such as the kitchen, the bedroom, the hallway or the whole house? | Does the user say where to vacuum, either a room such as the kitchen, the bedroom or the hallway, or everywhere, such as the whole home? |
| true | names a room or the whole house | names a room, or asks for the whole home or everywhere |
| false | does not say where to vacuum | says nothing about a room or the whole home, only to vacuum |

Why: Jev reads questions literally. With the old wording, "all the lights" and
"the flat" did not count as naming a room or "the whole house", so the room
was dropped even though the room choice itself picked `all` with confidence
1.00. The new wording was written after seeing those test mistakes.

## Results on the 200 test commands

Both versions are tuned the same way: only the room checks (`lights.room?`,
`vacuum.room?`) get a cut-off tuned on dev; colour and drink stay at 0.5.

| | Old wording | Current wording | LLM |
|---|---|---|---|
| Cut-off 0.5 (default) | 195 right | 195 right | 199 |
| Room cut-off tuned on dev | 196 (room 0.35) | 199 (room 0.25) | 199 |

Old wording, wrong calls with the tuned room cut-off: "switch on all the lights" and
"turn all lights on" (room `all` dropped), "olly clean the flat" (room `all`
dropped), "quiet" (`volume_down` instead of `mute`). The current wording fixes
the three room cases but newly misreads "house lights" at the default cut-off
(it reads as "only the lights"): the same literal reading, triggered by other words.

## Files

```
jev/spec.json, jev/questions.json   the old wording and the 12 questions built from it
jev/config.json                     room cut-off tuned on dev for the old wording (0.35)
results/jev/raw.json                Jev's answers to all 250 commands (old wording)
results/jev/*.jsonl, *_mistakes.csv predictions and wrong calls at the tuned room cut-off
results/report/                     the four-scenario report for the old wording
regenerate.py                       rebuilds config, predictions and report from raw.json
```

`raw.json` holds the answers Jev gave to the old wording. Everything else is
rebuilt from it with the current code (same tuning and report as the current
version), with no API calls:

```bash
python -m old_version.regenerate
```
