import io
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

from app.core.garment_page import PageFetchError, check_public_url, pick_product_image


PAGE = """
<html>
  <head>
    <meta property="og:image" content="https://cdn.example/logo.png">
    <script type="application/ld+json">
      {"@type": "Product", "name": "Coat", "image": ["__IMAGE__", {"@type": "ImageObject", "url": "https://cdn.example/ignored.jpg"}]}
    </script>
  </head>
</html>
"""


def test_product_json_ld_wins_over_open_graph():
    html = PAGE.replace("__IMAGE__", "https://shop.example/coat.jpg")
    chosen = pick_product_image(html.encode(), "text/html", "https://shop.example/coat")
    assert chosen == "https://shop.example/coat.jpg"


def test_relative_open_graph_uses_the_page_address():
    html = b'<meta property="og:image" content="/media/dress.webp">'
    chosen = pick_product_image(html, "text/html", "https://shop.example/dresses/1")
    assert chosen == "https://shop.example/media/dress.webp"


def test_svg_and_data_urls_are_skipped():
    html = b"""
    <meta property="og:image" content="data:image/svg+xml,abcd">
    <meta property="og:image" content="/icon.svg">
    <meta property="twitter:image" content="/look.jpg">
    """
    chosen = pick_product_image(html, "text/html", "https://shop.example/item")
    assert chosen == "https://shop.example/look.jpg"


def test_metadata_address_is_rejected():
    try:
        check_public_url("http://169.254.169.254/latest/meta-data")
    except ValueError as exc:
        assert "внутренн" in str(exc)
    else:
        raise AssertionError("metadata address was accepted")


def test_missing_photo_explains_what_to_send():
    try:
        pick_product_image(b"<html><title>empty</title></html>", "text/html", "https://shop.example")
    except PageFetchError as exc:
        assert "фото" in str(exc)
    else:
        raise AssertionError("empty page was accepted")


def _png(color: tuple[int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (80, 100), color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_api_tryon_uses_photo_from_product_page(client, api_key):
    image = _png((180, 40, 60))
    holder: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/coat.png"):
                body, content_type = image, "image/png"
            else:
                page = (
                    "<html><script type='application/ld+json'>"
                    '{"@type":"Product","image":"%s/coat.png"}'
                    "</script></html>" % holder["base"]
                )
                body, content_type = page.encode(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    holder["base"] = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        response = client.post(
            "/v1/try-on",
            headers={"X-API-Key": api_key},
            data={"model": "mock", "wait_seconds": "5", "garment_url": holder["base"] + "/product"},
            files={"person_image": ("person.png", _png((20, 40, 80)), "image/png")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "succeeded"
    finally:
        server.shutdown()
        server.server_close()


def test_api_rejects_page_on_the_internal_network(client, api_key):
    response = client.post(
        "/v1/try-on",
        headers={"X-API-Key": api_key},
        data={"model": "mock", "garment_url": "http://192.168.0.2/coat"},
        files={"person_image": ("person.png", _png((20, 40, 80)), "image/png")},
    )
    assert response.status_code == 422
    assert "внутренн" in response.json()["detail"]
