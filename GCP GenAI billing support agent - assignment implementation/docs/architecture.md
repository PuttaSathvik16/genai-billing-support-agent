# Architecture & Design Notes

## End-to-end flow

1. **Customer message → Dialogflow CX** matches `billing.inquiry.high_bill`
   (see `dialogflow/intent_billing_inquiry_high_bill.json`).
2. **Route → Webhook** (`dialogflow/route_billing_high_bill.yaml`) calls
   `functions/high_bill_explanation`, which prompts Gemini with the
   customer's real billing data and returns a grounded explanation.
3. **Call ends → transcript analysis** runs `functions/promise_extraction`
   against the transcript, producing structured JSON of any promises made.
4. **Pub/Sub `conversation-ended` event** triggers
   `functions/notify_after_call`, which emails a summary + promises to a
   stakeholder via SendGrid, after redacting PII from the logged transcript
   (`guardrails/pii_redaction.py`).
5. **Conversation + promise data → BigQuery.** `sql/promise_analytics.sql`
   tracks promise volume and fulfillment rate over time.
6. **Cloud Monitoring** (`monitoring/alert_policy.yaml`) watches the
   webhook's error rate and alerts on-call if it exceeds 5% over 5 minutes.

## Key design decisions

**Why a webhook instead of a static Dialogflow response?**
The answer depends on the specific customer's real billing data, which can't
be hardcoded into a canned response.

**Why `temperature=0.2` on the explanation call, `temperature=0.0` on
extraction?**
The explanation needs to sound natural but stay factual — a small amount of
temperature keeps phrasing from feeling robotic while still being grounded.
Extraction is a structured-data task with one correct answer per transcript,
so temperature is set to 0 for maximum determinism.

**Why Pub/Sub instead of calling the notification function directly from the
webhook?**
Decoupling. If email delivery is slow or temporarily down, it shouldn't block
the live conversation from completing. Pub/Sub buffers the event and lets the
notification function retry independently.

**Why redact PII before logging rather than after?**
Once PII is written to Cloud Logging or BigQuery, it's in scope for
compliance/audit even if deleted later. Redacting inline, before the first
write, means those systems never see the raw sensitive data in the first
place.

## Guardrails (Responsible AI)

1. **Grounding constraint** — the Task 2 prompt explicitly restricts Gemini
   to the supplied `billing_data` and instructs it to say so honestly if the
   data doesn't fully explain an increase, rather than guessing. This is the
   single highest-value guardrail for this use case: a hallucinated dollar
   figure in a billing explanation is both a trust problem and a potential
   compliance issue.
2. **PII redaction** (`guardrails/pii_redaction.py`) — regex-based, applied
   inline before any transcript text is persisted. Covers SSNs, card
   numbers, and phone numbers. Documented limitation: for full PII coverage
   (names, addresses), this should be paired with Cloud DLP's
   `inspectContent` API rather than relying on regex alone.
3. **Vertex AI safety filters** — configured in
   `functions/high_bill_explanation/main.py` via `safety_settings`, blocking
   hate speech, dangerous content, sexually explicit content, and harassment
   at the `BLOCK_LOW_AND_ABOVE` threshold.

## What's not included (and why)

- **No Terraform/IaC for the full stack.** The `gcloud` commands in the
  README are sufficient for the assignment scope; a production rollout
  would move these into Terraform.
- **No `billing_conversations` table creation script.** That table is owned
  by the production conversation-logging pipeline, outside this repo's
  scope — `sql/promise_analytics.sql` documents the expected schema instead.
- **Cloud DLP integration** for full-coverage PII detection is noted as a
  follow-up rather than implemented, to keep the guardrail fast and
  dependency-light for this exercise.
