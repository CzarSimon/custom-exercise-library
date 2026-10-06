"""hevy-exgen: generate custom Hevy exercises (metadata, image, demo GIF) from a name."""

import argparse
import sys
from pathlib import Path

from . import env, gif, hevy_api, images, metadata, output

DEFAULT_OUT = Path("exercises")


def _add_image_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--image-model", default=images.DEFAULT_IMAGE_MODEL, help="OpenAI image model (default: %(default)s)")
    p.add_argument(
        "--quality",
        default="medium",
        choices=["low", "medium", "high"],
        help="Image quality; higher costs more (default: %(default)s)",
    )
    p.add_argument("--style", default=None, help="Override the illustration style prompt")
    p.add_argument("--no-gif", action="store_true", help="Only draw the hero image, skip the GIF keyframes")


def _add_gif_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--gif-size", type=int, default=512, help="GIF width/height in px (default: %(default)s)")
    p.add_argument("--tweens", type=int, default=3, help="Cross-fade frames between poses (default: %(default)s)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hevy-exgen", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="Generate metadata, image and GIF for one or more exercise names")
    g.add_argument("names", nargs="+", help='Exercise name(s), e.g. "Bent-knee single-leg Smith calf raise"')
    g.add_argument("--notes", help="Extra context for Claude (setup, variant, what you want emphasised)")
    g.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output root (default: %(default)s)")
    g.add_argument("--model", default=metadata.DEFAULT_MODEL, help="Claude model (default: %(default)s)")
    g.add_argument(
        "--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"], help="Claude effort level"
    )
    g.add_argument("--metadata-only", action="store_true", help="Skip all image generation")
    g.add_argument("--upload", action="store_true", help="Also create the exercise in Hevy via the API")
    g.add_argument("--force", action="store_true", help="Overwrite an existing exercise folder")
    _add_image_args(g)
    _add_gif_args(g)

    i = sub.add_parser("images", help="(Re)draw the image and GIF from an exercise folder's exercise.json")
    i.add_argument("dir", type=Path)
    _add_image_args(i)
    _add_gif_args(i)

    a = sub.add_parser("gif", help="Rebuild demo.gif from the PNGs in an exercise folder's frames/")
    a.add_argument("dir", type=Path)
    _add_gif_args(a)

    u = sub.add_parser("upload", help="Create the exercise in Hevy from an exercise folder")
    u.add_argument("dir", type=Path)

    s = sub.add_parser("serve", help="Open a local web UI to browse exercises and copy fields into Hevy")
    s.add_argument("--dir", type=Path, default=DEFAULT_OUT, help="Exercises folder (default: %(default)s)")
    s.add_argument("--port", type=int, default=8765, help="Port (default: %(default)s)")
    s.add_argument("--lan", action="store_true", help="Also reachable from your phone on the same Wi-Fi")
    s.add_argument("--no-browser", action="store_true", help="Don't open a browser window")

    return parser


def _image_generator(args) -> images.ImageGenerator:
    model = images.resolve_model(args.image_model)
    if model != args.image_model:
        print(f"  using image model {model} for {args.image_model!r}")
    return images.ImageGenerator(
        model=model,
        quality=args.quality,
        style=args.style or images.DEFAULT_STYLE,
    )


def _draw(spec, out_dir: Path, args) -> None:
    gen = _image_generator(args)
    if args.no_gif:
        print("  drawing hero image...")
        (out_dir / "image.png").write_bytes(gen.generate_hero(spec))
        return
    _, frames = gen.generate_all(spec, out_dir, log=print)
    _assemble(spec, out_dir, frames, args)


def _assemble(spec, out_dir: Path, frames: list[Path], args) -> None:
    holds = [f.hold_ms for f in spec.visual.keyframes]
    if len(holds) != len(frames):
        # Frames were added/removed by hand; fall back to a uniform hold.
        holds = [holds[0] if holds else 400] * len(frames)
    path = gif.build_gif(
        frames,
        holds,
        out_dir / "demo.gif",
        size=args.gif_size,
        tweens=args.tweens,
        ping_pong=spec.visual.loop_style == "ping_pong",
    )
    print(f"  wrote {path}")


def _check_keys(need_anthropic: bool, need_openai: bool) -> bool:
    missing = [k for k in env.missing_keys(need_openai) if need_anthropic or k != "ANTHROPIC_API_KEY"]
    if not missing:
        return True
    where = f" (loaded {env.LOADED})" if env.LOADED else " (no .env file found)"
    print(f"Missing {', '.join(missing)}{where}.", file=sys.stderr)
    print(
        "Put them in a .env file in the directory you run hevy-exgen from (or the repo root), "
        "or export them in your shell. See .env.example.",
        file=sys.stderr,
    )
    return False


def cmd_generate(args) -> int:
    if not _check_keys(need_anthropic=True, need_openai=not args.metadata_only):
        return 2
    failures = 0
    for name in args.names:
        out_dir = args.out / output.slugify(name)
        if (out_dir / output.SPEC_FILE).exists() and not args.force:
            print(f"{out_dir} already exists; use --force to overwrite or `hevy-exgen images {out_dir}`.")
            failures += 1
            continue

        print(f"[{name}] writing metadata with {args.model}...")
        try:
            spec = metadata.generate_spec(name, args.notes, model=args.model, effort=args.effort)
        except Exception as e:  # noqa: BLE001 - report and continue with the next name
            print(f"  failed: {e}", file=sys.stderr)
            failures += 1
            continue

        output.save_spec(spec, out_dir)
        print(f"  {spec.name}: {spec.hevy_muscle_group} / {spec.hevy_exercise_type} / {spec.hevy_equipment}")

        if not args.metadata_only:
            try:
                _draw(spec, out_dir, args)
            except Exception as e:  # noqa: BLE001
                print(f"  image generation failed: {e}", file=sys.stderr)
                print(f"  metadata is saved; retry with `hevy-exgen images {out_dir}`", file=sys.stderr)
                failures += 1

        output.write_readme(spec, out_dir)
        print(f"  wrote {out_dir / 'README.md'}")

        if args.upload:
            failures += _upload(spec)
    return 1 if failures else 0


def cmd_images(args) -> int:
    if not _check_keys(need_anthropic=False, need_openai=True):
        return 2
    spec = output.load_spec(args.dir)
    print(f"[{spec.name}] drawing images...")
    _draw(spec, args.dir, args)
    output.write_readme(spec, args.dir)
    return 0


def cmd_gif(args) -> int:
    spec = output.load_spec(args.dir)
    frames = sorted((args.dir / "frames").glob("*.png"))
    if not frames:
        print(f"No frames in {args.dir / 'frames'}; run `hevy-exgen images {args.dir}` first.", file=sys.stderr)
        return 1
    _assemble(spec, args.dir, frames, args)
    output.write_readme(spec, args.dir)
    return 0


def cmd_upload(args) -> int:
    return _upload(output.load_spec(args.dir))


def _upload(spec) -> int:
    try:
        template_id = hevy_api.create_custom_exercise(spec)
    except hevy_api.HevyError as e:
        print(f"  Hevy upload failed: {e}", file=sys.stderr)
        return 1
    print(f"  created in Hevy (template id {template_id}); add image.png and the description in the app.")
    return 0


def cmd_serve(args) -> int:
    from .server import serve

    if not args.dir.is_dir():
        print(f"{args.dir} doesn't exist yet; generate an exercise first or pass --dir.", file=sys.stderr)
        return 1
    serve(args.dir, host="0.0.0.0" if args.lan else "127.0.0.1", port=args.port, open_browser=not args.no_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env.LOADED = env.load_dotenv()
    handler = {"generate": cmd_generate, "images": cmd_images, "gif": cmd_gif, "upload": cmd_upload, "serve": cmd_serve}
    return handler[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
