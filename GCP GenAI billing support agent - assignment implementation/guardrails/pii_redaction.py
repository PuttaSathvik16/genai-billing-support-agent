"""
Task 7, Guardrail 2: PII redaction.

Strips SSNs, card numbers, and phone numbers out of call transcripts before
they are written to Cloud Logging or BigQuery. Applied in
functions/notify_after_call/main.py immediately before any transcript text
is logged.

Run the built-in tests with:
    python guardrails/pii_redaction.py
"""

import re

PII_PATTERNS = [
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN_REDACTED]"),
    (re.compile(r"\b(?:\d[ -]*?){13,16}\b"), "[CARD_REDACTED]"),
    (re.compile(r"\b\d{10}\b"), "[PHONE_REDACTED]"),
]


def redact(text: str) -> str:
    """Replaces PII patterns in `text` with redaction placeholders.

    This is a defense-in-depth pattern-matching guardrail — not a substitute
    for a proper DLP scan (see note below), but cheap enough to run inline on
    every transcript before it's persisted anywhere.
    """
    if not text:
        return text
    redacted = text
    for pattern, replacement in PII_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


# Note: for production-grade coverage (names, addresses, less-structured PII),
# this should be paired with Cloud DLP's inspectContent API rather than relying
# on regex alone. Regex catches the highest-risk, most-structured cases cheaply
# and synchronously, which is why it's used inline here.


if __name__ == "__main__":
    tests = [
        (
            "My SSN is 123-45-6789, please update my file.",
            "My SSN is [SSN_REDACTED], please update my file.",
        ),
        (
            "Card number is 4111 1111 1111 1111 for the payment.",
            "Card number is [CARD_REDACTED] for the payment.",
        ),
        (
            "Call me back at 5551234567 tomorrow.",
            "Call me back at [PHONE_REDACTED] tomorrow.",
        ),
        (
            "No sensitive info in this line at all.",
            "No sensitive info in this line at all.",
        ),
    ]

    passed = 0
    for original, expected in tests:
        result = redact(original)
        ok = result == expected
        passed += ok
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {original!r} -> {result!r}")

    print(f"\n{passed}/{len(tests)} tests passed.")
