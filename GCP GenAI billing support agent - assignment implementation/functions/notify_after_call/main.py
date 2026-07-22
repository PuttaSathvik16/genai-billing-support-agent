"""
Cloud Function (Gen2, Pub/Sub trigger) that fires when a conversation ends.
Publishes a summary + extracted promises email via SendGrid.

Deploy:
    gcloud functions deploy notify-after-call \
      --gen2 --runtime=python312 \
      --trigger-topic=conversation-ended \
      --entry-point=notify_after_call --region=us-central1 \
      --set-secrets=SENDGRID_API_KEY=sendgrid-api-key:latest

Expected Pub/Sub message payload (base64-encoded JSON):
{
  "conversation_id": "conv_12345",
  "call_summary": "Customer asked about a $25.70 bill increase...",
  "extracted_promises": [
    {"promise_type": "credit", "amount": 42.00,
     "timeframe": "3-5 business days", "description": "..."}
  ],
  "stakeholder_email": "billing-team@example.com",
  "raw_transcript": "Agent: ...\\nCustomer: ..."
}
"""

import os
import json
import base64
import logging
import sys

import functions_framework
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "..", "guardrails"))
from pii_redaction import redact  # Task 7 guardrail, reused here for the logged transcript

FROM_EMAIL = os.environ.get("NOTIFY_FROM_EMAIL", "billing-genai@telecom.com")


def _build_email_body(payload: dict) -> str:
    lines = [f"Call Summary: {payload.get('call_summary', 'N/A')}", "", "Promises made:"]
    promises = payload.get("extracted_promises", [])
    if not promises:
        lines.append("- None")
    for pr in promises:
        amount = pr.get("amount")
        amount_str = f"${amount:.2f}" if amount is not None else "N/A"
        lines.append(
            f"- {pr.get('promise_type', 'unknown').title()}: {amount_str} "
            f"within {pr.get('timeframe', 'unspecified')} "
            f"— {pr.get('description', '')}"
        )
    return "\n".join(lines)


@functions_framework.cloud_event
def notify_after_call(cloud_event):
    try:
        message_data = cloud_event.data["message"].get("data", "")
        payload = json.loads(base64.b64decode(message_data).decode("utf-8"))

        stakeholder_email = payload.get("stakeholder_email")
        if not stakeholder_email:
            logging.error("No stakeholder_email in payload, skipping send.")
            return

        # Guardrail: redact PII before this transcript is logged anywhere downstream.
        if "raw_transcript" in payload:
            logging.info(
                "Redacted transcript for audit log: %s",
                redact(payload["raw_transcript"]),
            )

        body = _build_email_body(payload)

        message = Mail(
            from_email=FROM_EMAIL,
            to_emails=stakeholder_email,
            subject=f"Call Summary - {payload.get('conversation_id', 'unknown')}",
            plain_text_content=body,
        )

        api_key = os.environ["SENDGRID_API_KEY"]
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        logging.info("SendGrid response status: %s", response.status_code)

    except KeyError as exc:
        logging.exception("Missing required config or payload field: %s", exc)
    except Exception as exc:  # noqa: BLE001
        logging.exception("notify_after_call failed: %s", exc)
        raise  # let Pub/Sub retry on unexpected failures
