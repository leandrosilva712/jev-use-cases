## Results (jev/test.jsonl, llm/test.jsonl)

|                                  |   jev (jev-1.13.0) |   llm (gemini-3.5-flash-lite) |
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

### jev (jev-1.13.0)

| expected_function   |   right call % |
|:--------------------|---------------:|
| coffee              |          100   |
| lights              |          100   |
| no_call             |          100   |
| plug                |          100   |
| speaker             |           96.6 |
| vacuum              |          100   |

| arg            |   right % |
|:---------------|----------:|
| coffee.drink   |     100   |
| lights.action  |     100   |
| lights.color   |     100   |
| lights.room    |     100   |
| plug.action    |     100   |
| speaker.action |      96.6 |
| vacuum.room    |     100   |

### llm (gemini-3.5-flash-lite)

| expected_function   |   right call % |
|:--------------------|---------------:|
| coffee              |          100   |
| lights              |           98.8 |
| no_call             |          100   |
| plug                |          100   |
| speaker             |          100   |
| vacuum              |          100   |

| arg            |   right % |
|:---------------|----------:|
| coffee.drink   |     100   |
| lights.action  |      98.8 |
| lights.color   |      98.8 |
| lights.room    |     100   |
| plug.action    |     100   |
| speaker.action |     100   |
| vacuum.room    |     100   |
