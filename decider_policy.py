
import json
from urllib.request import Request, urlopen


DECIDER_URL = "http://127.0.0.1:8099/v1/systemone"
FALLBACK_POLICY = "severity_first"
MIN_CONFIDENCE = 0.20


RESPONSE_CATEGORIES = {
    "routine_dispatch",
    "critical_reroute",
    "maintain_assignments",
    "resource_recovery",
}


def choose_dispatch_policy(state: str) -> tuple[str, float]:
    payload = {
        "state": state,
        "questions": {
            "dispatch_policy": {
                "type": "choice",
                "instructions": (
                    "Choose the dispatch policy that best fits "
                    "the current simulated fire-response situation."
                ),
                "criteria": {
                    "severity_first": (
                        "Prioritize the highest-severity active fire. "
                        "Break ties by oldest creation time. Prefer this "
                        "when a more dangerous fire needs urgent attention."
                    ),
                    "oldest_first": (
                        "Prioritize the oldest active fire, even if a "
                        "newer fire is more severe. Prefer this when "
                        "fires have similar severity and waiting time matters."
                    ),
                },
            }
        },
    }

    request = Request(
        DECIDER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    # Fail visibly during this initial integration test.
    with urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))

    answer = result["answers"]["dispatch_policy"]
    model_choice = answer["choice"]
    confidence = float(answer["confidence"])

    if model_choice not in {"severity_first", "oldest_first"}:
        raise ValueError(f"Unexpected Decider choice: {model_choice!r}")

    if confidence < MIN_CONFIDENCE:
        selected_policy = FALLBACK_POLICY
        print(
            f"[Decider] Low confidence ({confidence:.3f}); "
            f"using fallback: {selected_policy}"
        )
    else:
        selected_policy = model_choice

    print(
        f"[Decider] Model chose {model_choice}; "
        f"confidence={confidence:.3f}; "
        f"policy applied={selected_policy}"
    )

    return selected_policy, confidence

# Rerouting 
def choose_reroute_decision(
    state: str,
    incident_id: str,
) -> tuple[str, float]:
    reroute_option = f"reroute_to_{incident_id}"

    payload = {
        "state": state,
        "questions": {
            "reroute_decision": {
                "type": "choice",
                "instructions": (
                    "Decide whether an en-route drone should keep "
                    "its current target or reroute to a new fire. "
                    "Consider the severity difference, drone resources, "
                    "and both fire locations."
                ),
                "criteria": {
                    "keep_current": (
                        "Keep the current target if changing course "
                        "is not sufficiently justified."
                    ),
                    reroute_option: (
                        "Reroute to the new fire because its higher "
                        "severity justifies reconsidering the assignment."
                    ),
                },
            }
        },
    }

    request = Request(
        DECIDER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))

    answer = result["answers"]["reroute_decision"]
    choice = answer["choice"]
    confidence = float(answer["confidence"])

    if choice not in {"keep_current", reroute_option}:
        raise ValueError(f"Unexpected rerouting choice: {choice!r}")

    if confidence < MIN_CONFIDENCE:
        choice = "keep_current"

    print(
        f"[Decider] Rerouting decision={choice}; "
        f"confidence={confidence:.3f}"
    )

    return choice, confidence

def classify_response_policy(state: str) -> tuple[str, float]:
    """Classify an incident event before the coordinator acts."""

    payload = {
        "state": state,
        "questions": {
            "response_category": {
                "type": "choice",
                "instructions": (
                    "Classify the incoming fire-response situation "
                    "into exactly one response category. Use the "
                    "incident, drone assignments, and resource facts. "
                    "Do not invent information. The coordinator will "
                    "validate and execute the chosen response."
                ),   
                "criteria": {
                    "routine_dispatch": (
                        "Choose ONLY when an active fire needs an initial assignment "
                        "and no currently assigned drone needs to be interrupted. "
                        "This is for routine fires when existing assignments can remain "
                        "unchanged."
                    ),
                    "critical_reroute": (
                        "Choose when a new or escalated fire has severity 4 or 5, "
                        "at least one drone is travelling to a lower-severity fire, "
                        "and no idle drone is available to handle the critical fire. "
                        "Reconsider redirecting an en-route drone."
                    ),
                    "maintain_assignments": (
                        "Choose when no new meaningful incident requires action, "
                        "no critical incident requires reconsideration, and current "
                        "assignments should remain unchanged."
                    ),
                    "resource_recovery": (
                        "Choose when a drone has insufficient battery or water to "
                        "continue its current mission and should return to base."
                    ),
                },
            }
        },
    }

    request = Request(
        DECIDER_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))

    answer = result["answers"]["response_category"]
    category = answer["choice"]
    confidence = float(answer["confidence"])

    if category not in RESPONSE_CATEGORIES:
        raise ValueError(f"Unexpected response category: {category!r}")

    print(
        f"[Decider] Response category={category}; "
        f"confidence={confidence:.3f}"
    )

    return category, confidence
