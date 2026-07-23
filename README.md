# GenAI-Powered Billing Support Agent - GCP Reference Implementation
# GCP Generative AI - Hands - on Coding Assignment

**Sathvik Putta | Virtusa Corporation**

A GenAI-powered virtual agent for telecom billing inquiries, built on Google Cloud:
Dialogflow CX (Conversational Agents), Vertex AI (Gemini), Cloud Functions, Pub/Sub,
BigQuery, and Cloud Monitoring.

This repo implements the components for the GCP GenAI hands-on assignment. Each task
maps to a folder below. Code is written to be deployable (correct syntax, real SDK
usage) but has not been deployed end-to-end in a production environment - it was
built and partially tested in a GCP free-tier sandbox project.

**Business Scenario:** GenAI - powered virtual agent for telecom billing inquiries - response generation, promise extraction, post-call notification, analytics, and monitoring.


## Repo structure

```
.
├── dialogflow/                     # Task 1 - Intent definition
│   └── intent_billing_inquiry_high_bill.json
├── functions/
│   ├── high_bill_explanation/      # Task 2 - Vertex AI webhook fulfillment
│   │   ├── main.py
│   │   └── requirements.txt
│   ├── promise_extraction/         # Task 3 - Post-call promise extraction
│   │   ├── main.py
│   │   └── requirements.txt
│   └── notify_after_call/          # Task 4 - Pub/Sub-triggered email notification
│       ├── main.py
│       └── requirements.txt
├── sql/
│   └── promise_analytics.sql       # Task 5 - BigQuery analytics query
├── monitoring/
│   └── alert_policy.yaml           # Task 6 - Cloud Monitoring alert policy
├── guardrails/
│   └── pii_redaction.py            # Task 7 - Responsible AI: PII redaction guardrail
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


   ---

## Task 1 - Dialogflow CX: Intent & Flow

**Intent: `billing.inquiry.high_bill`** - training phrases

- Why is my bill so high this month?
- My bill went up and I don't understand why.
- I was charged more than usual, can you explain this?

**Route (pseudo-config)**

```yaml
route: billing_high_bill_route
condition: $intent.name = 'billing.inquiry.high_bill'
triggerFulfillment: webhook 'billing-genai-webhook', tag 'high_bill_explanation'
targetPage: Billing_Explanation_Page
```

**Webhook / fulfillment service**

The route calls a webhook fulfillment tag (`high_bill_explanation`) that is served by a Cloud Function (Python, Cloud Functions Gen2, HTTP trigger). Dialogflow CX passes the WebhookRequest JSON (session params, detected intent, fulfillmentInfo.tag); the function reads `billing_data` from the session parameters (populated earlier in the flow via a data connector to the billing system) and returns a WebhookResponse with the generated explanation text.

<img width="1798" height="969" alt="Task1_Dialogflow_Intent" src="https://github.com/user-attachments/assets/dc273776-3824-46bc-aea6-c162f88343af" />


*Screenshot: billing.inquiry.high_bill intent, saved with all 4 training phrases (Conversational Agents console).*

---

## Task 2 - Vertex AI: Generative Billing Response

Fulfillment function (pseudo-code). It calls Vertex AI's Gemini model with a grounded prompt built from the customer's actual `billing_data`, so the model explains rather than invents numbers:

```python
model = GenerativeModel('gemini-1.5-flash')

prompt = f"""
Using ONLY this billing data, explain in 2-3 sentences why the bill
increased. Do not invent numbers. Previous: {prev}, Current: {curr},
New charges: {new_charges}
"""

response = model.generate_content(prompt, temperature=0.2)
return response.text
```

<img width="1788" height="931" alt="Task2_VertexAI_Response" src="https://github.com/user-attachments/assets/498700cb-cb3d-47d1-8d8a-a37e1fe94650" />


*Screenshot: live Gemini response in Agent Platform Studio, grounded in the sample billing data with no invented figures.*

---

## Task 3 - Conversation Profile: Promise Extraction

**Extraction prompt**

```
Extract every refund/credit/follow-up promise from this transcript.
Return JSON array: [{promise_type, amount, timeframe, description}]
```

**Example transcript -> expected output**

```
Agent: I'll credit you $42, it'll post in 3 to 5 business days.

-> [{"promise_type": "credit",
     "amount": 42.00,
     "timeframe": "3 to 5 business days",
     "description": "Issue a $42 credit to the account to resolve
                      a double-billed data add-on dispute."}]
```

<img width="1791" height="925" alt="Task3_PromiseExtraction" src="https://github.com/user-attachments/assets/75077bc4-d438-4e75-ba8e-6949ae5cbfd0" />


*Screenshot: live extraction run producing valid structured JSON from a sample transcript.*

---

## Task 4 - Post-Conversation Email Notification

A Cloud Function is triggered by a Pub/Sub message published when Dialogflow CX (or the CCAI Insights pipeline) marks the conversation as ended. It composes the call summary and extracted promises, then sends the notification through SendGrid.

```python
def notify_after_call(event):
    data = decode(event)  # call_summary, promises, stakeholder_email
    body = f"Summary: {data['call_summary']}\nPromises: {data['promises']}"
    send_email(to=data['stakeholder_email'], subject='Call Summary', body=body)
```

GCP services: Pub/Sub (conversation-ended event) triggers Cloud Functions; SendGrid/SMTP sends the email.

<img width="1785" height="930" alt="Task4_CloudFunctions_Setup" src="https://github.com/user-attachments/assets/a0dce58c-5567-4dcc-8384-00aaf7251b12" />


*Screenshot: Cloud Run functions creation form with the trigger dropdown open, showing Pub/Sub, Cloud Storage, Firestore, and Eventarc options. No function was deployed.*

---

## Task 5 - Conversation Insights: Analytics

Conversation data is stored in BigQuery (table: `billing_conversations`).

```sql
SELECT promise_type, COUNT(*) AS count, AVG(amount) AS avg_amount,
       SUM(IF(fulfilled, 1, 0)) / COUNT(*) AS fulfillment_rate
FROM billing_conversations
WHERE call_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 4 WEEK)
GROUP BY promise_type;
```

Business value: flags whether agents are promising more than the org can fulfill — an early signal of process or trust breakdown.

<img width="1783" height="929" alt="Task5_BigQuery_Query" src="https://github.com/user-attachments/assets/b188b3ae-32eb-4f84-af39-4f65a8cd1894" />


*Screenshot: query executed in BigQuery Studio. Expected error shown since billing_conversations is a production table not provisioned in this sandbox project.*

---

## Task 6 - Monitoring & Observability

**GenAI behavior**
- Cloud Logging: every Vertex AI call logs prompt, response, latency, and token counts as structured JSON log entries for audit and drift review.
- Cloud Monitoring custom metric: `genai/response_confidence` and `genai/grounding_score` (derived from response vs. billing_data match) charted over time.

**System health**
- Cloud Monitoring dashboards on Cloud Functions: invocation count, error rate, p95 latency, cold-start count.
- Error Reporting: automatically groups uncaught exceptions from the webhook and notification functions.

**Business KPIs**
- Dialogflow CX built-in analytics: containment rate, escalation rate, average handle time.
- BigQuery scheduled query feeding a Looker Studio dashboard for promise volume and fulfillment rate (from Task 5).

**Alert condition**

Cloud Monitoring alerting policy: if the webhook Cloud Function's error rate exceeds 5% over a rolling 5-minute window (metric: `cloudfunctions.googleapis.com/function/execution_count` filtered on `status != 'ok'`), fire a notification to the on-call Slack channel and PagerDuty. This catches Vertex AI outages or malformed billing_data before it silently degrades the customer experience.

<img width="1796" height="925" alt="Task6_Monitoring_Alerting" src="https://github.com/user-attachments/assets/2910a8ae-000d-4c51-bf57-8ce02ee8968d" />


*Screenshot: Cloud Monitoring "Create alerting policy" screen showing the condition-builder, metric selector, and log-based/SQL alert options. No policy was created.*

---

## Task 7 - Responsible AI Guardrails (Bonus)

**1. Grounding constraint (applied in the prompt, Task 2)**

The prompt in Task 2 explicitly restricts the model to the billing_data provided and instructs it to say so honestly rather than invent figures when the data is incomplete. This is a prompt-level guardrail rather than a code-level filter.

Justification: hallucinated dollar amounts or dates in a billing explanation create real financial and regulatory exposure for the telecom (a customer could reasonably act on a wrong figure the bot stated). Constraining the model to only the supplied structured data keeps every generated claim traceable back to a system-of-record value.

**2. PII redaction before logging**

```python
import re

PII_PATTERNS = [
    (r'\b\d{3}-\d{2}-\d{4}\b', '[SSN_REDACTED]'),
    (r'\b(?:\d[ -]*?){13,16}\b', '[CARD_REDACTED]'),
    (r'\b\d{10}\b', '[PHONE_REDACTED]'),
]

def redact(text: str) -> str:
    for pattern, replacement in PII_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text

# applied immediately before writing to Cloud Logging / BigQuery
logging.info(redact(transcript))
```

Justification: transcripts and logs routinely contain account numbers, phone numbers, or card fragments read aloud by customers. Redacting before persistence keeps Cloud Logging and BigQuery exports out of PCI/PII scope and limits blast radius if logs are ever over-shared internally.

**3. Vertex AI safety filters**

`safety_settings` block harassment/hate/dangerous-content categories on the `generate_content` call — guards against abusive transcript content leaking into the response.

<img width="1787" height="977" alt="Task7_SafetySettings" src="https://github.com/user-attachments/assets/fc7746e1-e61a-42e1-99d2-48692a93abec" />


*Screenshot: Safety filter settings panel in Agent Platform Studio showing the four filter categories (Hate speech, Dangerous content, Sexually explicit content, Harassment content).*

---

*Note: code is pseudo-code per assignment scope, not production-ready. Screenshots above show live testing of the Dialogflow CX intent and Vertex AI prompts within the allotted sandbox project, without full end-to-end deployment.*

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
