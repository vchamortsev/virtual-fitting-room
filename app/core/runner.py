"""Один поток на примерку: видеокарта не делится между запросами."""

import json
import logging
import shutil
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from queue import Queue

from PIL import Image

from app.core.store import Job, JobStore
from app.providers.base import TryOnInput
from app.providers.mock import MOCK_WARNING
from app.providers.registry import ProviderRegistry

log = logging.getLogger(__name__)


class JobRunner:
    def __init__(
        self,
        store: JobStore,
        registry: ProviderRegistry,
        data_dir: Path,
        retention_hours: int,
        public_base_url: str = "",
    ):
        self.store = store
        self.registry = registry
        self.data_dir = data_dir
        self.retention_hours = retention_hours
        self.public_base_url = public_base_url.rstrip("/")
        self._queue: Queue[str | None] = Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._progress_lock = threading.Lock()
        self._progress: dict[str, dict] = {}

    def start(self) -> None:
        self.store.fail_interrupted("Сервер перезапустился во время примерки. Отправьте фото ещё раз.")
        self.cleanup()
        for job_id in self.store.queued_ids():
            self._queue.put(job_id)
        self._thread = threading.Thread(target=self._loop, name="tryon-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)
        if self._thread is not None:
            self._thread.join(timeout=5)

    def submit(self, job_id: str) -> None:
        self._queue.put(job_id)

    def note_progress(self, job_id: str, step: int, steps: int) -> None:
        """Первый завершённый шаг включает подготовку фото, поэтому в оценку времени не входит."""

        now = time.monotonic()
        with self._progress_lock:
            state = self._progress.get(job_id)
            if state is None:
                state = {"step": 0, "steps": steps, "mark": now, "samples": []}
                self._progress[job_id] = state
            state["steps"] = steps
            if step > state["step"]:
                if state["step"] >= 1:
                    state["samples"].append(now - state["mark"])
                state["mark"] = now
                state["step"] = step

    def progress_of(self, job_id: str) -> dict | None:
        with self._progress_lock:
            state = self._progress.get(job_id)
            if state is None:
                return None
            samples = state["samples"]
            eta = None
            if samples:
                average = sum(samples) / len(samples)
                remaining = max(0, state["steps"] - state["step"])
                eta = int(round(average * remaining))
            return {"step": state["step"], "steps": state["steps"], "eta_seconds": eta}

    def clear_progress(self, job_id: str) -> None:
        with self._progress_lock:
            self._progress.pop(job_id, None)

    def job_dir(self, job_id: str) -> Path:
        return self.data_dir / "jobs" / job_id

    def result_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "result.png"

    def cleanup(self) -> None:
        for job_id in self.store.expired_ids(self.retention_hours):
            self.store.delete(job_id)
            shutil.rmtree(self.job_dir(job_id), ignore_errors=True)

    def _loop(self) -> None:
        while not self._stop.is_set():
            job_id = self._queue.get()
            try:
                if job_id is None:
                    return
                self._run(job_id)
            except Exception:
                log.exception("Сбой обработчика задания %s", job_id)
            finally:
                self._queue.task_done()

    def _run(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None or job.status != "queued":
            return
        self.cleanup()
        self.store.mark_running(job_id)
        log.info("Примерка %s, модель %s", job_id, job.model)
        try:
            image = self._generate(job)
            destination = self.result_path(job_id)
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination, format="PNG", optimize=True)
            self.store.mark_succeeded(job_id)
            log.info("Примерка %s готова", job_id)
        except RuntimeError as exc:
            log.info("Примерка %s отклонена: %s", job_id, exc)
            self.store.mark_failed(job_id, str(exc))
        except Exception:
            log.exception("Примерка %s упала", job_id)
            self.store.mark_failed(job_id, "Примерка не выполнилась. Подробности в журнале сервера.")
        finally:
            self.clear_progress(job_id)
        self._notify(job_id)

    def _generate(self, job: Job) -> Image.Image:
        folder = self.job_dir(job.id)
        with Image.open(folder / "person.jpg") as source:
            person = source.convert("RGB")
        with Image.open(folder / "garment.jpg") as source:
            garment = source.convert("RGB")
        mask_path = folder / "mask.png"
        mask = None
        if mask_path.is_file():
            with Image.open(mask_path) as source:
                mask = source.convert("L")
        provider = self.registry.get(job.model)
        card = provider.probe()
        if not card.available:
            raise RuntimeError(card.detail)
        return provider.generate(
            TryOnInput(
                person=person,
                garment=garment,
                category=job.category,
                garment_photo_type=job.garment_photo_type,
                seed=job.seed,
                num_timesteps=job.num_timesteps,
                guidance_scale=job.guidance_scale,
                segmentation_free=job.segmentation_free,
                mask=mask,
            ),
            on_progress=lambda step, steps: self.note_progress(job.id, step, steps),
        )

    def _notify(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None or not job.webhook_url:
            return
        payload = {
            "id": job.id,
            "status": job.status,
            "model": job.model,
            "error": job.error,
        }
        if job.status == "succeeded":
            path = f"/v1/try-on/{job.id}/result"
            payload["result_url"] = f"{self.public_base_url}{path}" if self.public_base_url else path
        if job.model == "mock":
            payload["warning"] = MOCK_WARNING
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            job.webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=5):
                return
        except (urllib.error.URLError, TimeoutError) as exc:
            log.info("Webhook для %s не доставлен: %s", job_id, exc)
