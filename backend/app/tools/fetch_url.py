"""URL fetcher with SSRF guard."""
from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import trafilatura

_log = logging.getLogger(__name__)


def _is_blocked_host(host: str) -> bool:
    """Block private/loopback/link-local/cloud-metadata hosts to prevent SSRF."""
    if not host:
        return True
    if host.lower() in {"localhost", "metadata.google.internal"}:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return True
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return True
    return False


def _check_url(url: str) -> None:
    """Raise ValueError if the URL targets a blocked host."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        host = ""
    if _is_blocked_host(host):
        raise ValueError(f"URL host blocked by SSRF policy: {host or '<empty>'}")


def fetch_url(url: str) -> dict:
  """Fetch URL and extract main text. Returns {title, content, word_count}."""
  _check_url(url)
  downloaded = trafilatura.fetch_url(url)
  if not downloaded:
    raise ValueError(f"无法抓取 URL: {url}")

  text = trafilatura.extract(
    downloaded,
    include_comments=False,
    include_tables=False,
    no_fallback=False,
  )
  if not text:
    raise ValueError(f"未提取到正文: {url}")

  meta = trafilatura.extract_metadata(downloaded)
  title = (meta.title if meta and meta.title else url)[:200]

  return {
    "title": title,
    "content": text,
    "word_count": len(text),
  }
