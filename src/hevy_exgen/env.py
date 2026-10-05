"""Load API keys from a .env file so they don't have to be exported by hand."""

import os
from pathlib import Path

LOADED: Path | None = None  # the .env file the CLI loaded, for error messages


def find_dotenv(start: Path | None = None) -> Path | None:
    """Return the nearest .env in the start dir or its parents, else the one in the repo root."""
    here = (start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        if (d / ".env").is_file():
            return d / ".env"
    repo_env = Path(__file__).resolve().parents[2] / ".env"
    return repo_env if repo_env.is_file() else None


def load_dotenv(path: Path | None = None) -> Path | None:
    """Set variables from .env. A non-empty value already in the environment wins."""
    path = path or find_dotenv()
    if path is None:
        return None
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value and not os.environ.get(key):
            os.environ[key] = value
    return path


def missing_keys(need_openai: bool) -> list[str]:
    missing = []
    has_profile = (Path.home() / ".config" / "anthropic").is_dir()  # from `ant auth login`
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN") or has_profile):
        missing.append("ANTHROPIC_API_KEY")
    if need_openai and not os.environ.get("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")
    return missing
