import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from hevy_exgen import cli, images, metadata, output
from hevy_exgen.gif import build_gif
from hevy_exgen.models import ExerciseSpec

SPEC = {
    "name": "Smith Machine Bent-Knee Calf Raise",
    "category": "calf_isolation",
    "hevy_exercise_type": "weight_reps",
    "hevy_equipment": "machine",
    "hevy_muscle_group": "calves",
    "primary_muscles": [{"name": "soleus", "hevy_group": "calves"}],
    "secondary_muscles": [
        {"name": "gastrocnemius", "hevy_group": "calves"},
        {"name": "quadriceps (isometric)", "hevy_group": "quadriceps"},
    ],
    "description": "Bent-knee calf raise that biases the soleus.",
    "setup": ["Set bar on traps", "Forefoot on a plate"],
    "execution": ["Lower heels", "Drive up"],
    "coaching_cues": ["Keep knees bent ~45 degrees"],
    "common_mistakes": ["Bouncing"],
    "runner_rationale": "The soleus absorbs the largest forces in running.",
    "suggested_prescription": "3x8-12, heavy",
    "progressions": ["Single-leg"],
    "visual": {
        "camera_view": "side view",
        "setting": "Smith machine, plate under forefoot",
        "keyframes": [
            {"label": "Bottom", "pose": "heels low, knees 45 deg", "hold_ms": 500},
            {"label": "Top", "pose": "full plantarflexion, knees 45 deg", "hold_ms": 600},
        ],
        "hero_frame_index": 1,
        "loop_style": "ping_pong",
    },
}


def png_bytes(color) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="PNG")
    return buf.getvalue()


def image_response(color):
    return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(png_bytes(color)).decode())])


class FakeImages:
    def __init__(self):
        self.calls = []

    def generate(self, **kw):
        self.calls.append(("generate", kw))
        return image_response("red")

    def edit(self, **kw):
        self.calls.append(("edit", kw))
        return image_response("blue")


def test_hevy_payload_derives_other_muscles():
    spec = ExerciseSpec.model_validate(SPEC)
    assert spec.hevy_payload() == {
        "exercise": {
            "title": "Smith Machine Bent-Knee Calf Raise",
            "exercise_type": "weight_reps",
            "equipment_category": "machine",
            "muscle_group": "calves",
            "other_muscles": ["quadriceps"],
        }
    }


def test_invalid_hevy_enum_rejected():
    bad = {**SPEC, "hevy_muscle_group": "soleus"}
    with pytest.raises(ValueError):
        ExerciseSpec.model_validate(bad)


def test_generate_spec_uses_structured_output_and_handles_refusal():
    spec = ExerciseSpec.model_validate(SPEC)
    captured = {}

    def parse(**kw):
        captured.update(kw)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=spec)

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(parse=parse)))
    assert metadata.generate_spec("calf raise", "smith, bent knee", client=client) is spec
    assert captured["output_format"] is ExerciseSpec
    assert captured["model"] == "claude-opus-5-5"
    assert "smith, bent knee" in captured["messages"][0]["content"]

    client.beta.messages.parse = lambda **kw: SimpleNamespace(stop_reason="refusal", parsed_output=None)
    with pytest.raises(metadata.GenerationRefused):
        metadata.generate_spec("x", client=client)


def test_image_generator_draws_hero_then_edits_other_frames(tmp_path):
    spec = ExerciseSpec.model_validate(SPEC)
    fake = FakeImages()
    gen = images.ImageGenerator(client=SimpleNamespace(images=fake))
    hero, frames = gen.generate_all(spec, tmp_path, log=lambda *_: None)

    assert [c[0] for c in fake.calls] == ["generate", "edit"]
    assert "Top" in fake.calls[0][1]["prompt"]  # hero is keyframe index 1
    assert "soleus" in fake.calls[0][1]["prompt"]
    assert "Bottom" in fake.calls[1][1]["prompt"]
    assert hero.read_bytes() == frames[1].read_bytes()
    assert [f.name for f in frames] == ["00-bottom.png", "01-top.png"]


def test_build_gif_ping_pong(tmp_path):
    paths = []
    for i, color in enumerate(["red", "green", "blue"]):
        p = tmp_path / f"{i}.png"
        p.write_bytes(png_bytes(color))
        paths.append(p)
    out = build_gif(paths, [300, 300, 300], tmp_path / "demo.gif", size=64, tweens=2)
    gif = Image.open(out)
    # ping-pong order 0,1,2,1 -> 4 keyframes, each followed by 2 tweens
    assert gif.n_frames == 12
    assert gif.info["loop"] == 0


def test_cli_generate_end_to_end(tmp_path, monkeypatch):
    spec = ExerciseSpec.model_validate(SPEC)
    monkeypatch.setattr(cli.metadata, "generate_spec", lambda *a, **k: spec)
    fake = FakeImages()
    monkeypatch.setattr(cli.images.openai, "OpenAI", lambda: SimpleNamespace(images=fake))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    monkeypatch.setenv("OPENAI_API_KEY", "test")

    rc = cli.main(["generate", "calf raise", "--out", str(tmp_path), "--gif-size", "64"])
    assert rc == 0
    out_dir = tmp_path / "calf-raise"
    for name in ["exercise.json", "README.md", "image.png", "demo.gif", "frames/00-bottom.png"]:
        assert (out_dir / name).exists(), name
    assert json.loads((out_dir / "exercise.json").read_text())["name"] == spec.name
    readme = (out_dir / "README.md").read_text()
    assert "| Primary muscle group | Calves |" in readme
    assert "![Demo](demo.gif)" in readme

    # Re-running without --force refuses to overwrite.
    assert cli.main(["generate", "calf raise", "--out", str(tmp_path)]) == 1
    # Rebuilding the GIF from existing frames works offline.
    assert cli.main(["gif", str(out_dir), "--gif-size", "64"]) == 0


def test_slugify():
    assert output.slugify("Pogo Hops (Single-Leg)") == "pogo-hops-single-leg"


def test_dotenv_loading_and_key_check(tmp_path, monkeypatch):
    from hevy_exgen import env

    monkeypatch.setenv("HOME", str(tmp_path))  # no `ant` profile
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # empty in shell: .env should win
    monkeypatch.setenv("OPENAI_API_KEY", "from-shell")  # non-empty in shell: shell wins
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text('# keys\nexport ANTHROPIC_API_KEY="sk-ant-test"\nOPENAI_API_KEY=from-file\nHEVY_API_KEY=\n')

    nested = tmp_path / "sub" / "dir"
    nested.mkdir(parents=True)
    assert env.find_dotenv(nested) == dotenv
    assert env.load_dotenv(dotenv) == dotenv
    import os

    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-test"
    assert os.environ["OPENAI_API_KEY"] == "from-shell"
    assert env.missing_keys(need_openai=True) == []

    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert env.missing_keys(need_openai=True) == ["OPENAI_API_KEY"]


def test_cli_fails_fast_without_keys(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    for k in ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(cli.env, "find_dotenv", lambda start=None: None)
    called = []
    monkeypatch.setattr(cli.metadata, "generate_spec", lambda *a, **k: called.append(1))

    assert cli.main(["generate", "Pogo jumps"]) == 2
    assert not called
    assert "Missing ANTHROPIC_API_KEY, OPENAI_API_KEY" in capsys.readouterr().err


def test_image_model_aliases():
    assert images.resolve_model("gpt-image-2.5") == "gpt-image-2.5-sunburst"
    assert images.resolve_model("gpt-image-2") == "gpt-image-2"
