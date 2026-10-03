"""Create the exercise in Hevy via its public API (Hevy Pro; key under Settings > Developer).

The API only accepts title, type, equipment and muscle groups. The image and
description still have to be added in the app.
"""

import json
import os
import urllib.error
import urllib.request

from .models import ExerciseSpec

API_URL = "https://api.hevyapp.com/v1/exercise_templates"


class HevyError(RuntimeError):
    pass


def create_custom_exercise(spec: ExerciseSpec, api_key: str | None = None) -> int | None:
    api_key = api_key or os.environ.get("HEVY_API_KEY")
    if not api_key:
        raise HevyError("Set HEVY_API_KEY (Hevy app > Settings > Developer) to upload.")

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(spec.hevy_payload()).encode(),
        headers={"api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            body = resp.read().decode() or "{}"
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        if e.code == 403:
            raise HevyError(f"Hevy refused the exercise (custom exercise limit?): {detail}") from e
        raise HevyError(f"Hevy API error {e.code}: {detail}") from e

    try:
        return json.loads(body).get("id")
    except (json.JSONDecodeError, AttributeError):
        return None
