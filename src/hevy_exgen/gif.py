"""Assemble keyframe PNGs into a looping demo GIF."""

from pathlib import Path

from PIL import Image


def build_gif(
    frame_paths: list[Path],
    hold_ms: list[int],
    out_path: Path,
    *,
    size: int = 512,
    tweens: int = 3,
    tween_ms: int = 60,
    ping_pong: bool = True,
) -> Path:
    """Write an animated GIF that cycles through the keyframes.

    tweens: number of cross-fade frames inserted between consecutive keyframes, to soften
    the jump between poses. ping_pong: play 0..n then back n-1..1 (a full rep for
    up/down movements) instead of jumping from the last frame to the first.
    """
    if not frame_paths:
        raise ValueError("No frames to assemble.")
    if len(frame_paths) != len(hold_ms):
        raise ValueError("frame_paths and hold_ms must have the same length.")

    keys = [_load(p, size) for p in frame_paths]
    order = list(range(len(keys)))
    if ping_pong and len(keys) > 2:
        order += list(range(len(keys) - 2, 0, -1))

    frames: list[Image.Image] = []
    durations: list[int] = []
    for pos, idx in enumerate(order):
        frames.append(keys[idx])
        durations.append(max(hold_ms[idx], 20))
        nxt = order[(pos + 1) % len(order)]
        if len(keys) > 1:
            for t in range(1, tweens + 1):
                frames.append(Image.blend(keys[idx], keys[nxt], t / (tweens + 1)))
                durations.append(tween_ms)

    palette_frames = [f.convert("P", palette=Image.Palette.ADAPTIVE, colors=255) for f in frames]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    palette_frames[0].save(
        out_path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    return out_path


def _load(path: Path, size: int) -> Image.Image:
    img = Image.open(path).convert("RGB")
    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), (250, 250, 248))
    canvas.paste(img, ((size - img.width) // 2, (size - img.height) // 2))
    return canvas
