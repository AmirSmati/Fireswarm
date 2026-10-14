# Firewatch Swarm

**A human-in-the-loop fire-response simulation exploring policy decisions with Strands Decider 2B.**

Firewatch Swarm is a small 2D simulation in which a user creates fires on a grid and a fleet of simulated drones responds. A conventional coordinator manages assignments and resource constraints, while **Strands Decider 2B** can select a dispatch policy and reconsider a drone's existing assignment when a more severe fire appears.

> **Status:** The local simulation, dispatch-policy selection, and en-route rerouting have been implemented and tested. The Amazon Bedrock briefing module exists, but it is not yet connected to the live simulation flow. Bedrock inference is currently blocked by an AWS account-verification/access issue in the development environment, so end-to-end Bedrock integration remains unfinished.

This is an experimental simulation for software research and demonstrations. It is **not** a real-world firefighting, emergency-response, or autonomous-flight system.

## What it does

- Displays a grid, base, drones, active fires, and simulation status using Pygame.
- Lets the user create fires by clicking an empty grid cell and selecting severity `1`–`5`.
- Simulates fire spread, drone movement, suppression, and incident events.
- Assigns eligible idle drones to active fires, preferring the nearest eligible drone and avoiding duplicate assignments.
- Uses Decider 2B to choose between dispatch policies when multiple fires are waiting for a drone.
- Can ask Decider 2B whether an **en-route** drone should keep its current target or be rerouted to a newly created, more severe fire.
- Includes regression tests for rerouting decisions and coordinator constraints.
- Contains a separate Amazon Bedrock/Nova Micro briefing module, intended to generate a factual explanation of a dispatch decision once Bedrock access is available and the module is wired into the application.

## How the decision loop works

```text
User clicks an empty grid cell
            |
            v
Create incident + record incident_detected event
            |
            +---- If a more severe fire appears ------------------+
            |                                                     |
            v                                                     v
Select policy for pending fires                       Reconsider an en-route drone
(severity_first / oldest_first)                       (keep_current / reroute_to_<fire>)
            |                                                     |
            v                                                     v
Coordinator checks eligibility and assignments         Coordinator applies the choice
            |                                                     |
            +--------------------------+--------------------------+
                                       v
                          Simulation advances one tick
                   (movement, spread, suppression, events)
```

### Responsibility split

- **Strands Decider 2B — structured decisions:** returns a typed choice with confidence. It is not the text-generation component.
- **Coordinator — operational constraints:** manages drone availability, target assignment, minimum resource thresholds, and whether a proposed reroute is applicable.
- **Simulation — world mechanics:** advances drones, fires, and incident state.
- **Amazon Bedrock — planned generative component:** `bedrock_briefing.py` calls Amazon Nova Micro to generate a short incident briefing from supplied facts. It must not override the structured decision or invent facts.

## Reusable Decider 2B pattern: `#policy`

The primary pattern demonstrated is **policy selection**: select a dispatch policy from the current world state, then let deterministic coordinator code apply that policy while enforcing constraints.

### Pattern A: dispatch-policy choice

- **State:** Unassigned active fires, their severities and creation ticks, plus eligible available drones.
- **Typed question:** `choice`
- **Options:**
  - `severity_first` — rank by severity descending, then age.
  - `oldest_first` — rank by age first, then severity descending.
- **Wiring:** `choose_dispatch_policy()` in `decider_policy.py` is called by the application when there are multiple pending fires and an available drone. The chosen policy is passed to `assign_available_drones()` in `allocation.py`.
- **Fallback:** Low-confidence choices fall back to `severity_first`; request failures leave the simulation able to continue with the fallback policy.

### Pattern B: reconsider an existing assignment

- **State:** An en-route drone's position and resources, its current fire target, and the new fire's position and severity.
- **Typed question:** `choice`
- **Options:** `keep_current` or `reroute_to_<incident_id>` for the new fire.
- **Wiring:** `reconsider_assignments()` in `main.py` calls `choose_reroute_decision()` in `decider_policy.py`. If the result recommends a reroute, the coordinator updates `target_incident_id`; the movement system then heads toward that target.
- **Guardrails:** The current implementation considers drones with `EN_ROUTE` status only, requires the new fire to be strictly more severe than the current target, and checks minimum battery/water levels before asking Decider. Uncertain or failed decisions leave the current assignment unchanged.

These two functions are useful starting points for adapting the choice-state-options-wiring pattern to another agent. The rerouting behavior is experimental; it is not intended as a validated emergency-response policy.

## Project structure

```text
firewatch-swarm/
├── allocation.py          # Eligibility, ranking, and drone assignment
├── bedrock_briefing.py    # Amazon Bedrock incident-briefing prototype
├── decider_policy.py      # Decider 2B calls for dispatch/rerouting choices
├── events.py              # Incident creation, escalation, and extinguishing events
├── fire_dynamics.py       # Fire spread mechanics
├── main.py                # Application loop and user-created fire handling
├── models.py              # World, drone, incident, and event dataclasses
├── movement.py             # Drone movement and suppression lifecycle
├── renderer.py            # Pygame interface and mouse/keyboard input
├── simulation.py          # Initial-world construction
├── tests/                 # Automated tests
├── requirements.txt
├── Dockerfile
├── .dockerignore
└── .gitignore
```

## Requirements

- Python 3.12 (the project has been exercised with Python 3.12.3).
- Pygame with a working graphical display.
- The Strands Decider package and its model checkpoint, served locally over HTTP.
- `pytest` to run the tests.
- For the optional Bedrock briefing: AWS SDK for Python (`boto3`), `awscrt` where required by the chosen AWS credential flow, valid AWS credentials, and permission/access to invoke the selected Bedrock model.

A CUDA-capable NVIDIA GPU is useful for local Decider inference but is not a requirement of the simulation code itself; CPU inference may be slower.

## Setup

### 1. Create the Python environment

From the repository directory:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 2. Start the Decider server

Install and configure Strands Decider by following the [official Strands Decider repository and inference guide](https://github.com/strands-labs/strands-decider/blob/main/docs/inference.md). The following example assumes the Decider repository has been cloned separately and its `.venv` is ready.

In a dedicated terminal:

```bash
cd /path/to/strands-decider
source .venv/bin/activate
strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --device cuda --port 8099
```

Keep this terminal open while running Firewatch Swarm. The application expects the local endpoint:

```text
http://127.0.0.1:8099/v1/systemone
```

If you do not have a CUDA-compatible setup, consult the upstream inference guide for a supported device option and installation extra.

### 3. Launch Firewatch Swarm

In a second terminal, from this repository:

```bash
source .venv/bin/activate
python main.py
```

### 4. Use the interface

- Press `1`, `2`, `3`, `4`, or `5` to select the severity of the next fire.
- Left-click an empty grid cell to create the fire.
- Watch the console for `[Decider]` and `[Dispatcher]` messages showing policy and rerouting decisions.
- Press `Q` or `Esc` to close the window.

**Development note:** During rerouting tests, `main.py` may be configured to start with one drone and no initial incidents. In that test setup, create fires manually after launching the application. Restore the normal initial-world setup in `main()` if you want to demonstrate the default scenario instead.

## Run the tests

With the project virtual environment active:

```bash
pytest -q
```

The suite includes coverage for model/state mechanics, allocation/movement behavior, and rerouting cases such as accepting a reroute, keeping the current target, equal-severity fires, and insufficient resources.

## Amazon Bedrock briefing (in progress)

`bedrock_briefing.py` contains a standalone Amazon Bedrock Converse call configured for the EU Nova Micro inference profile `eu.amazon.nova-micro-v1:0` in `eu-central-1` (Frankfurt). It is designed to generate a concise, evidence-bound explanation of a decision already made by Decider and applied by the coordinator.

The development AWS account has returned account-verification / `Operation not allowed` errors on subsequent inference attempts. Consequently:

1. The briefing module has **not** been verified reliably end-to-end in the current environment.
2. It is **not yet wired into the application's rerouting path**.
3. A working AWS identity alone does not guarantee that Bedrock model invocation is enabled for an account.

Before enabling it, verify account/model access and permissions, test the module independently, then integrate it with graceful error handling. Bedrock usage may incur AWS charges. Do not commit AWS credentials, tokens, or local credential files.

## Current limitations and next steps

- Rerouting currently applies to drones that are still `EN_ROUTE`; it does not interrupt a drone already in `SUPPRESSING`.
- Rerouting is triggered by a newly created fire in the current manual-incident flow; escalation-triggered reconsideration is a future improvement.
- The current policy options are intentionally small and experimental. More realistic behavior requires evaluation rather than assuming Decider always improves outcomes.
- Finish the end-to-end Bedrock briefing integration and handle unavailable cloud access gracefully.
- Compare the baseline allocator with the Decider-enabled policy using repeatable scenarios and measured outcomes, such as response time, extinguished incidents, reassignment count, and inference latency.
- Before a public hackathon submission, add an OSI-approved `LICENSE`, clearly package the reusable decision pattern, and prepare the Builder Center article and a public demo video under three minutes.

## Hackathon context

This project is being developed for the [AWS Builder Center Agent Experience Hackathon: Strands Decider](https://builder.aws.com/build/hackathons/4f50957c-1d08-37ab-b11c-97516b9adeb4/agent-experience-hackathon). The current intended decision-pattern tag is `#policy`, alongside the required `#strands-decider-2b` tag. Check the official page for the latest requirements and submission dates.

## License

No project license has been selected in this draft. Add an approved open-source license before making the repository public or submitting it to the hackathon. Until a license is added, others should not assume they have permission to reuse the project source.
