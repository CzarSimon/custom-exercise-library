"""Hevy's exercise taxonomy, as accepted by POST /v1/exercise_templates.

Values mirror the enums in Hevy's public OpenAPI spec. The in-app labels are
what you see in the "Create Exercise" screen of the Hevy app.
"""

from typing import Literal

MuscleGroup = Literal[
    "abdominals",
    "shoulders",
    "biceps",
    "triceps",
    "forearms",
    "quadriceps",
    "hamstrings",
    "calves",
    "glutes",
    "abductors",
    "adductors",
    "lats",
    "upper_back",
    "traps",
    "lower_back",
    "chest",
    "cardio",
    "neck",
    "full_body",
    "other",
]

ExerciseType = Literal[
    "weight_reps",
    "reps_only",
    "bodyweight_reps",
    "bodyweight_assisted_reps",
    "duration",
    "weight_duration",
    "distance_duration",
    "short_distance_weight",
]

EquipmentCategory = Literal[
    "none",
    "barbell",
    "dumbbell",
    "kettlebell",
    "machine",
    "plate",
    "resistance_band",
    "suspension",
    "other",
]

EXERCISE_TYPE_LABELS: dict[str, str] = {
    "weight_reps": "Weight & Reps",
    "reps_only": "Reps Only",
    "bodyweight_reps": "Weighted Bodyweight",
    "bodyweight_assisted_reps": "Assisted Bodyweight",
    "duration": "Duration",
    "weight_duration": "Weight & Duration",
    "distance_duration": "Distance & Duration",
    "short_distance_weight": "Weight & Distance",
}

EQUIPMENT_LABELS: dict[str, str] = {
    "none": "None",
    "barbell": "Barbell",
    "dumbbell": "Dumbbell",
    "kettlebell": "Kettlebell",
    "machine": "Machine",
    "plate": "Plate",
    "resistance_band": "Resistance Band",
    "suspension": "Suspension Band",
    "other": "Other",
}


def muscle_label(group: str) -> str:
    return group.replace("_", " ").title()
