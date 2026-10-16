
import boto3


REGION = "eu-central-1"
MODEL_ID = "eu.amazon.nova-micro-v1:0"


def generate_incident_briefing(
    drone_id: str,
    current_fire_id: str,
    current_severity: int | None,
    new_fire_id: str,
    new_severity: int,
    decision: str,
) -> str:
    """Generate a brief explanation of an existing dispatch decision."""

    client = boto3.client(
        "bedrock-runtime",
        region_name=REGION,
    )
    if current_severity is None:
        current_target_fact = (
            f"- Previous route: {current_fire_id}; "
            "the drone was returning to base"
        )
    else:
        current_target_fact = (
            f"- Current target: {current_fire_id}, "
            f"severity {current_severity}"
        )
    prompt = f"""
        You are the briefing component of a simulated fire-response system.

        Facts:
        - Drone: {drone_id}
        - {current_target_fact}
        - New fire: {new_fire_id}, severity {new_severity}
        - Decision from the decision system: {decision}

        Write a briefing of no more than 50 words.
        Explain the decision using only the facts provided.
        Do not invent distances, hazards, people at risk, or other facts.
        Do not make a different dispatch decision.
        This is a simulation, not a real emergency.
        """

    response = client.converse(
        modelId=MODEL_ID,
        messages=[
            {
                "role": "user",
                "content": [{"text": prompt}],
            }
        ],
        inferenceConfig={
            "maxTokens": 100,
            "temperature": 0.2,
        },
    )

    return response["output"]["message"]["content"][0]["text"].strip()
