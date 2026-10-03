"""Generate an ExerciseSpec from an exercise name with Claude."""

import anthropic

from .models import ExerciseSpec

DEFAULT_MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """\
You are a strength & conditioning coach who specialises in distance runners. You write \
exercise entries for the Hevy workout-logging app, for exercises its built-in library is \
missing.

The athlete's S&C falls into four categories:
1. lower_body_strength: heavy compound lifts (squat, hinge, lunge, step-up patterns).
2. calf_isolation: calf strength work with particular emphasis on the soleus (bent-knee \
raises, isometrics, seated/Smith/leg-press variants, single-leg, tempo and deficit variants).
3. olympic_lift: Olympic lifts and their derivatives for power (cleans, snatches, pulls, \
jerks, hang/block/power variants, jump shrugs).
4. plyometric: jumps, hops, bounds and pogos that train elastic recoil in tendons, especially \
the Achilles (pogo hops, drop jumps, depth jumps, ankle hops, single-leg hops, bounding, \
skipping drills). Use "other" only if none fit.

Interpret the exercise name the way a runner's S&C coach would. If the name is ambiguous, \
choose the most common variant and make the name specific (e.g. "Calf raise" on a Smith \
machine with bent knees becomes "Smith Machine Bent-Knee Calf Raise").

Hevy rules:
- hevy_muscle_group is the single primary group. Soleus and gastrocnemius map to "calves"; \
Achilles-focused plyometrics map to "calves" unless the movement is clearly hip- or \
quad-dominant. Olympic lifts usually map to "full_body" or "quadriceps"/"glutes"; pick what \
the athlete would filter by.
- Every muscle's hevy_group must be one of Hevy's groups. List only meaningfully loaded \
muscles; 1-3 primary, 0-6 secondary.
- hevy_exercise_type: "weight_reps" for loaded lifts (barbell, dumbbell, machine, plate); \
"reps_only" for plain bodyweight reps (most plyometrics); "bodyweight_reps" for bodyweight \
movements that are sometimes loaded with extra weight (logged as added kg, e.g. weighted \
pogos with a vest); "bodyweight_assisted_reps" for assisted bodyweight work; "duration" or \
"weight_duration" for isometric holds; "distance_duration" or "short_distance_weight" for \
bounding/sled-style drills measured by distance.
- hevy_equipment: the main implement ("none" for unloaded plyometrics, "plate" for \
plate-loaded machines like a leg press only if Hevy users would call it that, otherwise \
"machine").

Visual brief: it drives an image model that draws the hero image and the keyframes of an \
animated GIF of one rep. Pick the camera view that makes the key joint actions obvious \
(side view for most lower-body work). Use 2 keyframes for simple up/down movements, 3-4 for \
multi-phase movements (Olympic lifts, depth jumps). Pose descriptions must be concrete and \
visual (joint angles, contact points, implement position). For fast plyometrics give short \
hold_ms (120-250); for strength work 400-700; for isometric holds 1000-1500. Set loop_style to "cycle" when \
playing the frames in reverse would look wrong.

Write the description, cues and steps in plain, concise English for an experienced lifter.\
"""


class GenerationRefused(RuntimeError):
    pass


def generate_spec(
    exercise_name: str,
    notes: str | None = None,
    *,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    effort: str = "medium",
) -> ExerciseSpec:
    client = client or anthropic.Anthropic()

    user = f"Exercise: {exercise_name}"
    if notes:
        user += f"\n\nAthlete's notes on this exercise:\n{notes}"

    response = client.beta.messages.parse(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort},
        output_format=ExerciseSpec,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )

    if response.stop_reason == "refusal":
        raise GenerationRefused(f"Claude declined to generate metadata for {exercise_name!r}.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude's response was truncated (max_tokens); try again.")

    spec = response.parsed_output
    if spec is None:
        raise RuntimeError("Claude returned no structured output.")
    if not spec.visual.keyframes:
        raise RuntimeError("Claude returned a visual brief without keyframes.")
    return spec
