# GenAI-Powered Billing Support Agent - GCP Reference Implementation

A GenAI-powered virtual agent for telecom billing inquiries, built on Google Cloud:
Dialogflow CX (Conversational Agents), Vertex AI (Gemini), Cloud Functions, Pub/Sub,
BigQuery, and Cloud Monitoring.

This repo implements the components for the GCP GenAI hands-on assignment. Each task
maps to a folder below. Code is written to be deployable (correct syntax, real SDK
usage) but has not been deployed end-to-end in a production environment — it was
built and partially tested in a GCP free-tier sandbox project.

## Repo structure

```
.
├── dialogflow/                     # Task 1 — Intent definition
│   └── intent_billing_inquiry_high_bill.json
├── functions/
│   ├── high_bill_explanation/      # Task 2 — Vertex AI webhook fulfillment
│   │   ├── main.py
│   │   └── requirements.txt
│   ├── promise_extraction/         # Task 3 — Post-call promise extraction
│   │   ├── main.py
│   │   └── requirements.txt
│   └── notify_after_call/          # Task 4 — Pub/Sub-triggered email notification
│       ├── main.py
│       └── requirements.txt
├── sql/
│   └── promise_analytics.sql       # Task 5 — BigQuery analytics query
├── monitoring/
│   └── alert_policy.yaml           # Task 6 — Cloud Monitoring alert policy
├── guardrails/
│   └── pii_redaction.py            # Task 7 — Responsible AI: PII redaction guardrail
└── docs/
    └── architecture.md             # End-to-end flow + design notes
```

## Architecture (high level)

1. Customer asks about their bill → Dialogflow CX matches `billing.inquiry.high_bill`.
2. Route triggers webhook → `functions/high_bill_explanation` calls Vertex AI (Gemini)
   with a grounded prompt built from the customer's real billing data.
3. When the call ends, a transcript-analysis step runs `functions/promise_extraction`
   to pull out any refund/credit/follow-up commitments as structured JSON.
4. A Pub/Sub message on `conversation-ended` triggers `functions/notify_after_call`,
   which emails a summary + extracted promises to a stakeholder via SendGrid.
5. Conversation and promise data lands in BigQuery; `sql/promise_analytics.sql`
   surfaces fulfillment-rate trends.
6. `monitoring/alert_policy.yaml` defines an alert if the webhook's error rate
   exceeds 5% over 5 minutes.
7. `guardrails/pii_redaction.py` scrubs PII from transcripts before they're logged,
   and the Task 2 prompt itself enforces a grounding constraint (see
   `docs/architecture.md`).

## Setup (for actually deploying)

```bash
# 1. Set your project
gcloud config set project YOUR_PROJECT_ID

# 2. Enable required APIs
gcloud services enable dialogflow.googleapis.com \
  aiplatform.googleapis.com \
  cloudfunctions.googleapis.com \
  pubsub.googleapis.com \
  bigquery.googleapis.com \
  monitoring.googleapis.com

# 3. Deploy the webhook function
cd functions/high_bill_explanation
gcloud functions deploy high-bill-explanation \
  --gen2 --runtime=python312 --trigger-http \
  --entry-point=high_bill_explanation --region=us-central1 \
  --allow-unauthenticated

# 4. Deploy the notification function (Pub/Sub trigger)
cd ../notify_after_call
gcloud functions deploy notify-after-call \
  --gen2 --runtime=python312 \
  --trigger-topic=conversation-ended \
  --entry-point=notify_after_call --region=us-central1 \
  --set-secrets=SENDGRID_API_KEY=sendgrid-api-key:latest

# 5. Import the intent (via Dialogflow CX console or API — see dialogflow/README notes)

# 6. Create the alert policy
gcloud alpha monitoring policies create --policy-from-file=monitoring/alert_policy.yaml
```

## Notes

- `SENDGRID_API_KEY` and any billing-data connector credentials are expected to be
  provided via Secret Manager, not hardcoded.
- The BigQuery table `billing_conversations` is a production dependency and is not
  created by this repo — see `sql/promise_analytics.sql` for the expected schema.
