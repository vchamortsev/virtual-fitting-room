import time
import pytest

from app.core.runner import JobRunner
from app.providers.fashn import run_with_step_progress


def test_eta_starts_after_a_measured_step(tmp_path):
    runner = JobRunner(store=None, registry=None, data_dir=tmp_path, retention_hours=1)
    runner.note_progress("job_a", 0, 10)
    assert runner.progress_of("job_a") == {"step": 0, "steps": 10, "eta_seconds": None}

    runner.note_progress("job_a", 1, 10)
    assert runner.progress_of("job_a")["eta_seconds"] is None

    time.sleep(0.2)
    runner.note_progress("job_a", 2, 10)
    snapshot = runner.progress_of("job_a")
    assert snapshot["step"] == 2
    assert snapshot["steps"] == 10
    assert snapshot["eta_seconds"] is not None
    assert 1 <= snapshot["eta_seconds"] <= 3

    runner.clear_progress("job_a")
    assert runner.progress_of("job_a") is None


def test_sampling_wrapper_reports_each_step():
    pipe = pytest.importorskip("fashn_vton.pipeline", reason="Для этого теста нужен дополнительный движок FASHN")

    calls = []

    def pipeline(**kwargs):
        for _ in pipe.tqdm(range(kwargs["num_timesteps"]), total=kwargs["num_timesteps"]):
            pass
        return "done"

    result = run_with_step_progress(pipeline, 3, lambda step, steps: calls.append((step, steps)), num_timesteps=3)
    assert result == "done"
    assert calls == [(0, 3), (1, 3), (2, 3), (3, 3)]


def test_finished_job_has_no_progress(client, api_key):
    response = client.post(
        "/v1/try-on",
        headers={"X-API-Key": api_key},
        data={"model": "mock", "wait_seconds": "5"},
        files={
            "person_image": ("person.png", _png(), "image/png"),
            "garment_image": ("garment.png", _png(), "image/png"),
        },
    )
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["step"] is None
    assert body["steps"] is None
    assert body["eta_seconds"] is None


def _png() -> bytes:
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (80, 120), (20, 40, 80)).save(buffer, format="PNG")
    return buffer.getvalue()
