# custom-exercise-library

Tool to generate images and metadata for custom exercises in [Hevy](https://www.hevyapp.com/).

You give it an exercise name, for example `"Single-leg bent-knee Smith calf raise"` or `"Drop jump to pogo"`. It writes a folder with everything you need to create the exercise in Hevy:

| Output | What it is |
|---|---|
| `README.md` | The Hevy fields laid out for copy-paste (name, equipment, primary muscle group, other muscles, exercise type), followed by the description, setup, execution, cues, common mistakes, why it matters for running, a suggested prescription and progressions |
| `image.png` | A square illustration of the movement at its key position, with primary muscles in red and secondary muscles in orange |
| `demo.gif` | A looping animation of one rep, built from 2–4 generated keyframes |
| `frames/*.png` | The individual keyframes, so you can replace a bad one and rebuild the GIF |
| `exercise.json` | The structured spec. Edit it and re-run `images` to redraw |

It is built for a runner's strength and conditioning programme, which covers four kinds of work:

1. **Lower-body strength**: heavy compound squat and hinge patterns.
2. **Calf isolation** with a soleus focus: bent-knee, isometric, single-leg, tempo and deficit variants.
3. **Olympic lifts and derivatives** for power.
4. **Plyometrics** for elastic recoil in the Achilles: pogos, drop jumps, hops, bounds.

## How it works

```
exercise name (+ optional notes)
        │
        ▼
Claude (claude-opus-5-5, structured output)  ──►  ExerciseSpec
  • name, category, Hevy type / equipment / muscle group
  • anatomical primary + secondary muscles (e.g. soleus → Hevy "calves")
  • description, setup, execution, cues, mistakes, rationale
  • visual brief: camera view, setting, 2–4 keyframes with poses + timing
        │
        ▼
OpenAI image model (gpt-image-2)
  1. generate the hero keyframe from text      → image.png
  2. edit the hero into each other keyframe    → frames/   (same athlete, camera, style)
        │
        ▼
Pillow: cross-fade + loop (ping-pong or cycle) → demo.gif
        │
        ▼ (optional)
Hevy API POST /v1/exercise_templates
```

Notes on the design:

- **Claude's output is checked against a schema.** The Hevy fields are typed with Hevy's own enum values, so the result always passes Hevy's validation. Claude also lists the anatomical muscles (soleus, gastrocnemius, tibialis posterior) and maps each one to a Hevy group. *Other muscles* is then worked out from those mappings, so Claude doesn't pick it a second time.
- **Every GIF frame is an edit of the hero image.** Image models drift between separate generations (a different athlete, a different camera angle). Editing one reference image keeps the frames consistent.
- **The loop style comes from the movement.** Squats and calf raises play forward and then backward (`ping_pong`). Cleans, depth jumps and bounds play forward and restart (`cycle`).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env   # fill in, then: export $(grep -v '^#' .env | xargs)
```

| Variable | Needed for |
|---|---|
| `ANTHROPIC_API_KEY` | Metadata, always required (or `ant auth login`) |
| `OPENAI_API_KEY` | Image and GIF |
| `HEVY_API_KEY` | Optional upload; needs Hevy Pro (Settings → Developer) |

## Usage

```bash
# One exercise, everything
hevy-exgen generate "Single-leg bent-knee Smith machine calf raise"

# Give Claude extra context about the variant
hevy-exgen generate "Pogo hops" --notes "stiff knees, minimal ground contact, 20 cm amplitude"

# Several at once
hevy-exgen generate "Drop jump" "Hang power clean" "Isometric soleus wall hold"

# Cheap first pass: metadata and hero image only, low quality
hevy-exgen generate "Snatch pull from blocks" --no-gif --quality low

# Metadata only (no OpenAI key needed)
hevy-exgen generate "Seated soleus raise" --metadata-only

# Edit exercises/<slug>/exercise.json (poses, camera, muscles), then redraw
hevy-exgen images exercises/pogo-hops --quality high

# Replace or delete a bad frame in frames/, then rebuild just the GIF (no API calls)
hevy-exgen gif exercises/pogo-hops --tweens 4

# Create it in Hevy via the API
hevy-exgen upload exercises/pogo-hops        # or: generate ... --upload
```

Useful flags: `--effort` (Claude effort, default `medium`), `--model`, `--image-model`, `--quality low|medium|high`, `--style "<custom illustration style>"`, `--gif-size`, `--out`, `--force`.

### Getting it into Hevy

Hevy's public API can only create an exercise with a **title, exercise type, equipment, primary muscle group and other muscles**. It has no field for an image or a description. So you can either:

- **Do it all in the app:** *Exercises → Create Exercise*. Copy the fields from `README.md` and add `image.png` as the exercise image.
- **Use the API for the fields:** run `hevy-exgen upload`, then open the exercise in the app to add `image.png`. Paste the description into the exercise notes in your routine.

The API can't edit or delete custom exercises, so check the metadata before you upload.

Exercise type mapping (API value → in-app label): `weight_reps` → Weight & Reps, `reps_only` → Reps Only, `bodyweight_reps` → Weighted Bodyweight, `bodyweight_assisted_reps` → Assisted Bodyweight, `duration` → Duration, `weight_duration` → Weight & Duration, `distance_duration` → Distance & Duration, `short_distance_weight` → Weight & Distance.

## Cost

Each exercise costs about one Claude request plus 1 image (`--no-gif`) or 2–4 images (with the GIF). `--quality low` is fine for iterating on poses. Switch to `medium` or `high` for the version you keep.

## Development

```bash
pytest
```

The tests use fake API clients, so they make no network calls and need no keys.
