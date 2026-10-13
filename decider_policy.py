
import json
from urllib.request import Request, urlopen


DECIDER_URL = "http://127.0.0.1:8099/v1/systemone"
FALLBACK_POLICY = "severity_first"
MIN_CONFIDENCE = 0.20


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
