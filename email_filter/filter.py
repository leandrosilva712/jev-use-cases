"""Triage an inbox with Jev: one request per email, four questions answered in parallel.

Run:  uv run python -m email_filter.filter
"""
import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

load_dotenv()  # reads TYPESAFE_API_KEY from .env

HERE = Path(__file__).parent
CATEGORIES = {
    "billing": "Invoices, payments, charges, refunds, subscriptions",
    "technical": "Bugs, outages, errors, IT or account-access problems",
    "sales": "Pricing, quotes, demos, partnerships, purchases",
    "hr": "Payroll, leave, onboarding, hiring, benefits",
    "newsletter": "Bulk newsletters and digests the recipient subscribed to",
    "spam": "Unsolicited junk, ads, scams",
}
QUEUES = ["billing", "technical", "sales", "hr"]  # categories that go to a human queue

# The four judgments. Each is answered independently from the same email.
QUESTIONS = {
    "category": Choice(instructions="Which topic is this email about?", criteria=CATEGORIES),
    "phishing": Noul(instructions="The email tries to trick the reader into giving up credentials, money or "
                                  "personal data, for example with a fake login link or a fake prize."),
    "urgency": Score(instructions="How quickly does this email need a human response?",
                     criteria=["Can wait, no deadline or impact", "Should be handled today", "Needs immediate attention"]),
    "needs_reply": Noul(instructions="The sender expects a personal reply from the recipient."),
}


def decide_action(category, phishing, urgency, phishing_threshold):
    """Plain code turns the judgments into an action."""
    if phishing >= phishing_threshold:
        return "quarantine"
    if category in ("newsletter", "spam"):
        return "archive"
    priority = "P1" if urgency >= 1.5 else "P2" if urgency >= 0.5 else "P3"
    return f"route:{category} {priority}"


def triage(jev, email, phishing_threshold):
    state = {"from": email["from"], "subject": email["subject"], "body": email["body"]}
    start = time.perf_counter()
    response = jev.system_one(state=state, questions=QUESTIONS)
    seconds = time.perf_counter() - start
    answers = response.answers
    category = answers["category"].choice
    phishing = answers["phishing"].noul
    urgency = answers["urgency"].score
    needs_reply = answers["needs_reply"].noul
    return {
        "id": email["id"],
        "subject": email["subject"],
        "action": decide_action(category, phishing, urgency, phishing_threshold),
        "category": category,
        "phishing": phishing,
        "urgency": urgency,
        "needs_reply": needs_reply,
        "tokens_in": response.usage.input_tokens,
        "tokens_out": response.usage.output_tokens,
        "latency_ms": seconds * 1000,
    }


def accuracy(results, emails, phishing_threshold):
    """Compare each judgment with the `expected` labels."""
    hits = {"category": 0, "phishing": 0, "urgency": 0, "needs_reply": 0}
    for r, email in zip(results, emails):
        want = email["expected"]
        hits["category"] += r["category"] == want["category"]
        hits["phishing"] += (r["phishing"] >= phishing_threshold) == want["phishing"]
        hits["urgency"] += round(r["urgency"]) == want["urgency"]
        hits["needs_reply"] += (r["needs_reply"] >= 0.5) == want["needs_reply"]
    return {name: count / len(emails) for name, count in hits.items()}


def main():
    parser = argparse.ArgumentParser(description="Jev email filter")
    parser.add_argument("--phishing-threshold", type=float, default=0.5, help="P(phishing) at or above this is quarantined")
    args = parser.parse_args()

    emails = json.loads((HERE / "emails.json").read_text())
    jev = TypeSafeClient()
    results = [triage(jev, email, args.phishing_threshold) for email in emails]

    print(f"{'id':>2}  {'subject':<38} {'action':<22} {'phish':>5} {'urg':>4} {'reply':>5} {'ms':>6}")
    for r in results:
        print(f"{r['id']:>2}  {r['subject'][:38]:<38} {r['action']:<22} {r['phishing']:>5.2f} {r['urgency']:>4.1f} {r['needs_reply']:>5.2f} {r['latency_ms']:>6.0f}")

    scores = accuracy(results, emails, args.phishing_threshold)
    tokens_in = sum(r["tokens_in"] for r in results)
    tokens_out = sum(r["tokens_out"] for r in results)
    print("\naccuracy vs expected: " + ", ".join(f"{name} {value:.0%}" for name, value in scores.items()))
    print(f"tokens: {tokens_in} in / {tokens_out} out over {len(emails)} emails")
    latencies = sorted(r["latency_ms"] for r in results)
    latency = {"avg_ms": sum(latencies) / len(latencies), "p50_ms": latencies[len(latencies) // 2], "max_ms": latencies[-1]}
    print(f"jev latency per email: avg {latency['avg_ms']:.0f} ms, p50 {latency['p50_ms']:.0f} ms, max {latency['max_ms']:.0f} ms")

    (HERE / "results.json").write_text(json.dumps({"accuracy": scores, "tokens_in": tokens_in,
                                                   "tokens_out": tokens_out, "latency": latency, "results": results}, indent=2))
    print(f"wrote {HERE / 'results.json'}")


if __name__ == "__main__":
    main()
