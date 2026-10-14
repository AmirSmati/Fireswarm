
from decider_policy import classify_response_policy

scenarios = {
    "ROUTINE DISPATCH": """
        Event: incident_detected.
        A new severity-2 fire has appeared and is unassigned.
        One idle drone has 90% battery and 90% water.
        All existing drone assignments can remain unchanged.
        Classify the response policy.
    """,
    "CRITICAL REROUTE": """
        Event: incident_detected.
        A new severity-5 fire has appeared and is unassigned.
        Drone-1 is travelling to a severity-1 fire.
        Drone-1 has 90% battery and 90% water.
        No idle drones are available.
        Classify the response policy.
    """,
    "MAINTAIN ASSIGNMENTS": """
        Event: routine_status_update.
        No new fires or escalations have occurred.
        All assigned drones are progressing normally.
        Their battery and water levels are sufficient.
        No new assignment or interruption is required.
        Classify the response policy.
    """,
    "RESOURCE RECOVERY": """
        Event: resource_threshold_crossed.
        Drone-1 has only 5% water remaining and 40% battery.
        It cannot continue its current mission effectively.
        No new critical fire needs its immediate attention.
        Prioritize returning to base to replenish resources.
        Classify the response policy.
    """,
}

for name, state in scenarios.items():
    print(f"\n--- {name} ---", flush=True)

    try:
        category, confidence = classify_response_policy(state)
        print(f"Result: {category} ({confidence:.3f})", flush=True)
    except Exception as exc:
        print(f"ERROR: {exc}", flush=True)
