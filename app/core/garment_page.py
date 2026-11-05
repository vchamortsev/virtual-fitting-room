"""Фото вещи со страницы товара: JSON-LD, Open Graph или прямая ссылка на картинку."""

import json
import socket
import urllib.error
import urllib.request
from html.parser import HTMLParser
from ipaddress import ip_address
from urllib.parse import urljoin, urlparse

from PIL import Image

from app.core.images import open_image

_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


class PageFetchError(ValueError):
    """Страницу товара не удалось прочитать или на ней нет фото."""


def garment_from_url(url: str, *, max_image_bytes: int) -> Image.Image:
    body, content_type, final_url = _fetch(url, max_bytes=max_image_bytes)
    if _looks_like_image(content_type, body):
        return open_image(body, max_bytes=max_image_bytes)
    if len(body) > 2_000_000:
        raise PageFetchError("Страница товара слишком большая.")
    image_url = pick_product_image(body, content_type, final_url)
    image_body, image_type, _ = _fetch(image_url, max_bytes=max_image_bytes)
    if not _looks_like_image(image_type, image_body):
        raise PageFetchError("По ссылке с карточки пришёл не файл изображения.")
    return open_image(image_body, max_bytes=max_image_bytes)


def pick_product_image(body: bytes, content_type: str, page_url: str) -> str:
    parser = _ProductPageParser()
    parser.feed(_decode(body, content_type))
    candidates = [*parser.product_images, *parser.meta_images, *parser.extra_images]
    for candidate in candidates:
        absolute = urljoin(page_url, candidate.strip())
        if _usable_image_url(absolute):
            return absolute
    raise PageFetchError("На странице не нашлось фото товара. Пришлите файл вещи.")


def check_public_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.hostname
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("Ссылка на товар должна начинаться с http:// или https://.")
    if host.lower() in {"metadata.google.internal"}:
        raise ValueError("Эта ссылка запрещена.")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Не удалось найти адрес страницы товара.") from exc
    for info in infos:
        if _blocked_ip(info[4][0]):
            raise ValueError("Ссылка ведёт во внутреннюю сеть. Нужна публичная страница товара.")
    return url.strip()


def _blocked_ip(raw: str) -> bool:
    address = ip_address(raw.split("%", 1)[0])
    if address.is_loopback:
        return False
    return (
        address.is_private
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _usable_image_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    path = parsed.path.lower()
    return not path.endswith(".svg")


def _looks_like_image(content_type: str, body: bytes) -> bool:
    kind = content_type.split(";", 1)[0].strip().lower()
    if kind in _IMAGE_TYPES:
        return True
    return body.startswith(b"\xff\xd8") or body.startswith(b"\x89PNG\r\n\x1a\n") or body.startswith(b"RIFF")


def _decode(body: bytes, content_type: str) -> str:
    charset = "utf-8"
    marker = "charset="
    lower = content_type.lower()
    if marker in lower:
        charset = content_type[lower.index(marker) + len(marker) :].split(";", 1)[0].strip(" \"'")
    try:
        return body.decode(charset, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _fetch(url: str, *, max_bytes: int, timeout: float = 12) -> tuple[bytes, str, str]:
    safe_url = check_public_url(url)
    request = urllib.request.Request(
        safe_url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,image/png,image/jpeg;q=0.9,*/*;q=0.8",
        },
    )
    opener = urllib.request.build_opener(_SafeRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = check_public_url(response.geturl())
            content_type = response.headers.get("Content-Type", "")
            chunks: list[bytes] = []
            total = 0
            while True:
                block = response.read(65_536)
                if not block:
                    break
                total += len(block)
                if total > max_bytes:
                    raise PageFetchError(f"Файл по ссылке больше {max_bytes // (1024 * 1024)} МБ.")
                chunks.append(block)
    except (PageFetchError, ValueError):
        raise
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise PageFetchError("Не удалось открыть ссылку на товар.") from exc
    return b"".join(chunks), content_type, final_url


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _ProductPageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta_images: list[str] = []
        self.extra_images: list[str] = []
        self.product_images: list[str] = []
        self._json_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag == "meta":
            key = (attr.get("property") or attr.get("name") or "").lower()
            if key in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"} and attr.get("content"):
                self.meta_images.append(attr["content"])
        if tag == "link":
            rel = attr.get("rel", "").lower()
            if "image_src" in rel and attr.get("href"):
                self.extra_images.append(attr["href"])
        if attr.get("itemprop", "").lower() == "image":
            source = attr.get("src") or attr.get("href") or attr.get("content")
            if source:
                self.extra_images.append(source)
        if tag == "script" and "ld+json" in attr.get("type", "").lower():
            self._json_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._json_parts is not None:
            self.product_images.extend(_images_from_jsonld("".join(self._json_parts)))
            self._json_parts = None

    def handle_data(self, data: str) -> None:
        if self._json_parts is not None:
            self._json_parts.append(data)


def _images_from_jsonld(raw: str) -> list[str]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    found: list[str] = []
    _walk_products(payload, found)
    return found


def _walk_products(node, found: list[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_products(item, found)
        return
    if not isinstance(node, dict):
        return
    if _is_product(node):
        found.extend(_image_values(node.get("image")))
    for value in node.values():
        if isinstance(value, (dict, list)):
            _walk_products(value, found)


def _is_product(node: dict) -> bool:
    kind = node.get("@type")
    values = kind if isinstance(kind, list) else [kind]
    return any(str(item).lower() in {"product", "productgroup"} for item in values)


def _image_values(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        images: list[str] = []
        for item in value:
            images.extend(_image_values(item))
        return images
    if isinstance(value, dict):
        nested = value.get("url") or value.get("contentUrl") or value.get("contentURL")
        return [nested] if isinstance(nested, str) else []
    return []
