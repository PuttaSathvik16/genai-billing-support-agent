"""
Cloud Function (Gen2, HTTP trigger) that serves as the Dialogflow CX webhook
fulfillment for the billing.inquiry.high_bill intent.

Deploy:
    gcloud functions deploy high-bill-explanation \
      --gen2 --runtime=python312 --trigger-http \
      --entry-point=high_bill_explanation --region=us-central1 \
      --allow-unauthenticated
"""

import os
import logging

import functions_framework
import vertexai
from vertexai.generative_models import (
    GenerativeModel,
    GenerationConfig,
    HarmCategory,
    HarmBlockThreshold,
)

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id")
LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")
MODEL_NAME = os.environ.get("VERTEX_MODEL", "gemini-1.5-flash-002")

vertexai.init(project=PROJECT_ID, location=LOCATION)
_model = GenerativeModel(MODEL_NAME)

PROMPT_TEMPLATE = """You are a telecom billing support assistant. Using ONLY the
billing data provided below, write a short, empathetic explanation (2-3
sentences) of why this customer's bill increased. Do not invent charges,
dates, or amounts that are not in the data. If the data does not fully
explain the increase, say so honestly and offer to escalate to a human agent.

Billing data:
- Previous bill: {previous_amount}
- Current bill: {current_amount}
- New charges: {new_charges}
- Plan changes: {plan_changes}
- One-time fees: {one_time_fees}
"""

# Guardrail: Vertex AI safety filters (Task 7, guardrail 3)
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
}


def _extract_billing_data(session_params: dict) -> dict:
    """Pulls billing_data out of the Dialogflow CX session parameters,
    with safe fallbacks so a missing field doesn't crash the webhook."""
    billing_data = session_params.get("billing_data", {}) or {}
    return {
        "previous_amount": billing_data.get("previous_amount", "unknown"),
        "current_amount": billing_data.get("current_amount", "unknown"),
        "new_charges": billing_data.get("new_charges", "None"),
        "plan_changes": billing_data.get("plan_changes", "None"),
        "one_time_fees": billing_data.get("one_time_fees", "None"),
    }


@functions_framework.http
def high_bill_explanation(request):
    """Dialogflow CX webhook fulfillment entry point."""
    try:
        req = request.get_json(silent=True) or {}
        session_info = req.get("sessionInfo", {})
        params = session_info.get("parameters", {})

        billing_data = _extract_billing_data(params)
        prompt = PROMPT_TEMPLATE.format(**billing_data)

        response = _model.generate_content(
            prompt,
            generation_config=GenerationConfig(
                temperature=0.2,       # low temperature: factual, not creative
                max_output_tokens=220,
            ),
            safety_settings=SAFETY_SETTINGS,
        )

        explanation_text = response.text if response.candidates else (
            "I wasn't able to generate an explanation right now — "
            "let me connect you with a human agent."
        )

        return {
            "fulfillment_response": {
                "messages": [
                    {"text": {"text": [explanation_text]}}
                ]
            }
        }

    except Exception as exc:  # noqa: BLE001
        logging.exception("high_bill_explanation webhook failed: %s", exc)
        return {
            "fulfillment_response": {
                "messages": [
                    {"text": {"text": [
                        "Sorry, I'm having trouble pulling up your billing "
                        "details right now. Let me get you a human agent."
                    ]}}
                ]
            }
        }, 200  # return 200 so Dialogflow CX still shows a graceful message
