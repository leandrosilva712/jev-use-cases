## 4. Cut-off tuned on dev (room 0.25), asking "did you mean ...?" below a threshold

- Cut-offs: lights.room?, vacuum.room? at 0.25 (tuned on dev); lights.color?, coffee.drink? at 0.5 (default), as in scenario 3.
- Confirmation: Jev asks "did you mean ...?" instead of acting when the call's confidence (its least certain answer) is below the threshold. Swept on the test commands as a what-if, not tuned.

### Jev with confirmation, by threshold (200 test commands)

| threshold   |   acted correctly |   acted wrongly |   asked (did you mean...?) |   asked, call was right |   asked, call was wrong | wrong calls caught   |
|:------------|------------------:|----------------:|---------------------------:|------------------------:|------------------------:|:---------------------|
| off         |               199 |               1 |                          0 |                       0 |                       0 | 0 of 1               |
| 0.50        |               193 |               1 |                          6 |                       6 |                       0 | 0 of 1               |
| 0.55        |               193 |               1 |                          6 |                       6 |                       0 | 0 of 1               |
| 0.60        |               191 |               1 |                          8 |                       8 |                       0 | 0 of 1               |
| 0.65        |               191 |               1 |                          8 |                       8 |                       0 | 0 of 1               |
| 0.70        |               189 |               1 |                         10 |                      10 |                       0 | 0 of 1               |
| 0.75        |               187 |               1 |                         12 |                      12 |                       0 | 0 of 1               |
| 0.80        |               182 |               1 |                         17 |                      17 |                       0 | 0 of 1               |
| 0.85        |               166 |               1 |                         33 |                      33 |                       0 | 0 of 1               |
| 0.90        |               145 |               1 |                         54 |                      54 |                       0 | 0 of 1               |
| 0.95        |                89 |               0 |                        111 |                     110 |                       1 | 1 of 1               |
| 1.00        |                60 |               0 |                        140 |                     139 |                       1 | 1 of 1               |

- Median call confidence: right calls 0.94, wrong calls 0.92.
- For reference, the LLM (no confidence, so no gate) acts on every command: 199 correctly, 1 wrongly.
