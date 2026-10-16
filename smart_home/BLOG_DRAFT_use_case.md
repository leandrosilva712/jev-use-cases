# Hands-on: Jev vs an LLM as a smart-home assistant

## The problem

Most teams that put an LLM in front of a product end up doing the same thing: turning a user's request into a function call. "Dim the living room lights" has to become `lights(action="dimmer", room="living room")`, and "what's the weather like?" has to become no call at all. Today this is done with an LLM and native tool calling, and it works well. But it costs a full generative model call per request, and the user waits for it.

This is exactly the kind of task Jev is built for. Most of the work is picking from closed sets: which device, which action, which room, which colour. Jev doesn't generate text; it answers typed questions with probabilities. So we built a small smart-home assistant, inspired by the smart-home demo in TypeSafe's docs, and ran the same requests through Jev and through an LLM, each set up the way its own documentation recommends.

## The dataset

We needed realistic voice commands with known answers, so we used **MASSIVE** (Amazon, CC BY 4.0): Alexa-style utterances in 51 languages, each labelled with an intent and slot values. We took the English (en-US) set and its smart-home commands (lights, vacuum, coffee machine, smart plug) plus the speaker-volume commands.

We **picked commands, we never edited them**. A command was kept only if every argument it carries maps to a clear option the API accepts. That filtered out:
- free-text values that a closed-set model can't produce (times, percentages, dates: "make coffee at six am");
- compound requests ("make the bedroom lights red and the hall lights normal");
- questions about devices ("how do I start the robot vacuum?");
- vague values ("make me a creamy coffee", "romantic lighting");
- 14 commands we removed by hand after reading them, because their label was wrong, contradictory or garbled (for example "switch up the colour of the lights" labelled as *brighter*).

We added 30 unrelated commands (weather, news, trivia, small talk) whose correct answer is no call. The answer key was derived automatically from MASSIVE's labels: intent to function and slots to arguments. Whole-home requests ("the house", "my home", "the flat", "all the lights") map to `room="all"`.

The result is **250 commands**, split into a **dev set of 50** and a **test set of 200**, with about 20% of each function in dev:

| Function | Dev | Test | Total |
|---|---|---|---|
| lights | 22 | 86 | 108 |
| speaker | 6 | 29 | 35 |
| plug | 6 | 21 | 27 |
| vacuum | 5 | 20 | 25 |
| coffee | 5 | 20 | 25 |
| no call | 6 | 24 | 30 |

The 50 dev commands are the only data used to adjust anything; the 200 test commands are scored once, at the end.

## The API

The assistant controls five devices. Every argument is a closed set of options, written as plain typed Python; optional arguments have a default that applies when the user doesn't mention them:

```python
LightAction = Literal["on", "off", "brighter", "dimmer", "color"]
Room = Literal["kitchen", "living room", "bedroom", "bathroom", "dining room", "hallway",
               "office", "den", "garage", "porch", "patio", "balcony", "garden", "all"]
Color = Literal["red", "orange", "yellow", "green", "blue", "purple", "pink", "white"]
Drink = Literal["regular", "espresso", "cappuccino", "latte", "americano"]
PlugAction = Literal["on", "off"]
SpeakerAction = Literal["volume_up", "volume_down", "mute"]

def lights(action: LightAction, room: Optional[Room] = None, color: Optional[Color] = None) -> str: ...
def vacuum(room: Optional[Room] = None) -> str: ...
def coffee(drink: Drink = "regular") -> str: ...
def plug(action: PlugAction) -> str: ...
def speaker(action: SpeakerAction) -> str: ...
```

## One spec, two consumers

Both models need the same thing: a description of what each function, argument and option means. We kept that wording in a single file, `spec.json`, and generated each model's input from it. That way neither side got better descriptions than the other.

The spec was drafted by an LLM (Claude), prompted with the API source code only and never the dataset, so the wording couldn't be fitted to our test commands. The prompt followed the style of TypeSafe's function-calling cookbook: short definitions, one line per option, no lists of phrasings. We then reviewed and edited it by hand. Here is the entry for the lights' `room` argument:

```json
"room": {
  "question": "Which room's lights does the user mean?",
  "stated": {
    "question": "Does the user say where the lights are, either a room such as the kitchen, the bedroom or the porch, or everywhere, such as all the lights or the whole home?",
    "true": "names a room, or asks for all the lights or the whole home",
    "false": "says nothing about a room or the whole home, only the lights"
  },
  "options": {
    "kitchen": null,
    "living room": "the living room or lounge",
    "hallway": "the hallway or corridor",
    "all": "the lights in every room of the house"
  }
}
```

The `stated` part is a yes/no question: "does the user mention this argument at all?". It only exists for optional arguments, and we'll come back to it, because it's where most of the story happens.

## Jev: speculative fan-out, following the cookbook

Jev follows TypeSafe's function-calling cookbook. Every function and argument becomes a question, and **all of them are sent in one request**. That's the speculative fan-out pattern. For our API that means 12 questions per command:

- `__tool__`: a choice between the five functions and `no_call`;
- one choice per argument, such as `lights.action` and `lights.room` (over the 14 rooms);
- one yes/no question per optional argument, such as `lights.room?`, `lights.color?` and `coffee.drink?`.

The spec entry above becomes two of those questions:

```json
"lights.room": {
  "type": "choice",
  "instructions": "Which room's lights does the user mean?",
  "criteria": { "kitchen": null, "living room": "the living room or lounge", "...": "...",
                "all": "the lights in every room of the house" }
},
"lights.room?": {
  "type": "noul",
  "instructions": "Does the user say where the lights are, either a room such as the kitchen, ... or everywhere, such as all the lights or the whole home?",
  "criteria": { "true": "names a room, or asks for all the lights or the whole home",
                "false": "says nothing about a room or the whole home, only the lights" }
}
```

Jev answers all 12 in a single pass. Our code then assembles the call:
1. `__tool__` picks the function.
2. Required arguments take their chosen option.
3. Optional arguments take their chosen option **only if** the yes/no question says the user mentioned them. Otherwise the default stands.

Most of those answers are thrown away: on average a call uses 3.8 of the 12. We chose this anyway because it targets **latency**. One round trip instead of a "which function?" request followed by a second request for that function's arguments. Jev's input tokens are cheap ($42 per billion), and its output tokens are free, so asking about devices nobody mentioned costs very little.

Turning the yes/no probability into yes or no needs a **cut-off**. TypeSafe's default is 0.5. We'll see that this single number matters.

## The LLM: native function calling with a light model

For the baseline we did what most teams would: native function calling with a small, fast model, **Gemini 3.5 Flash-Lite**. Thinking was set to its lowest level ("minimal"; it used 0 thinking tokens on every command), and we didn't set temperature, top_p or top_k, which are deprecated on the newest Gemini models.

Gemini gets the same `spec.json` wording, placed where an LLM expects it: function descriptions, parameter descriptions and enum values. Here is the lights tool's `room` parameter:

```json
"room": {
  "type": "string",
  "enum": ["kitchen", "living room", "bedroom", "...", "all"],
  "description": "Which room's lights does the user mean?\nliving room: the living room or lounge\nhallway: the hallway or corridor\n...\nall: the lights in every room of the house"
}
```

The router question and the "no call" description become the system instruction:

> You are the voice assistant of a smart home. What is the person asking the smart home voice assistant to do? Answer by calling the one function that does it. If it is something other than a home device function, such as a question or small talk, do not call any function and reply in one short sentence. Only fill an optional argument when the person says it; otherwise leave it out.

The `stated` yes/no questions aren't used. An LLM's normal way to say "only if mentioned" is to leave the parameter out of `required`.

We ran Gemini in **VALIDATED** mode. The model still decides whether to call a function at all, but any call it makes is constrained to the schema, so it can't invent a room called "attic". We want to measure whether the model understands the request, not whether it writes valid JSON. A plain-text reply counts as "no call".

## Results

All numbers are on the 200 test commands. The Jev columns differ only in the cut-off for the room yes/no questions; the next sections explain the change.

| | Jev, default cut-off (0.5) | Jev, room cut-off tuned on dev (0.25) | Gemini 3.5 Flash-Lite |
|---|---|---|---|
| Right function | 100% | 100% | 100% |
| Right call (function and every argument) | 97.5% (195) | **99.5% (199)** | 99.5% (199) |
| Unrelated commands left without a call | 100% | 100% | 100% |
| Invalid calls / errors | 0 / 0 | 0 / 0 | 0 / 0 |
| Latency, median | **232 ms** | **232 ms** | 741 ms |
| Latency, 95th percentile | **335 ms** | **335 ms** | 1,177 ms |
| Latency, slowest | **364 ms** | **364 ms** | 2,047 ms |
| Input / output tokens per command (average) | 1,566 / 648 (output free) | 1,566 / 648 | 996 / 16.5 |
| Cost per 1,000 commands | **$0.066** | **$0.066** | $0.340 |

**Speed and cost.** This is where Jev clearly wins. It's about **3× faster** in the typical case (232 vs 741 ms) and **5.6× faster** in the worst case (364 ms vs 2 s). Its latency is also far more predictable: Jev's slowest command is barely slower than its typical one, while Gemini's slowest takes almost three times its median. It's about **5× cheaper** too ($0.066 vs $0.34 per 1,000 commands), even though Jev reads more input tokens: the fan-out sends all 12 questions every time, but each token costs about 7× less and the output is free.

**Accuracy.** Both picked the right device for every one of the 200 commands, and both correctly left all 24 unrelated test commands without a call. With TypeSafe's default cut-off, Jev got 195 calls fully right against Gemini's 199. After tuning a single cut-off on the dev set, Jev matched Gemini at 199. The interesting part is *which* commands each one got wrong.

## Where each one fails

**Jev, default cut-off: 5 wrong calls**

| Command | Expected | Jev's call | P("a room was mentioned") |
|---|---|---|---|
| house lights blue | `lights(color, room="all", blue)` | `lights(color, blue)`, room missing | 0.47 |
| i need to change my house lights color to blue | `lights(color, room="all", blue)` | `lights(color, blue)`, room missing | 0.32 |
| clean my house | `vacuum(room="all")` | `vacuum()`, room missing | 0.34 |
| olly clean the flat | `vacuum(room="all")` | `vacuum()`, room missing | 0.34 |
| quiet | `speaker(action="mute")` | `speaker(action="volume_down")` | – |

**Jev, room cut-off tuned on dev: 1 wrong call.** "quiet" (`volume_down` instead of `mute`).

**Gemini: 1 wrong call.** "put the disco lights on" became `lights(action="color", color="purple")` instead of `lights(action="on")`. It read "disco" as a request for a colour. Because VALIDATED mode only allows listed values, the guess comes out as a perfectly valid call that is simply wrong.

Four of Jev's five mistakes follow the same pattern, and it's revealing. In every one, Jev's "which room?" answer was **right**: it picked `all`. What went wrong was the separate yes/no question, "does the user say where?". Jev was only 32–47% sure that "house lights", "my house" or "the flat" counted as naming a place. These requests mean "everywhere", but they don't name a room, and they don't literally say "all the lights" or "the whole home". Jev reads questions literally, which is a weakness TypeSafe itself documents, and it hedges on exactly these indirect mentions. Below the 0.5 cut-off, the code dropped a room Jev had actually identified correctly.

This is also where the two approaches differ structurally. Jev answers its questions **independently**: the yes/no question doesn't see that the room question was certain about `all`. Gemini decides whether to include the room and which room to use in one step, and it catches the meaning: "my house" means everywhere. It pays for that with roughly three times the latency.

"Quiet" is a different kind of literal reading. The options were described as "the sound made quieter" (`volume_down`) and "the sound silenced completely" (`mute`), and a single word "quiet" sits closer to "quieter". Arguably both readings are acceptable.

*Sidenote: the room question was reworded once. In our first run, its yes/no question asked whether the user named "a room or the whole house". With that wording, "switch on all the lights" and "turn all lights on" lost their room, with a probability of only 0.07–0.09 that a room was mentioned. Rewording it to mention "all the lights or the whole home" fixed those two, but "house lights" became borderline instead. The literal reading didn't go away; it moved to different words. The first version scored 195 with the default cut-off and 196 after tuning; it's kept in the repository for reference.*

## Tuning one cut-off, only where it's needed

The failures point to a specific fix. Jev's room choice is reliable, but its "was a room mentioned?" probabilities for whole-home requests sit below 0.5. They aren't low, though. On the test set, every command that did mention a room got at least 0.32, and every command that didn't got at most 0.16. A cut-off anywhere between those two values separates them perfectly. 0.5 sits too high.

The other two yes/no questions don't have this problem. Across all 250 commands, "was a colour mentioned?" and "was a drink mentioned?" never landed between 0.2 and 0.5. People name colours and drinks explicitly, so Jev is either clearly sure or clearly not. So we tuned **only the room cut-off**, shared by `lights.room?` and `vacuum.room?`, and left colour and drink at TypeSafe's default.

The tuning used the **50 dev commands only**. We tried every cut-off from 0.20 to 0.80, kept the one with the most fully correct calls, and broke ties in favour of the value closest to 0.5:

| Room cut-off | 0.20 | 0.25 | 0.30 – 0.80 (incl. 0.50) |
|---|---|---|---|
| Right calls on dev | 48 / 50 | **48 / 50** | 47 / 50 |

The chosen setting is stored in Jev's config:

```json
{
  "model": "jev-1.13.0",
  "stated_cutoff": 0.5,
  "stated_cutoffs": { "lights.room?": 0.25, "vacuum.room?": 0.25 },
  "tuned_on": "dev (50 rows)"
}
```

On the test set, which the tuning never saw, this one change fixed all four room mistakes and broke nothing: **195 → 199**.

Fifty dev commands is small, and the choice came down to a handful of borderline cases. The exact value (0.25) shouldn't be over-interpreted. The procedure is the point, and it carries over to a real pipeline: look at where the model hesitates, adjust only that decision, choose the value on held-out data, and confirm it once on data you haven't touched. Working with Jev was mostly straightforward: the questions follow mechanically from the API and the spec, there's no prompt to tune, and its answers come with probabilities that tell you where to look. But its literal reading means a production setup should expect a small amount of this kind of tuning, ideally on a larger dev set than ours.

## Asking "did you mean…?"

Jev's probabilities make a second safety net possible: if the call's confidence is below a threshold, ask the user to confirm instead of acting. We tried thresholds from 0.50 to 1.00 on the test set, for both cut-offs. This is a what-if analysis, not something we tuned. Each cell shows acted correctly / acted wrongly / asked the user:

| Confirm below | Default cut-off (0.5) | Room cut-off tuned (0.25) |
|---|---|---|
| never | 195 / 5 / 0 | 199 / 1 / 0 |
| 0.50 | 193 / 1 / 6 (4 of 5 mistakes caught) | 193 / 1 / 6 (0 of 1 caught) |
| 0.60 | 191 / 1 / 8 | 191 / 1 / 8 |
| 0.70 | 189 / 1 / 10 | 189 / 1 / 10 |
| 0.80 | 182 / 1 / 17 | 182 / 1 / 17 |
| 0.90 | 145 / 1 / 54 | 145 / 1 / 54 |
| 0.95 | 89 / 0 / 111 (5 of 5 caught) | 89 / 0 / 111 (1 of 1 caught) |
| 1.00 | 60 / 0 / 140 | 60 / 0 / 140 |

The two columns tell a consistent story. With the default cut-off, the four room mistakes are **uncertain** ones: their confidence is between 0.06 and 0.36. Asking for confirmation below 0.5 catches four of the five mistakes, at the cost of asking about two commands Jev had right. Tuning the cut-off fixes those same four cases outright, with no extra questions. Confirmation and tuning are two ways of dealing with the same borderline cases.

What neither can fix is a **confident** mistake. "quiet" was answered with 0.92 confidence, close to the 0.94 median of correct calls. Catching it means a threshold of 0.95, which asks the user about 111 of 200 commands. Confidence catches the cases where the model hesitates, not the cases where it is confidently literal. In practice we'd keep confirmation for high-risk actions (switching off a plug that powers a freezer) rather than apply one threshold to everything.

## Takeaways

- **Jev is much faster and cheaper:** about 3× lower median latency, 5.6× lower worst-case latency, very little variation, and about 5× lower cost. For a voice assistant, where the user waits for every request, that difference is noticeable.
- **Accuracy is close.** Both got every function right and handled every unrelated request. Out of the box Jev made 5 argument mistakes to Gemini's 1. After tuning one cut-off on 50 dev commands, both made 1.
- **Jev's mistakes are literal; the LLM's are interpretive.** Jev missed whole-home requests phrased indirectly ("house lights", "the flat") because a separately asked yes/no question read them literally. Gemini understood those, but turned "disco lights" into a purple colour change.
- **Jev's probabilities are useful in practice.** They showed exactly which decision to tune, and they let you ask for confirmation when Jev hesitates. They don't protect against confident misreadings.
- **Speculative fan-out fits this problem:** few functions, latency matters, and unused questions are nearly free. With many more functions it would need a first step that narrows down the candidates.

---

## Notes (for footnotes or an annex)

1. **Answer key.** Derived automatically from MASSIVE's intent and slot labels: e.g. `iot_hue_lightoff` with slot `house_place: kitchen` becomes `lights(action="off", room="kitchen")`. Whole-home phrasings ("house", "home", "flat", "all the lights") map to `room="all"`. An optional argument the command doesn't mention is expected to be left at its default.
2. **Scoring.** A call counts as right only if the function and every argument match. Omitted optional arguments are filled with the API default before comparing, so leaving `room` out and sending `room=None` count the same.
3. **How Jev's call confidence is computed.** Each answer the call relies on has a confidence, and the call's confidence is the **lowest** of them (the least certain part). Answers to questions about other devices are ignored.
4. **Choice confidence.** Reported by Jev as `(p_top − 1/n) / (1 − 1/n)`: how far the top option sits above an even split over *n* options. 0 means no preference; 1 means certain.
5. **Yes/no confidence.** Jev returns only a probability *p* for yes/no questions; we use `|2p − 1|`. 0.5 gives 0 (a coin flip); 0 or 1 gives 1. Note that this measures distance from 0.5, not from the cut-off. With the room cut-off at 0.25, a probability of 0.24 drops the room but still scores a confidence of 0.52.
6. **The cut-off.** An optional argument is filled in only if P(yes) for "was it mentioned?" is at or above the cut-off. Otherwise the API default applies (no room, no colour, a regular coffee). Cut-offs are set per argument; we tuned only `room`.
7. **Tuning procedure.** Dev set only, gate off, cut-offs from 0.20 to 0.80 in steps of 0.05, ties to the value closest to 0.5.
8. **Latency.** Wall-clock time around each API call, measured from the same machine for both models, including the network round trip. Both were warmed up with one untimed request.
9. **Cost.** Reported token counts multiplied by list prices. Jev: $42 per billion input tokens, output free. Gemini 3.5 Flash-Lite: $0.30 per million input, $2.50 per million output, thinking tokens billed as output (0 here).
10. **Fan-out trade-off.** All 12 questions are sent every time, and about 8 of the answers are discarded. A two-step design (first pick the function, then ask its arguments) would send roughly half the tokens but need two round trips, about double the latency. This is an estimate; we didn't measure it. At about 1,566 tokens per command, Jev's 100K tokens-per-second limit caps throughput at roughly 64 commands per second.
11. **Why VALIDATED mode.** In Gemini's default AUTO mode the model can return a value that isn't in the list (e.g. `room="attic"`). VALIDATED constrains calls to the schema, so the comparison measures understanding rather than JSON adherence, which is closer to Jev, which can only pick listed options.
12. **Where the commands come from in MASSIVE, and contamination.** MASSIVE's own test partition has only 220 smart-home commands, so we drew from all its partitions, preferring test: 160 of our commands come from MASSIVE's test partition, 36 from its dev partition and 54 from its train partition. Our own dev/test split is separate from MASSIVE's. MASSIVE is public, so either model may have seen these sentences in training; this applies to both equally and doesn't favour one over the other.
13. **Reproducibility.** All model answers are cached. The tables in this post are regenerated with no API calls by `python -m evaluation.report` (four scenarios: default and tuned cut-off, each with and without confirmation).
