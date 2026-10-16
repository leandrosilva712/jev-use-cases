# Jev vs LLM: smart-home function calling (200 test commands)

Old wording (old_version/jev/spec.json). Generated from cached answers: Jev old_version/results/jev/raw.json. LLM answers: results/llm/test.jsonl. No API calls.

## 1. Default cut-off (0.5), no confirmation

- Jev `jev-1.13.0`: one request per command with all 12 questions (speculative fan-out); the call is assembled from the answers that apply.
- Cut-offs for "does the command mention X?": lights.room?, lights.color?, vacuum.room?, coffee.drink? at 0.5 (default).
- Confirmation: off (every call is made).
- LLM `gemini-3.5-flash-lite`: native function calling, mode VALIDATED (calls constrained to the listed options), minimal thinking, no temperature; same wording as Jev (jev/spec.json). Not tuned, no cut-off, no confidence: identical in every scenario.

### Results (test commands)

|                                  |   Jev (jev-1.13.0) |   LLM (gemini-3.5-flash-lite) |
|:---------------------------------|-------------------:|------------------------------:|
| Commands                         |           200      |                      200      |
| Right function %                 |           100      |                      100      |
| Right call (function + args) %   |            97.5    |                       99.5    |
| Right args, given right device % |            97.2    |                       99.4    |
| Unrelated -> no_call %           |           100      |                      100      |
| Device command -> no_call %      |             0      |                        0      |
| Invalid calls                    |             0      |                        0      |
| Errors                           |             0      |                        0      |
| Latency p50 (ms)                 |           237.8    |                      741      |
| Latency p95 (ms)                 |           323.7    |                     1176.8    |
| Latency max (ms)                 |           365      |                     2047.1    |
| Input tokens / command           |          1516.8    |                      995.7    |
| Output tokens / command          |           647.6    |                       16.5    |
| Cost per 1,000 commands ($)      |             0.0637 |                        0.3399 |

### Right calls by function (%)

| expected_function   |   Jev |   LLM |
|:--------------------|------:|------:|
| coffee              | 100   | 100   |
| lights              |  97.7 |  98.8 |
| no_call             | 100   | 100   |
| plug                | 100   | 100   |
| speaker             |  96.6 | 100   |
| vacuum              |  90   | 100   |

### Right arguments by argument (%), when the function is right

| arg            |   Jev |   LLM |
|:---------------|------:|------:|
| coffee.drink   | 100   | 100   |
| lights.action  | 100   |  98.8 |
| lights.color   | 100   |  98.8 |
| lights.room    |  97.7 | 100   |
| plug.action    | 100   | 100   |
| speaker.action |  96.6 | 100   |
| vacuum.room    |  90   | 100   |

### Wrong calls

**Jev: 5 wrong calls**

| utt                      | expected_call                   | call                          |   confidence | weakest        |
|:-------------------------|:--------------------------------|:------------------------------|-------------:|:---------------|
| switch on all the lights | lights(action="on", room="all") | lights(action="on")           |         0.82 | lights.room?   |
| turn all lights on       | lights(action="on", room="all") | lights(action="on")           |         0.86 | lights.room?   |
| quiet                    | speaker(action="mute")          | speaker(action="volume_down") |         0.92 | speaker.action |
| clean my house           | vacuum(room="all")              | vacuum()                      |         0.22 | vacuum.room?   |
| olly clean the flat      | vacuum(room="all")              | vacuum()                      |         0.58 | vacuum.room?   |

**LLM: 1 wrong call**

| utt                     | expected_call       | call                                   |
|:------------------------|:--------------------|:---------------------------------------|
| put the disco lights on | lights(action="on") | lights(color="purple", action="color") |

## 2. Default cut-off (0.5), asking "did you mean ...?" below a threshold

- Cut-off: 0.5 (default), as in scenario 1.
- Confirmation: Jev asks "did you mean ...?" instead of acting when the call's confidence (its least certain answer) is below the threshold. Swept on the test commands as a what-if, not tuned.

### Jev with confirmation, by threshold (200 test commands)

| threshold   |   acted correctly |   acted wrongly |   asked (did you mean...?) |   asked, call was right |   asked, call was wrong | wrong calls caught   |
|:------------|------------------:|----------------:|---------------------------:|------------------------:|------------------------:|:---------------------|
| off         |               195 |               5 |                          0 |                       0 |                       0 | 0 of 5               |
| 0.50        |               191 |               4 |                          5 |                       4 |                       1 | 1 of 5               |
| 0.55        |               190 |               4 |                          6 |                       5 |                       1 | 1 of 5               |
| 0.60        |               190 |               3 |                          7 |                       5 |                       2 | 2 of 5               |
| 0.65        |               190 |               3 |                          7 |                       5 |                       2 | 2 of 5               |
| 0.70        |               189 |               3 |                          8 |                       6 |                       2 | 2 of 5               |
| 0.75        |               188 |               3 |                          9 |                       7 |                       2 | 2 of 5               |
| 0.80        |               186 |               3 |                         11 |                       9 |                       2 | 2 of 5               |
| 0.85        |               180 |               2 |                         18 |                      15 |                       3 | 3 of 5               |
| 0.90        |               174 |               1 |                         25 |                      21 |                       4 | 4 of 5               |
| 0.95        |                90 |               0 |                        110 |                     105 |                       5 | 5 of 5               |
| 1.00        |                61 |               0 |                        139 |                     134 |                       5 | 5 of 5               |

- Median call confidence: right calls 0.94, wrong calls 0.82.
- For reference, the LLM (no confidence, so no gate) acts on every command: 199 correctly, 1 wrongly.

## 3. Cut-off tuned on dev (room 0.35), no confirmation

- Jev `jev-1.13.0`: one request per command with all 12 questions (speculative fan-out); the call is assembled from the answers that apply.
- Cut-offs for "does the command mention X?": lights.room?, vacuum.room? at 0.35 (tuned on dev); lights.color?, coffee.drink? at 0.5 (default).
- Confirmation: off (every call is made).
- LLM `gemini-3.5-flash-lite`: native function calling, mode VALIDATED (calls constrained to the listed options), minimal thinking, no temperature; same wording as Jev (jev/spec.json). Not tuned, no cut-off, no confidence: identical in every scenario.

### Results (test commands)

|                                  |   Jev (jev-1.13.0) |   LLM (gemini-3.5-flash-lite) |
|:---------------------------------|-------------------:|------------------------------:|
| Commands                         |           200      |                      200      |
| Right function %                 |           100      |                      100      |
| Right call (function + args) %   |            98      |                       99.5    |
| Right args, given right device % |            97.7    |                       99.4    |
| Unrelated -> no_call %           |           100      |                      100      |
| Device command -> no_call %      |             0      |                        0      |
| Invalid calls                    |             0      |                        0      |
| Errors                           |             0      |                        0      |
| Latency p50 (ms)                 |           237.8    |                      741      |
| Latency p95 (ms)                 |           323.7    |                     1176.8    |
| Latency max (ms)                 |           365      |                     2047.1    |
| Input tokens / command           |          1516.8    |                      995.7    |
| Output tokens / command          |           647.6    |                       16.5    |
| Cost per 1,000 commands ($)      |             0.0637 |                        0.3399 |

### Right calls by function (%)

| expected_function   |   Jev |   LLM |
|:--------------------|------:|------:|
| coffee              | 100   | 100   |
| lights              |  97.7 |  98.8 |
| no_call             | 100   | 100   |
| plug                | 100   | 100   |
| speaker             |  96.6 | 100   |
| vacuum              |  95   | 100   |

### Right arguments by argument (%), when the function is right

| arg            |   Jev |   LLM |
|:---------------|------:|------:|
| coffee.drink   | 100   | 100   |
| lights.action  | 100   |  98.8 |
| lights.color   | 100   |  98.8 |
| lights.room    |  97.7 | 100   |
| plug.action    | 100   | 100   |
| speaker.action |  96.6 | 100   |
| vacuum.room    |  95   | 100   |

### Wrong calls

**Jev: 4 wrong calls**

| utt                      | expected_call                   | call                          |   confidence | weakest        |
|:-------------------------|:--------------------------------|:------------------------------|-------------:|:---------------|
| switch on all the lights | lights(action="on", room="all") | lights(action="on")           |         0.82 | lights.room?   |
| turn all lights on       | lights(action="on", room="all") | lights(action="on")           |         0.86 | lights.room?   |
| quiet                    | speaker(action="mute")          | speaker(action="volume_down") |         0.92 | speaker.action |
| olly clean the flat      | vacuum(room="all")              | vacuum()                      |         0.58 | vacuum.room?   |

**LLM: 1 wrong call**

| utt                     | expected_call       | call                                   |
|:------------------------|:--------------------|:---------------------------------------|
| put the disco lights on | lights(action="on") | lights(color="purple", action="color") |

### How the cut-off was tuned

Tuning on the 50 dev commands (gate off). Checks are grouped by argument name and each group gets one cut-off: every value from 0.20 to 0.80, keep the most right calls; ties go to the value closest to the default 0.5. Checks not in a group stay at 0.5.

**Group `room`** (lights.room?, vacuum.room?)

| 0.20   | 0.25   | 0.30   | 0.35   | 0.40   | 0.45   | 0.50   | 0.55   | 0.60   | 0.65   | 0.70   | 0.75   | 0.80   |
|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|
| 98%    | 98%    | 98%    | 98%    | 96%    | 96%    | 96%    | 96%    | 96%    | 96%    | 96%    | 94%    | 92%    |

Chosen: **0.35**.

Result: lights.room?, vacuum.room? at 0.35 (tuned on dev); lights.color?, coffee.drink? at 0.5 (default).

Calls that change with the tuned cut-off:

| command        | expected           | default cut-off   | tuned cut-off      |
|:---------------|:-------------------|:------------------|:-------------------|
| clean my house | vacuum(room="all") | vacuum()          | vacuum(room="all") |

## 4. Cut-off tuned on dev (room 0.35), asking "did you mean ...?" below a threshold

- Cut-offs: lights.room?, vacuum.room? at 0.35 (tuned on dev); lights.color?, coffee.drink? at 0.5 (default), as in scenario 3.
- Confirmation: Jev asks "did you mean ...?" instead of acting when the call's confidence (its least certain answer) is below the threshold. Swept on the test commands as a what-if, not tuned.

### Jev with confirmation, by threshold (200 test commands)

| threshold   |   acted correctly |   acted wrongly |   asked (did you mean...?) |   asked, call was right |   asked, call was wrong | wrong calls caught   |
|:------------|------------------:|----------------:|---------------------------:|------------------------:|------------------------:|:---------------------|
| off         |               196 |               4 |                          0 |                       0 |                       0 | 0 of 4               |
| 0.50        |               191 |               4 |                          5 |                       5 |                       0 | 0 of 4               |
| 0.55        |               190 |               4 |                          6 |                       6 |                       0 | 0 of 4               |
| 0.60        |               190 |               3 |                          7 |                       6 |                       1 | 1 of 4               |
| 0.65        |               190 |               3 |                          7 |                       6 |                       1 | 1 of 4               |
| 0.70        |               189 |               3 |                          8 |                       7 |                       1 | 1 of 4               |
| 0.75        |               188 |               3 |                          9 |                       8 |                       1 | 1 of 4               |
| 0.80        |               186 |               3 |                         11 |                      10 |                       1 | 1 of 4               |
| 0.85        |               180 |               2 |                         18 |                      16 |                       2 | 2 of 4               |
| 0.90        |               174 |               1 |                         25 |                      22 |                       3 | 3 of 4               |
| 0.95        |                90 |               0 |                        110 |                     106 |                       4 | 4 of 4               |
| 1.00        |                61 |               0 |                        139 |                     135 |                       4 | 4 of 4               |

- Median call confidence: right calls 0.94, wrong calls 0.84.
- For reference, the LLM (no confidence, so no gate) acts on every command: 199 correctly, 1 wrongly.
