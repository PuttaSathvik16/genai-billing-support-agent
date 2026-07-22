"""
Cloud Function (Gen2, HTTP trigger) that analyzes a completed call transcript
and extracts any refund/credit/follow-up promises the agent made, returning
structured JSON.

Can be called directly, or wired into a CCAI Insights post-call pipeline.

Deploy:
    gcloud functions deploy promise-extraction \
      --gen2 --runtime=python312 --trigger-http \
      --entry-point=extract_promises --region=us-central1
"""

import os
import json
import logging

import functions_framework
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "your-gcp-project-id")
LOCATION = os.environ.get("VERTEX_LOCATION", "us-central1")
MODEL_NAME = os.environ.get("VERTEX_MODEL", "gemini-1.5-flash-002")

vertexai.init(project=PROJECT_ID, location=LOCATION)
_model = GenerativeModel(MODEL_NAME)

EXTRACTION_PROMPT = """You are a QA analyst reviewing a billing support call
transcript. Extract every promise the agent made to the customer. A promise
is any commitment involving a refund, credit, or follow-up action.

Return ONLY valid JSON, an array of objects, each with:
- promise_type: "refund" | "credit" | "follow_up" | "callback"
- amount: numeric value in USD, or null if not applicable
- timeframe: e.g. "3-5 business days", or null if not stated
- description: one-sentence summary of the commitment

If no promises were made, return an empty array.

Transcript:
{transcript}
"""

# Response schema enforced via Gemini's structured output mode, so we get
# back parseable JSON instead of free text wrapped in prose.
RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "promise_type": {
                "type": "STRING",
                "enum": ["refund", "credit", "follow_up", "callback"],
            },
            "amount": {"type": "NUMBER", "nullable": True},
            "timeframe": {"type": "STRING", "nullable": True},
            "description": {"type": "STRING"},
        },
        "required": ["promise_type", "description"],
    },
}


def _extract(transcript: str) -> list:
    prompt = EXTRACTION_PROMPT.format(transcript=transcript)
    response = _model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            temperature=0.0,  # deterministic extraction, not generative writing
            response_mime_type="application/json",
            response_schema=RESPONSE_SCHEMA,
        ),
    )
    return json.loads(response.text)


@functions_framework.http
def extract_promises(request):
    try:
        body = request.get_json(silent=True) or {}
        transcript = body.get("transcript", "").strip()

        if not transcript:
            return {"error": "Missing 'transcript' in request body."}, 400

        promises = _extract(transcript)
        return {"promises": promises}, 200

    except json.JSONDecodeError:
        logging.exception("Model did not return valid JSON")
        return {"error": "Extraction failed to produce valid JSON."}, 502
    except Exception as exc:  # noqa: BLE001
        logging.exception("promise extraction failed: %s", exc)
        return {"error": "Internal error during extraction."}, 500


if __name__ == "__main__":
    # Local smoke test: python main.py
    sample_transcript = (
        "Agent: I see the $42 discrepancy from the double-billed data "
        "add-on. I'll issue a $42 credit to your account, it should post "
        "within 3 to 5 business days.\n"
        "Customer: Okay, thank you.\n"
        "Agent: I'm also going to flag your account for a callback from "
        "our retention team tomorrow to review your plan options."
    )
    print(json.dumps(_extract(sample_transcript), indent=2))
