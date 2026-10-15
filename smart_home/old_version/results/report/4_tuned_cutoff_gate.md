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
