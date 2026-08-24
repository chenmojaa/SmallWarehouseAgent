"""Parse Feishu wiki content into Markdown text.

Two formats are supported:
  - docx: raw_content is plain text. We pass it through with light cleanup.
  - bitable: records + fields -> a Markdown table (rows = records, cols = fields).

Both return the project's standard parser output:
    {"title": str, "content": str}
"""
from __future__ import annotations

from datetime import datetime, timezone


def _md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _format_field(value, field: dict) -> str:
    """Convert a bitable cell value to a single Markdown-safe string."""
    if value is None:
        return ""
    ui_type = field.get("ui_type") or ""
    if ui_type == "DateTime":
        try:
            ms = int(value)
            dt = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d")
        except (TypeError, ValueError, OSError):
            return str(value)
    if ui_type == "User":
        # value is a list of {name, en_name, id, ...}
        if isinstance(value, list):
            names = [v.get("name") or v.get("en_name") or "" for v in value]
            return ", ".join(n for n in names if n)
        return str(value)
    if ui_type == "Formula":
        # value is a list of {text, type}; the rendered text is in .text
        if isinstance(value, list):
            for v in value:
                if isinstance(v, dict) and v.get("text"):
                    return str(v["text"])
            return ""
        return str(value)
    if ui_type in ("SingleSelect",):
        # value is the option name (string)
        return str(value)
    if ui_type == "MultiSelect":
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)
    if ui_type == "Checkbox":
        return "☑" if value else "☐"
    if isinstance(value, list):
        # Generic list-of-objects fallback.
        return ", ".join(_format_field(v, field) for v in value)
    return str(value)


def _records_to_markdown(fields: list[dict], records: list[dict]) -> str:
    if not fields:
        return ""
    # Keep field order as returned; preserve only scalar/text-ish fields.
    headers = [f.get("field_name") or f.get("name") or "" for f in fields]
    rows: list[list[str]] = []
    for rec in records:
        row: list[str] = []
        rec_fields = rec.get("fields", {}) or {}
        for f in fields:
            # Field lookup is by name OR id (API varies).
            fname = f.get("field_name")
            fid = f.get("field_id")
            v = rec_fields.get(fname)
            if v is None and fid is not None:
                v = rec_fields.get(fid)
            row.append(_format_field(v, f))
        rows.append(row)

    n_cols = len(headers)
    rows = [r + [""] * (n_cols - len(r)) for r in rows]
    widths = [0] * n_cols
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(_md_escape(c)))
    widths = [max(w, len(_md_escape(h))) for w, h in zip(widths, headers)]

    def fmt_row(cells: list[str]) -> str:
        return "| " + " | ".join(_md_escape(c).ljust(widths[i]) for i, c in enumerate(cells)) + " |"

    header_line = fmt_row(headers)
    sep = "| " + " | ".join("-" * widths[i] for i in range(n_cols)) + " |"
    body = "\n".join(fmt_row(r) for r in rows)
    return header_line + "\n" + sep + ("\n" + body if body else "")


def parse_feishu_docx(doc_id: str, title: str, raw_content: str) -> dict:
    """docx is plain text wrapped with a heading. Light cleanup only."""
    text = (raw_content or "").strip()
    out_title = (title or doc_id).strip() or doc_id
    if not text:
        text = "(empty document)"
    return {"title": out_title[:200], "content": text}


def parse_feishu_bitable(app_title: str, table_title: str,
                         fields: list[dict], records: list[dict]) -> dict:
    """Render a bitable (multi-dimensional table) as a single Markdown table."""
    md = _records_to_markdown(fields, records)
    title = f"{app_title} / {table_title}" if table_title else (app_title or "Bitable")
    if not md:
        content = "(empty table)"
    else:
        content = f"### {table_title or 'Table'}\n\n{md}"
    return {"title": title[:200], "content": content}
