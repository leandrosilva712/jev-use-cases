## Results (jev_test.jsonl)

|                                  | jev (jev-1.13.0)   |
|:---------------------------------|:-------------------|
| Commands                         | 200                |
| Right function %                 | 100.0              |
| Right call (function + args) %   | 98.0               |
| Right args, given right device % | 97.7               |
| Unrelated -> no_call %           | 100.0              |
| Device command -> no_call %      | 0                  |
| Invalid calls                    | 0                  |
| Errors                           | 0                  |
| After gate: acted correctly %    | 98.0               |
| After gate: acted wrongly %      | 2.0                |
| After gate: asked to clarify %   | 0                  |
| Clarify cases that were wrong %  | –                  |
| Wrong calls caught by clarify %  | 0                  |
| Median confidence, right calls   | 0.9400             |
| Median confidence, wrong calls   | 0.8400             |
| Latency p50 (ms)                 | 237.8              |
| Latency p95 (ms)                 | 323.7              |
| Latency max (ms)                 | 365.0              |
| Input tokens / command           | 1516.8             |
| Output tokens / command          | 647.6              |
| Cost per 1,000 commands ($)      | 0.0637             |

### jev (jev-1.13.0)

| expected_function   |   right call % |
|:--------------------|---------------:|
| coffee              |          100   |
| lights              |           97.7 |
| no_call             |          100   |
| plug                |          100   |
| speaker             |           96.6 |
| vacuum              |           95   |

| arg            |   right % |
|:---------------|----------:|
| coffee.drink   |     100   |
| lights.action  |     100   |
| lights.color   |     100   |
| lights.room    |      97.7 |
| plug.action    |     100   |
| speaker.action |      96.6 |
| vacuum.room    |      95   |
