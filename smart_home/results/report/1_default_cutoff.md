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
| Latency p50 (ms)                 |           231.5    |                      741      |
| Latency p95 (ms)                 |           334.5    |                     1176.8    |
| Latency max (ms)                 |           363.9    |                     2047.1    |
| Input tokens / command           |          1565.8    |                      995.7    |
| Output tokens / command          |           647.7    |                       16.5    |
| Cost per 1,000 commands ($)      |             0.0658 |                        0.3399 |

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

| utt                                            | expected_call                                    | call                                 |   confidence | weakest        |
|:-----------------------------------------------|:-------------------------------------------------|:-------------------------------------|-------------:|:---------------|
| i need to change my house lights color to blue | lights(action="color", room="all", color="blue") | lights(action="color", color="blue") |         0.36 | lights.room?   |
| house lights blue                              | lights(action="color", room="all", color="blue") | lights(action="color", color="blue") |         0.06 | lights.room?   |
| quiet                                          | speaker(action="mute")                           | speaker(action="volume_down")        |         0.92 | speaker.action |
| clean my house                                 | vacuum(room="all")                               | vacuum()                             |         0.32 | vacuum.room?   |
| olly clean the flat                            | vacuum(room="all")                               | vacuum()                             |         0.32 | vacuum.room?   |

**LLM: 1 wrong call**

| utt                     | expected_call       | call                                   |
|:------------------------|:--------------------|:---------------------------------------|
| put the disco lights on | lights(action="on") | lights(color="purple", action="color") |
