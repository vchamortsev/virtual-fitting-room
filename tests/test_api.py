import io

from PIL import Image


def png_bytes(color: tuple[int, int, int], size: tuple[int, int] = (80, 120)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_health_lists_local_models(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["default_model"] == "mock"
    ids = [item["id"] for item in body["models"]]
    assert ids == ["fashn-vton-1.5", "catvton-flux", "mock"]
    fashn = body["models"][0]
    flux = body["models"][1]
    assert fashn["commercial_use"] is True
    assert fashn["available"] is False
    assert flux["commercial_use"] is False
    assert flux["available"] is False
    assert "некоммерческ" in flux["detail"].lower()


def test_models_require_shop_key(client):
    assert client.get("/v1/models").status_code == 401


def test_mock_tryon_returns_png(client, api_key):
    response = client.post(
        "/v1/try-on",
        headers={"X-API-Key": api_key},
        data={"category": "tops", "model": "mock", "wait_seconds": "5", "garment_photo_type": "flat-lay"},
        files={
            "person_image": ("person.png", png_bytes((20, 40, 80)), "image/png"),
            "garment_image": ("garment.png", png_bytes((180, 40, 50)), "image/png"),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["model"] == "mock"
    assert body["warning"]
    image_response = client.get(body["result_url"], headers={"X-API-Key": api_key})
    assert image_response.status_code == 200
    assert image_response.headers["content-type"].startswith("image/png")
    assert image_response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_shop_cannot_read_another_shops_job(client, api_key):
    created = client.post(
        "/v1/try-on",
        headers={"X-API-Key": api_key},
        data={"model": "mock", "wait_seconds": "5"},
        files={
            "person_image": ("person.png", png_bytes((10, 10, 10)), "image/png"),
            "garment_image": ("garment.png", png_bytes((200, 200, 200)), "image/png"),
        },
    )
    job_id = created.json()["id"]
    hidden = client.get(f"/v1/try-on/{job_id}", headers={"Authorization": "Bearer other-key"})
    assert hidden.status_code == 404


def test_explicit_fashn_without_weights_is_conflict(client, api_key):
    response = client.post(
        "/v1/try-on",
        headers={"X-API-Key": api_key},
        data={"model": "fashn"},
        files={
            "person_image": ("person.png", png_bytes((10, 20, 30)), "image/png"),
            "garment_image": ("garment.png", png_bytes((30, 20, 10)), "image/png"),
        },
    )
    assert response.status_code == 409
    assert "fashn" in response.json()["detail"].lower() or "файл" in response.json()["detail"].lower()


def test_catvton_stays_off_by_default(client, api_key):
    response = client.post(
        "/v1/try-on",
        headers={"X-API-Key": api_key},
        data={"model": "catvton-flux"},
        files={
            "person_image": ("person.png", png_bytes((10, 20, 30)), "image/png"),
            "garment_image": ("garment.png", png_bytes((30, 20, 10)), "image/png"),
        },
    )
    assert response.status_code == 409
    assert "FLUX" in response.json()["detail"]


def test_rejects_unknown_category_and_tiny_image(client, api_key):
    bad_category = client.post(
        "/v1/try-on",
        headers={"X-API-Key": api_key},
        data={"category": "shoes", "model": "mock"},
        files={
            "person_image": ("person.png", png_bytes((10, 20, 30)), "image/png"),
            "garment_image": ("garment.png", png_bytes((30, 20, 10)), "image/png"),
        },
    )
    assert bad_category.status_code == 422

    tiny = png_bytes((1, 2, 3), size=(8, 8))
    bad_image = client.post(
        "/v1/try-on",
        headers={"X-API-Key": api_key},
        data={"model": "mock"},
        files={
            "person_image": ("person.png", tiny, "image/png"),
            "garment_image": ("garment.png", png_bytes((30, 20, 10)), "image/png"),
        },
    )
    assert bad_image.status_code == 422


def test_result_image_has_expected_canvas(client, api_key, tmp_path):
    response = client.post(
        "/v1/try-on",
        headers={"X-API-Key": api_key},
        data={"model": "preview", "wait_seconds": "5"},
        files={
            "person_image": ("person.png", png_bytes((12, 40, 90), (300, 400)), "image/png"),
            "garment_image": ("garment.png", png_bytes((210, 180, 160), (200, 200)), "image/png"),
        },
    )
    content = client.get(response.json()["result_url"], headers={"X-API-Key": api_key}).content
    path = tmp_path / "result.png"
    path.write_bytes(content)
    with Image.open(path) as image:
        assert image.size == (768, 1024)
