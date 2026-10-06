import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from hevy_exgen import output
from hevy_exgen.models import ExerciseSpec
from hevy_exgen.server import Library, make_handler

from .test_pipeline import SPEC, png_bytes


@pytest.fixture
def base_url(tmp_path):
    ex = tmp_path / "smith-calf-raise"
    output.save_spec(ExerciseSpec.model_validate(SPEC), ex)
    (ex / "image.png").write_bytes(png_bytes("red"))
    (ex / "frames").mkdir()
    (ex / "frames" / "00-bottom.png").write_bytes(png_bytes("blue"))
    (tmp_path / "secret.png").write_bytes(png_bytes("green"))
    (tmp_path / "not-an-exercise").mkdir()

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Library(tmp_path)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", ex
    server.shutdown()
    server.server_close()


def get(url):
    with urllib.request.urlopen(url) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


def status_of(url, data=None):
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_index_and_list(base_url):
    url, _ = base_url
    status, ctype, body = get(url + "/")
    assert status == 200 and ctype.startswith("text/html") and b"Exercise Library" in body

    items = json.loads(get(url + "/api/exercises")[2])
    assert [i["slug"] for i in items] == ["smith-calf-raise"]
    assert items[0]["name"] == SPEC["name"]
    assert items[0]["thumb"] == "/files/smith-calf-raise/image.png"
    assert items[0]["added_to_hevy"] is False


def test_detail_has_copy_ready_fields(base_url):
    url, _ = base_url
    d = json.loads(get(url + "/api/exercises/smith-calf-raise")[2])
    fields = {f["label"]: f["value"] for f in d["hevy_fields"]}
    assert fields == {
        "Name": SPEC["name"],
        "Equipment": "Machine",
        "Primary muscle group": "Calves",
        "Other muscles": "Quadriceps",
        "Exercise type": "Weight & Reps",
    }
    assert d["notes"].startswith(SPEC["description"])
    assert "Setup:\n1. Set bar on traps" in d["notes"]
    assert d["gif"] is None
    assert d["frames"] == ["/files/smith-calf-raise/frames/00-bottom.png"]


def test_files_served_and_traversal_blocked(base_url):
    url, _ = base_url
    status, ctype, body = get(url + "/files/smith-calf-raise/image.png")
    assert status == 200 and ctype == "image/png" and body == png_bytes("red")
    assert status_of(url + "/files/smith-calf-raise/exercise.json") == 404  # only images are served
    assert status_of(url + "/files/smith-calf-raise/..%2Fsecret.png") == 404
    assert status_of(url + "/files/..%2F/secret.png") == 404
    assert status_of(url + "/api/exercises/not-an-exercise") == 404


def test_added_to_hevy_status_persists(base_url):
    url, ex = base_url
    assert status_of(url + "/api/exercises/smith-calf-raise/status", b'{"added_to_hevy": true}') == 200
    assert json.loads((ex / "status.json").read_text()) == {"added_to_hevy": True}
    assert json.loads(get(url + "/api/exercises")[2])[0]["added_to_hevy"] is True
    assert status_of(url + "/api/exercises/nope/status", b'{"added_to_hevy": true}') == 404
