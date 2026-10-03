"""The exercise spec Claude produces, and the Hevy payload derived from it."""

from typing import Literal

from pydantic import BaseModel, Field

from .hevy import EquipmentCategory, ExerciseType, MuscleGroup

Category = Literal[
    "lower_body_strength",
    "calf_isolation",
    "olympic_lift",
    "plyometric",
    "other",
]


class Muscle(BaseModel):
    name: str = Field(description="Anatomical name, e.g. 'soleus', 'gluteus maximus'.")
    hevy_group: MuscleGroup = Field(description="The Hevy muscle group this muscle belongs to.")


class KeyFrame(BaseModel):
    label: str = Field(description="Short phase name, e.g. 'Start', 'Bottom', 'Ground contact', 'Catch'.")
    pose: str = Field(
        description=(
            "Precise, purely visual description of the body position in this phase: joint angles "
            "(ankle, knee, hip, trunk), foot contact, bar/implement position, gaze. Written for an "
            "illustrator, no coaching language."
        )
    )
    hold_ms: int = Field(description="How long the GIF should show this frame, in milliseconds.")


class VisualBrief(BaseModel):
    camera_view: str = Field(
        description="Camera angle that best shows the movement, e.g. 'strict side view from the athlete's right'."
    )
    setting: str = Field(
        description="Equipment and environment to draw, e.g. 'barbell on back, 30 cm box under the forefoot'."
    )
    keyframes: list[KeyFrame] = Field(description="2-4 keyframes in movement order that make up one rep.")
    hero_frame_index: int = Field(
        description="Index into keyframes of the frame that best shows the trained muscles under load."
    )
    loop_style: Literal["ping_pong", "cycle"] = Field(
        description=(
            "'ping_pong' plays the keyframes forward then backward (symmetric up/down movements "
            "like squats or calf raises); 'cycle' plays them forward and restarts (one-directional "
            "movements like cleans, depth jumps or bounds)."
        )
    )


class ExerciseSpec(BaseModel):
    name: str = Field(description="Clear, conventional exercise name as it should appear in Hevy (max ~40 chars).")
    category: Category
    hevy_exercise_type: ExerciseType
    hevy_equipment: EquipmentCategory
    hevy_muscle_group: MuscleGroup = Field(description="The single primary Hevy muscle group.")
    primary_muscles: list[Muscle]
    secondary_muscles: list[Muscle]
    description: str = Field(
        description="2-4 sentence description suitable for pasting into Hevy exercise/routine notes."
    )
    setup: list[str] = Field(description="Setup steps.")
    execution: list[str] = Field(description="Step-by-step execution of one rep.")
    coaching_cues: list[str]
    common_mistakes: list[str]
    runner_rationale: str = Field(description="Why this exercise matters for a distance runner.")
    suggested_prescription: str = Field(description="Typical sets x reps / duration and load guidance.")
    progressions: list[str] = Field(description="Easier and harder variations.")
    visual: VisualBrief

    @property
    def hevy_other_muscles(self) -> list[str]:
        """Secondary Hevy groups, derived from the anatomical muscle lists."""
        seen: list[str] = []
        for m in [*self.primary_muscles, *self.secondary_muscles]:
            if m.hevy_group != self.hevy_muscle_group and m.hevy_group not in seen:
                seen.append(m.hevy_group)
        return seen

    def hevy_payload(self) -> dict:
        """Request body for Hevy's POST /v1/exercise_templates."""
        return {
            "exercise": {
                "title": self.name,
                "exercise_type": self.hevy_exercise_type,
                "equipment_category": self.hevy_equipment,
                "muscle_group": self.hevy_muscle_group,
                "other_muscles": self.hevy_other_muscles,
            }
        }

    def hero_keyframe(self) -> KeyFrame:
        frames = self.visual.keyframes
        return frames[min(max(self.visual.hero_frame_index, 0), len(frames) - 1)]
