import ipaddress
import os
import socket
from email.message import Message
from pathlib import Path
from urllib.parse import quote, urljoin, urlsplit

import pypdfium2 as pdfium
import urllib3
from bs4 import BeautifulSoup, Comment, NavigableString, Tag

MAX_WEB = int(os.getenv("MAX_WEB_MB", "4")) * 1024**2
MAX_PAGES = int(os.getenv("MAX_PDF_PAGES", "500"))
MAX_TEXT = 4_000_000


class SourceError(Exception):
    """A message suitable for the research workspace."""


def fetch_page(url):
    for _ in range(6):
        try:
            parts = urlsplit(url)
            if (parts.scheme not in {"https", "http"} or not parts.hostname or
                    parts.username is not None or parts.password is not None or
                    "\\" in url or any(ord(c) < 32 for c in url)):
                raise ValueError
            host = parts.hostname.encode("idna").decode("ascii")
            port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
            if not port or "%" in host:
                raise ValueError
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except (ValueError, UnicodeError, OSError) as exc:
            raise SourceError("Не удалось определить публичный адрес страницы.") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if (not ip.is_global or ip.is_multicast or ip.is_reserved or
                    (ip.version == 6 and (ip not in ipaddress.ip_network("2000::/3") or
                                          ip.sixtofour is not None or ip.teredo is not None))):
                raise SourceError("Загрузка с локальных и непубличных адресов запрещена.")
        # Connect to the validated numeric address even if DNS later changes.
        address = addresses[0][4][0]
        pool = (urllib3.HTTPSConnectionPool(address, port, server_hostname=host, assert_hostname=host)
                if parts.scheme == "https" else urllib3.HTTPConnectionPool(address, port))
        authority = f"[{host}]" if ":" in host else host
        target = quote(parts.path or "/", safe="/%:@!$&'()*+,;=-._~")
        if parts.query:
            target += "?" + quote(parts.query, safe="/?%:@!$&'()*+,;=-._~")
        with pool:
            with pool.urlopen("GET", target, headers={"Host": f"{authority}:{port}",
                              "Accept-Encoding": "identity"}, redirect=False, retries=False,
                              preload_content=False, timeout=urllib3.Timeout(connect=5, read=10)) as response:
                if response.status in {301, 302, 303, 307, 308}:
                    location = response.headers.get("Location")
                    if not location:
                        raise SourceError("Сайт вернул перенаправление без адреса.")
                    url = urljoin(url, location)
                    continue
                if response.status != 200:
                    raise SourceError(f"Сайт не вернул страницу (HTTP {response.status}).")
                media = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if media not in {"text/html", "application/xhtml+xml"}:
                    raise SourceError("Ссылка должна вести на HTML-страницу.")
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise SourceError("Сайт вернул страницу с неподдерживаемым сжатием.")
                data = response.read(MAX_WEB + 1, decode_content=False)
                if len(data) > MAX_WEB:
                    raise SourceError(f"Страница превышает {MAX_WEB // 1024**2} МБ.")
                content_type = Message()
                content_type["Content-Type"] = response.headers["Content-Type"]
                return url, data, content_type.get_content_charset()
    raise SourceError("Слишком много перенаправлений при открытии страницы.")


def web_sections(source):
    try:
        url, data, charset = fetch_page(source["url"])
    except (urllib3.exceptions.HTTPError, OSError, ValueError) as exc:
        raise SourceError("Не удалось загрузить страницу. Проверьте ссылку и доступность сайта.") from exc
    soup = BeautifulSoup(data, "html.parser", from_encoding=charset)
    for element in soup(["script", "style", "noscript", "template", "head"]):
        element.decompose()
    heading, words, sections = None, [], []
    for node in (soup.body or soup).descendants:
        if isinstance(node, Tag) and node.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            if words:
                sections.append((None, heading, " ".join(words)))
            heading, words = node.get_text(" ", strip=True), []
        elif isinstance(node, NavigableString) and not isinstance(node, Comment):
            value = str(node).strip()
            if value:
                words.append(value)
    if words:
        sections.append((None, heading, " ".join(words)))
    return sections, url, data


def pdf_sections(source):
    sections = []
    total = 0
    try:
        with pdfium.PdfDocument(str(Path("/data/uploads") / str(source["id"]))) as doc:
            if len(doc) > MAX_PAGES:
                raise SourceError(f"В PDF больше {MAX_PAGES} страниц.")
            for index in range(len(doc)):
                page = doc[index]
                try:
                    text = page.get_textpage().get_text_bounded()
                finally:
                    page.close()
                total += len(text)
                if total > MAX_TEXT:
                    raise SourceError("В документе слишком много текста. Разделите его на части.")
                if text.strip():
                    sections.append((index + 1, None, text))
    except pdfium.PdfiumError as exc:
        raise SourceError("Не удалось прочитать PDF. Проверьте, что файл цел и открывается без пароля.") from exc
    return sections, None, None


EXTRACTORS = {"web": web_sections, "pdf": pdf_sections}
