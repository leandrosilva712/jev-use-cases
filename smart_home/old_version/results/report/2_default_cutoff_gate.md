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
