"""Draw the hero image and GIF keyframes with OpenAI's image API.

Strategy for consistent frames: draw the hero keyframe first from text alone, then
draw every other keyframe as an *edit* of the hero image, so the athlete, camera,
equipment and style stay the same and only the pose changes.
"""

import base64
from pathlib import Path

import openai

from .models import ExerciseSpec, KeyFrame

DEFAULT_IMAGE_MODEL = "gpt-image-2"

# Shorthands people type that aren't real API model IDs. Sunburst is OpenAI's
# higher-quality 2.5 model and is better at keeping a subject consistent across
# edits, which is how the GIF frames are made.
MODEL_ALIASES = {
    "gpt-image-2.5": "gpt-image-2.5-sunburst",
    "sunburst": "gpt-image-2.5-sunburst",
    "flare": "gpt-image-2.5-flare",
}


def resolve_model(name: str) -> str:
    return MODEL_ALIASES.get(name.strip().lower(), name)

DEFAULT_STYLE = (
    "Clean, modern flat-vector fitness illustration in the style of a workout app's exercise "
    "library. One athletic, gender-neutral figure in plain dark-grey training clothes and "
    "running shoes, drawn with anatomically correct proportions. The muscles being trained are "
    "shown as if the clothing were translucent: primary muscles in saturated red, secondary "
    "muscles in soft orange, all other muscles neutral grey. Equipment drawn accurately and to "
    "scale. Plain off-white background with a subtle floor line. Whole body and all equipment "
    "in frame, centred, with margin on all sides. No text, labels, arrows, logos or watermarks."
)


def _muscle_list(spec: ExerciseSpec) -> tuple[str, str]:
    primary = ", ".join(m.name for m in spec.primary_muscles) or "none"
    secondary = ", ".join(m.name for m in spec.secondary_muscles) or "none"
    return primary, secondary


def hero_prompt(spec: ExerciseSpec, style: str = DEFAULT_STYLE) -> str:
    primary, secondary = _muscle_list(spec)
    frame = spec.hero_keyframe()
    return (
        f"{style}\n\n"
        f"Exercise: {spec.name}.\n"
        f"Camera: {spec.visual.camera_view}.\n"
        f"Setting and equipment: {spec.visual.setting}.\n"
        f"Pose ({frame.label}): {frame.pose}\n"
        f"Highlight in red (primary): {primary}.\n"
        f"Highlight in orange (secondary): {secondary}."
    )


def frame_edit_prompt(spec: ExerciseSpec, frame: KeyFrame) -> str:
    return (
        "Redraw this exact illustration with only the athlete's body position changed. Keep the "
        "same athlete, clothing, proportions, muscle highlight colours, equipment, camera angle, "
        "zoom, framing, floor line, background and drawing style. Keep the feet in the same place "
        "on the floor unless the new pose is airborne.\n\n"
        f"Exercise: {spec.name}.\n"
        f"New pose ({frame.label}): {frame.pose}"
    )


class ImageGenerator:
    def __init__(
        self,
        client: openai.OpenAI | None = None,
        *,
        model: str = DEFAULT_IMAGE_MODEL,
        quality: str = "medium",
        size: str = "1024x1024",
        style: str = DEFAULT_STYLE,
    ):
        self.client = client or openai.OpenAI()
        self.model = model
        self.quality = quality
        self.size = size
        self.style = style

    def generate_hero(self, spec: ExerciseSpec) -> bytes:
        result = self.client.images.generate(
            model=self.model,
            prompt=hero_prompt(spec, self.style),
            size=self.size,
            quality=self.quality,
            n=1,
        )
        return _decode(result)

    def generate_frame(self, spec: ExerciseSpec, frame: KeyFrame, reference_png: bytes) -> bytes:
        kwargs = dict(
            model=self.model,
            image=("reference.png", reference_png, "image/png"),
            prompt=frame_edit_prompt(spec, frame),
            size=self.size,
            quality=self.quality,
            n=1,
        )
        try:
            result = self.client.images.edit(**kwargs, input_fidelity="high")
        except openai.BadRequestError as e:
            # Not every image model accepts input_fidelity; retry without it.
            if "input_fidelity" not in str(e):
                raise
            result = self.client.images.edit(**kwargs)
        return _decode(result)

    def generate_all(self, spec: ExerciseSpec, out_dir: Path, log=print) -> tuple[Path, list[Path]]:
        """Write image.png and frames/NN-<label>.png. Returns (hero_path, frame_paths)."""
        frames_dir = out_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        log(f"  drawing hero image ({spec.hero_keyframe().label})...")
        hero = self.generate_hero(spec)
        hero_path = out_dir / "image.png"
        hero_path.write_bytes(hero)

        frame_paths: list[Path] = []
        for i, frame in enumerate(spec.visual.keyframes):
            path = frames_dir / f"{i:02d}-{_slug(frame.label)}.png"
            if frame is spec.hero_keyframe():
                path.write_bytes(hero)
            else:
                log(f"  drawing keyframe {i + 1}/{len(spec.visual.keyframes)} ({frame.label})...")
                path.write_bytes(self.generate_frame(spec, frame, hero))
            frame_paths.append(path)
        return hero_path, frame_paths


def _decode(result) -> bytes:
    data = result.data[0]
    if not getattr(data, "b64_json", None):
        raise RuntimeError("Image API returned no image data.")
    return base64.b64decode(data.b64_json)


def _slug(text: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in text)
    return "-".join(p for p in out.split("-") if p) or "frame"
