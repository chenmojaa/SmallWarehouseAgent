"""URL fetcher using trafilatura."""
from __future__ import annotations

import trafilatura


def fetch_url(url: str) -> dict:
  """Fetch URL and extract main text. Returns {title, content, word_count}."""
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