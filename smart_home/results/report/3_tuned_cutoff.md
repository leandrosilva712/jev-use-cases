## 3. Cut-off tuned on dev (room 0.25), no confirmation

- Jev `jev-1.13.0`: one request per command with all 12 questions (speculative fan-out); the call is assembled from the answers that apply.
- Cut-offs for "does the command mention X?": lights.room?, vacuum.room? at 0.25 (tuned on dev); lights.color?, coffee.drink? at 0.5 (default).
- Confirmation: off (every call is made).
- LLM `gemini-3.5-flash-lite`: native function calling, mode VALIDATED (calls constrained to the listed options), minimal thinking, no temperature; same wording as Jev (jev/spec.json). Not tuned, no cut-off, no confidence: identical in every scenario.

### Results (test commands)

|                                  |   Jev (jev-1.13.0) |   LLM (gemini-3.5-flash-lite) |
|:---------------------------------|-------------------:|------------------------------:|
| Commands                         |           200      |                      200      |
| Right function %                 |           100      |                      100      |
| Right call (function + args) %   |            99.5    |                       99.5    |
| Right args, given right device % |            99.4    |                       99.4    |
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
| lights              | 100   |  98.8 |
| no_call             | 100   | 100   |
| plug                | 100   | 100   |
| speaker             |  96.6 | 100   |
| vacuum              | 100   | 100   |

### Right arguments by argument (%), when the function is right

| arg            |   Jev |   LLM |
|:---------------|------:|------:|
| coffee.drink   | 100   | 100   |
| lights.action  | 100   |  98.8 |
| lights.color   | 100   |  98.8 |
| lights.room    | 100   | 100   |
| plug.action    | 100   | 100   |
| speaker.action |  96.6 | 100   |
| vacuum.room    | 100   | 100   |

### Wrong calls

**Jev: 1 wrong call**

| utt   | expected_call          | call                          |   confidence | weakest        |
|:------|:-----------------------|:------------------------------|-------------:|:---------------|
| quiet | speaker(action="mute") | speaker(action="volume_down") |         0.92 | speaker.action |

**LLM: 1 wrong call**

| utt                     | expected_call       | call                                   |
|:------------------------|:--------------------|:---------------------------------------|
| put the disco lights on | lights(action="on") | lights(color="purple", action="color") |

### How the cut-off was tuned

Tuning on the 50 dev commands (gate off). Checks are grouped by argument name and each group gets one cut-off: every value from 0.20 to 0.80, keep the most right calls; ties go to the value closest to the default 0.5. Checks not in a group stay at 0.5.

**Group `room`** (lights.room?, vacuum.room?)

| 0.20   | 0.25   | 0.30   | 0.35   | 0.40   | 0.45   | 0.50   | 0.55   | 0.60   | 0.65   | 0.70   | 0.75   | 0.80   |
|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|:-------|
| 96%    | 96%    | 94%    | 94%    | 94%    | 94%    | 94%    | 94%    | 94%    | 94%    | 94%    | 94%    | 94%    |

Chosen: **0.25**.

Result: lights.room?, vacuum.room? at 0.25 (tuned on dev); lights.color?, coffee.drink? at 0.5 (default).

Calls that change with the tuned cut-off:

| command                                        | expected                                         | default cut-off                      | tuned cut-off                                    |
|:-----------------------------------------------|:-------------------------------------------------|:-------------------------------------|:-------------------------------------------------|
| i need to change my house lights color to blue | lights(action="color", room="all", color="blue") | lights(action="color", color="blue") | lights(action="color", room="all", color="blue") |
| house lights blue                              | lights(action="color", room="all", color="blue") | lights(action="color", color="blue") | lights(action="color", room="all", color="blue") |
| clean my house                                 | vacuum(room="all")                               | vacuum()                             | vacuum(room="all")                               |
| olly clean the flat                            | vacuum(room="all")                               | vacuum()                             | vacuum(room="all")                               |
