## 2. Default cut-off (0.5), asking "did you mean ...?" below a threshold

- Cut-off: 0.5 (default), as in scenario 1.
- Confirmation: Jev asks "did you mean ...?" instead of acting when the call's confidence (its least certain answer) is below the threshold. Swept on the test commands as a what-if, not tuned.

### Jev with confirmation, by threshold (200 test commands)

| threshold   |   acted correctly |   acted wrongly |   asked (did you mean...?) |   asked, call was right |   asked, call was wrong | wrong calls caught   |
|:------------|------------------:|----------------:|---------------------------:|------------------------:|------------------------:|:---------------------|
| off         |               195 |               5 |                          0 |                       0 |                       0 | 0 of 5               |
| 0.50        |               193 |               1 |                          6 |                       2 |                       4 | 4 of 5               |
| 0.55        |               193 |               1 |                          6 |                       2 |                       4 | 4 of 5               |
| 0.60        |               191 |               1 |                          8 |                       4 |                       4 | 4 of 5               |
| 0.65        |               191 |               1 |                          8 |                       4 |                       4 | 4 of 5               |
| 0.70        |               189 |               1 |                         10 |                       6 |                       4 | 4 of 5               |
| 0.75        |               187 |               1 |                         12 |                       8 |                       4 | 4 of 5               |
| 0.80        |               182 |               1 |                         17 |                      13 |                       4 | 4 of 5               |
| 0.85        |               166 |               1 |                         33 |                      29 |                       4 | 4 of 5               |
| 0.90        |               145 |               1 |                         54 |                      50 |                       4 | 4 of 5               |
| 0.95        |                89 |               0 |                        111 |                     106 |                       5 | 5 of 5               |
| 1.00        |                60 |               0 |                        140 |                     135 |                       5 | 5 of 5               |

- Median call confidence: right calls 0.94, wrong calls 0.32.
- For reference, the LLM (no confidence, so no gate) acts on every command: 199 correctly, 1 wrongly.
