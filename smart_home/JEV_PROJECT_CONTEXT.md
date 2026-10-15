# Jev research project: context and plan

Summary of the research chat so far (as of 15 Oct 2026), to drop into the project folder.

## 1. Goal

- Research TypeSafe AI's **Jev** (a "System One" decision model) for a two-part company blog series and an internal debrief for engineers.
- Run a small **proof of concept** that shows where Jev is useful compared with the LLM approach teams use today.

## 2. Jev: key facts to keep handy

- **What it is:** a decision model, not a chat model. You send a `state` (text or JSON) plus typed questions, and it returns probabilities. It generates no text. It's closed source; TypeSafe has published no architecture paper.
- **Endpoint:** `POST https://api.typesafe.ai/v1/systemone`. Python SDK: `typesafe-sdk` (`from typesafe_sdk import TypeSafeClient, Choice, Noul, NoulCriteria, Score`; `client.system_one(state=..., questions=..., model=...)`).
- **Model version:** pin `jev-1.13.0`, not `jev-latest`, so answers don't change mid-test.
- **Question types:**
  - **Noul:** yes/no, returns P(true). It has no `confidence` field.
  - **Choice:** pick one option, up to 255 options. Returns the choice, the probabilities and a confidence.
  - **Score:** an ordered scale of 2–10 levels. Returns the expected level, the probabilities, a confidence and the legend.
- **Confidence formulas** (from https://docs.typesafe.ai/confidence):
  - Choice: `(p_max - 1/n) / (1 - 1/n)`.
  - Score: also accounts for how far apart the competing levels are.
  - Noul: use the probability itself; `|2p - 1|` gives a confidence-style number if needed.
- **Pricing (vendor numbers):** $42 per billion input tokens, output free. Latency 70–500 ms.
- **Limits:**
  - 64k tokens per request, with 32k for the state plus the longest question.
  - Rate limits of 100K tokens/s and 80 requests/s, which can change without notice.
  - English gives the best results.
- **Known weaknesses** (TypeSafe's jaggedness page, https://docs.typesafe.ai/model-jaggedness/jev-1.13):
  - reads questions literally
  - math, numbers and dates
  - large irrelevant state (context rot)
  - option-order bias
  - adversarial content
  - contradictory option descriptions
- **TypeSafe's recommended patterns** (https://docs.typesafe.ai/patterns): speculative fan-out, confidence-gated routing, composite scoring, intent routing.
- **Closest open model for understanding the architecture:** vLLM Semantic Router's Decision 1.0 Lux-9B. It has published weights, code, diagrams and a METHODS.md.
  - It is a Qwen3.5-9B decoder with the text-generation head removed.
  - A small shared head scores each option's final vector against a final "query" vector, followed by a softmax.
  - It answers in one pass, with no autoregression.

## 3. Blog series status

- **Working doc:** "Jev blog series" in Google Drive, folder `Jev`:
  https://docs.google.com/document/d/1woS5nnF1KMjwofrzldv-18UVM3TMusjdL2PWsKIrtyI/edit
  - Merged from "Jev: A New Kind of AI Model - Blog Post" (Leandro's draft) and "Jev notes" (Pedro's notes).
  - The comments from both are copied in, each prefixed with its original author.
- **Blog 1 (introduction):**
  - intro and paradigm shift (YOLO/SAM analogy)
  - who built it
  - what Jev is
  - speed and cost (vendor numbers)
  - Jev + LLMs
  - how to use it (Noul, Choice, Score)
  - under the hood: the detailed Lux-9B architecture stays here
  - industry reaction
  - segue to Blog 2
- **Blog 2 (in depth):** pros and cons with mitigations; patterns; use case (this PoC); conclusions; references.
- **Agreed reorganisation still to apply:**
  - Remove the simplified pipeline section (1.5.2) and fold "Three things we can deduce" into the Lux deep dive.
  - Merge "Why would we need fast decision making?", "Jev + LLMs" and the three general use cases into one "Where Jev fits next to LLMs" section in Blog 1.
  - Blog 2's use-case section then becomes only the hands-on PoC.
  - Benchmarks: TypeSafe's own numbers in Blog 1; third-party numbers and our own PoC results in Blog 2.
  - Merge overlapping items in Blog 2:
    - cons: multi-label limit plus question independence become one con, "questions are independent"; add option-order bias as a con
    - patterns: confidence-gate plus intent routing become one "Routing" pattern
  - Conclusions: trade-offs debrief, then when to choose Jev, then opinion (Leandro's two paragraphs).
  - Fix the "[6]" citation (the parallel-questions cookbook); finish the reference entries that have no link; split the references per post; update OpenAI Decisions API pricing (public beta, $0.10 per million input tokens).
- **Add near the end of the architecture notes** (confidence explainer, short version):
  - **Confidence is not the probability of the answer.** It's a 0–1 summary of how concentrated the probabilities are. Choice measures how far the top option sits above an even split (0.85 probability gives 0.78 confidence with 3 options). Score also counts the distance between competing levels. Noul has no confidence field; values near 0.5 mean unsure.
  - **In practice:** act automatically when confidence is high, review when it's medium, route to a human when it's low, with stricter thresholds for riskier actions.

## 4. Proof of concept: smart-home assistant (tool calling)

### Why this one
- Tool calling is something teams already do with LLMs, so the comparison is fair and natural.
- Smart-home commands mostly have closed-set arguments (room, colour, device), which suits Jev. Jev picks from options; it can't write free values.
- It's inspired by TypeSafe's smart-home demo (https://docs.typesafe.ai/demos/smart-home) and the Function calling cookbook (https://docs.typesafe.ai/cookbooks).
- Ideas considered and dropped:
  - guardrails (already done before)
  - Banking77 (77 overlapping intents, possible training contamination)
  - Twitch, comments, feeds (nobody uses an LLM for these today, so there's no natural baseline)

### Scope decisions
- Keep it simple. **No** LLM splitting of compound requests and **no** conversational LLM fallback, unlike TypeSafe's demo.
  - Drop compound commands from the sample.
  - Count "general question" as "no call".
  - Mention in one sentence that a real assistant would hand those cases to an LLM.
- Each approach follows its own best practice. **No** asking the LLM for probabilities.

### Dataset
- **MASSIVE** (Amazon, CC BY 4.0): Alexa-style commands with intent and slot labels, in 51 languages.
- Take 200 English smart-home (`iot`) commands from the test split.
- Add 30 unrelated commands (weather, news, qa, general, datetime, cooking) labelled `no_call`.
- Mark 50 rows as `dev` (for choosing the threshold) and the rest as `test`.
- Caveat for the blog: it's a public benchmark, so the models may have seen it in training.

### Jev side (follows the smart-home demo)
- **One request per command, all questions together** (speculative fan-out):
  - category: smart-home command / general question / other
  - room: each room / whole house / not mentioned
  - device: lights / vacuum / coffee machine / plug ...
  - one action question per device (speculative)
  - light colour (speculative)
- Give every option a short description.
- Code assembles the function call from the answers that apply.
- **Confidence gate:** return "clarify" (did you mean...?) when confidence on category, device or action is below a threshold chosen on the dev rows only.

### LLM side (baseline)
- **Model:** `gemini-3.5-flash-lite`, on the free tier ($0.30 per million input tokens and $2.50 per million output on paid). Optionally add `claude-haiku-5-5` later.
- **Setup:**
  - Native tool calling, with the same functions as tools and the closed argument options as fixed lists in the schema.
  - Allow "no tool call".
  - Short system prompt: "controls a smart home".
- **Settings:**
  - Thinking at the lowest level.
  - Don't set temperature, top_p or top_k; they're deprecated on the newest Gemini models.
  - (If Claude is added, leave thinking off and use temperature 0.)
- **The free tier has strict rate limits:** throttle requests and add retry with backoff.

### Shared answer key
- Both approaches produce the same target calls, e.g. `lights(action, room, color)`, `vacuum(action, room)`, `coffee(type)`.
- Map MASSIVE intents to these calls (e.g. `iot_hue_lightoff` becomes `lights(action="off")`).

### Metrics
- right function
- right arguments
- correct "no call" on the unrelated commands
- delay per command (typical and slowest)
- cost per 1,000 commands
- invalid LLM tool calls
- for Jev: whether the "clarify" cases are mostly the ones it would have got wrong

### Expected story (stated fairly)
- Similar results on clear commands.
- Jev is much faster and cheaper, and asks "did you mean...?" instead of acting wrongly.
- The LLM may handle odd phrasing better, and it's the only option for free-text values (e.g. "alarm at 6:45").

## 5. Step plan and status

| # | Step | Status |
|---|---|---|
| 1 | Set up access: Jev API key, Gemini free-tier key, install SDKs | Done (keys available) |
| 2 | Load commands: run `step2_load_massive.py` (downloads MASSIVE, writes `commands.csv`, prints the intents and slot values) | Script written, **not run yet** |
| 3 | Define target functions and argument options from step 2's printed summary; add an `expected_call` column | Next |
| 4 | Build the Jev request (fan-out questions, call assembly, confidence gate) | To do |
| 5 | Build the Gemini tool-calling baseline with the same functions | To do |
| 6 | Run both, a few requests at a time (throttled for the free tier), and cache answers, latency and token usage to JSON | To do |
| 7 | Score and compare (metrics above); one results table | To do |
| 8 | Optional Portuguese bonus: same 50 commands from `pt-PT` (matching IDs; the file is already extracted by the step 2 script). Then write-up: table plus 3 examples (both right, LLM better, Jev asked to clarify) | To do |

**Immediate next action:** run `python step2_load_massive.py` (needs `pandas`), then use the printed intent and slot summary to design the functions in step 3.

## 6. Key links

- TypeSafe docs: https://docs.typesafe.ai/introduction
- Confidence: https://docs.typesafe.ai/confidence
- Patterns: https://docs.typesafe.ai/patterns
- Cookbooks: https://docs.typesafe.ai/cookbooks
- Smart-home demo: https://docs.typesafe.ai/demos/smart-home
- Jaggedness / limitations: https://docs.typesafe.ai/model-jaggedness/jev-1.13
- Parallel-questions cookbook (the 12.2x batching benchmark): https://docs.typesafe.ai/cookbooks/parallel_questions
- Lux-9B (architecture reference): https://huggingface.co/vllm-sr/Decision-1.0-Lux-9B
- MASSIVE dataset: https://github.com/alexa/massive
- Gemini models: https://ai.google.dev/gemini-api/docs/models
