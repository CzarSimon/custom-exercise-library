"""Write and read an exercise folder: exercise.json, README.md, image.png, demo.gif, frames/."""

import json
from pathlib import Path

from .hevy import EQUIPMENT_LABELS, EXERCISE_TYPE_LABELS, muscle_label
from .models import ExerciseSpec

SPEC_FILE = "exercise.json"


def slugify(text: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in text)
    return "-".join(p for p in out.split("-") if p) or "exercise"


def save_spec(spec: ExerciseSpec, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / SPEC_FILE
    path.write_text(json.dumps(spec.model_dump(), indent=2, ensure_ascii=False) + "\n")
    return path


def load_spec(out_dir: Path) -> ExerciseSpec:
    return ExerciseSpec.model_validate_json((out_dir / SPEC_FILE).read_text())


def write_readme(spec: ExerciseSpec, out_dir: Path) -> Path:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {i}" for i in items) or "- (none)"

    def steps(items: list[str]) -> str:
        return "\n".join(f"{n}. {i}" for n, i in enumerate(items, 1))

    other = ", ".join(muscle_label(m) for m in spec.hevy_other_muscles) or "(none)"
    primary = ", ".join(m.name for m in spec.primary_muscles) or "(none)"
    secondary = ", ".join(m.name for m in spec.secondary_muscles) or "(none)"
    images = ""
    if (out_dir / "image.png").exists():
        images += "![Exercise image](image.png)\n"
    if (out_dir / "demo.gif").exists():
        images += "![Demo](demo.gif)\n"

    md = f"""# {spec.name}

{images}
## Hevy fields (copy into "Create Exercise")

| Field | Value |
|---|---|
| Name | {spec.name} |
| Equipment | {EQUIPMENT_LABELS[spec.hevy_equipment]} |
| Primary muscle group | {muscle_label(spec.hevy_muscle_group)} |
| Other muscles | {other} |
| Exercise type | {EXERCISE_TYPE_LABELS[spec.hevy_exercise_type]} (`{spec.hevy_exercise_type}`) |
| Image | `image.png` |

**Description / notes:** {spec.description}

## Muscles

- **Primary:** {primary}
- **Secondary:** {secondary}

## Setup

{steps(spec.setup)}

## Execution

{steps(spec.execution)}

## Coaching cues

{bullets(spec.coaching_cues)}

## Common mistakes

{bullets(spec.common_mistakes)}

## Why it matters for running

{spec.runner_rationale}

**Suggested prescription:** {spec.suggested_prescription}

## Progressions

{bullets(spec.progressions)}
"""
    path = out_dir / "README.md"
    path.write_text(md)
    return path
