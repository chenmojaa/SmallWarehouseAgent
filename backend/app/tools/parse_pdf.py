"""Parse PDF -> Markdown text using pdfplumber, with table extraction.

Strategy per page (text-PDF path):
  1. Try line-based detection (visible borders) -- high precision.
  2. If none found, fall back to text-alignment detection -- lower precision
     but works for whitespace-aligned tables.
  3. Regions outside detected tables become flowing text.

Strategy per page (scanned-PDF fallback):
  - Render the page to an image, run Tesseract OCR with PSM 6 (block of text).
  - Group OCR'd words into lines by y-coordinate (10-pt tolerance).
  - Within each line, split into cells by x-gaps above a threshold.
  - Detect table regions: contiguous lines where (a) cell count is consistent,
    (b) cell x-starts align within tolerance.
  - Remaining lines become flowing prose.

Cross-page continuation:
  If a page's first table row looks like the previous page's last table header
  (same column count + similar first-row content), drop the duplicate header
  and append the body rows to the previous table.

Per-page layout:
  Tables and paragraphs are emitted in vertical (y) order so the output
  mirrors the visual flow of the page.
"""
from __future__ import annotations

import os
import shutil
from collections import defaultdict
from difflib import SequenceMatcher
from statistics import median

import pdfplumber
from pypdf import PdfReader


_LINES_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 4,
    "join_tolerance": 4,
}

_TEXT_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "text_tolerance": 3,
    "text_x_tolerance": 3,
}

OCR_CONFIG = "--psm 12"  # Assume a uniform block of text
OCR_Y_TOLERANCE = 12   # px tolerance for grouping words into lines (OCR has jitter)
OCR_X_CLUSTER_GAP = 50  # absolute px threshold: gap between words that splits into a new column
OCR_TABLE_MIN_ROWS = 3   # need at least this many consistent lines to call it a table
OCR_CONF_MIN = 30        # tesseract conf threshold


def _md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _clean_rows(rows: list[list[str]]) -> list[list[str]]:
    rows = [[(c or "").strip() for c in r] for r in rows]
    rows = [r for r in rows if any(c for c in r)]
    return rows


def _format_row(row: list[str], widths: list[int]) -> str:
    return "| " + " | ".join(_md_escape(c).ljust(widths[i]) for i, c in enumerate(row)) + " |"


def _table_to_markdown(rows: list[list[str]]) -> str:
    rows = _clean_rows(rows)
    if not rows:
        return ""
    n_cols = max((len(r) for r in rows), default=0)
    rows = [(r + [""] * (n_cols - len(r))) for r in rows]
    widths = [0] * n_cols
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(_md_escape(c)))
    header = rows[0]
    sep = "| " + " | ".join("-" * widths[i] for i in range(n_cols)) + " |"
    body = "\n".join(_format_row(r, widths) for r in rows[1:])
    out = _format_row(header, widths) + "\n" + sep
    if body:
        out += "\n" + body
    return out


def _render_body_rows(rows: list[list[str]], col_widths: list[int]) -> str:
    out_lines = []
    for r in rows:
        cells = r + [""] * (len(col_widths) - len(r))
        out_lines.append(_format_row(cells, col_widths))
    return "\n".join(out_lines)


def _merge_table_into(previous_md: str, new_rows: list[list[str]], widths: list[int], drop_first: bool) -> str:
    head, sep, *body_lines = previous_md.split("\n")
    body_lines = [ln for ln in body_lines if ln.strip()]
    extra_rows = _clean_rows(new_rows[1:] if drop_first else new_rows)
    if not extra_rows:
        return previous_md
    extra_md = _render_body_rows(extra_rows, widths)
    return "\n".join([head, sep, *body_lines, extra_md])


def _looks_like_continuation(prev_header: list[str], new_first_row: list[str]) -> bool:
    if len(prev_header) != len(new_first_row):
        return False
    a = [(c or "").strip() for c in prev_header]
    b = [(c or "").strip() for c in new_first_row]
    if not any(a) or not any(b):
        return False
    matches = 0
    for x, y in zip(a, b):
        if x and y and SequenceMatcher(None, x.lower(), y.lower()).ratio() > 0.6:
            matches += 1
    return matches >= max(1, len(a) // 2)


def _find_tables_on_page(page) -> list:
    found = page.find_tables(table_settings=_LINES_SETTINGS)
    if found:
        return list(found)
    return list(page.find_tables(table_settings=_TEXT_SETTINGS))


def _text_outside_tables(page, tables) -> str:
    if not tables:
        return page.extract_text() or ""
    boxes = [t.bbox for t in tables]

    def keep_word(word):
        for (bx0, btop, bx1, bbot) in boxes:
            if word["x0"] < bx1 and word["x1"] > bx0 and word["top"] < bbot and word["bottom"] > btop:
                return False
        return True

    words = [w for w in page.extract_words(use_text_flow=True) if keep_word(w)]
    lines: dict = {}
    for w in words:
        key = round(w["top"], 1)
        lines.setdefault(key, []).append(w)
    out = []
    for key in sorted(lines):
        ws = sorted(lines[key], key=lambda w: w["x0"])
        out.append(" ".join(w["text"] for w in ws))
    return "\n".join(out)


def _widths_of_md_table(md: str) -> list[int]:
    lines = md.split("\n")
    if len(lines) < 2:
        return []
    sep = lines[1]
    widths = []
    for cell in sep.strip().strip("|").split("|"):
        widths.append(len(cell.strip()))
    return widths


# ---------------------- OCR-based scanned-PDF path ----------------------

def _tesseract_cmd() -> str | None:
    """Locate the tesseract binary, allowing common Windows install paths."""
    import pytesseract
    if getattr(pytesseract.pytesseract, "tesseract_cmd", None):
        return pytesseract.pytesseract.tesseract_cmd
    # Probe well-known locations.
    for path in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
    ]:
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return path
    if shutil.which("tesseract"):
        return shutil.which("tesseract")
    return None


def _ocr_page_words(page) -> list[dict]:
    """Render a pdfplumber page to a PIL image and run Tesseract OCR."""
    cmd = _tesseract_cmd()
    if not cmd:
        raise RuntimeError(
            "Tesseract binary not found. Install Tesseract and add it to PATH, "
            "or set pytesseract.pytesseract.tesseract_cmd."
        )
    import pytesseract
    pil_img = page.to_image(resolution=200).original
    data = pytesseract.image_to_data(pil_img, output_type=pytesseract.Output.DICT, config=OCR_CONFIG)
    words = []
    for i, text in enumerate(data["text"]):
        s = (text or "").strip()
        if not s:
            continue
        try:
            conf = int(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1
        if conf < OCR_CONF_MIN:
            continue
        words.append({
            "text": s,
            "x0": data["left"][i],
            "x1": data["left"][i] + data["width"][i],
            "top": data["top"][i],
            "bottom": data["top"][i] + data["height"][i],
        })
    return words


def _group_words_into_lines(words: list[dict], y_tol: int = OCR_Y_TOLERANCE) -> list[list[dict]]:
    """Cluster words into lines by y-coordinate."""
    if not words:
        return []
    words_sorted = sorted(words, key=lambda w: (w["top"], w["x0"]))
    lines = []
    cur = []
    cur_top = words_sorted[0]["top"]
    for w in words_sorted:
        if abs(w["top"] - cur_top) <= y_tol:
            cur.append(w)
            cur_top = (cur_top + w["top"]) / 2 if cur else w["top"]
        else:
            cur.sort(key=lambda x: x["x0"])
            lines.append(cur)
            cur = [w]
            cur_top = w["top"]
    if cur:
        cur.sort(key=lambda x: x["x0"])
        lines.append(cur)
    return lines


def _line_to_cells(line: list[dict]) -> list[str]:
    """Split a line into cells by x-cluster gap.

    Words separated by more than OCR_X_CLUSTER_GAP pixels belong to different
    columns. This handles both prose lines (small inter-word gaps -> 1 cell)
    and table rows (large cell-to-cell gaps -> multiple cells).
    """
    if not line:
        return []
    if len(line) == 1:
        return [line[0]["text"]]
    cells = [[line[0]["text"]]]
    for i in range(1, len(line)):
        gap = line[i]["x0"] - line[i - 1]["x1"]
        if gap > OCR_X_CLUSTER_GAP:
            cells.append([line[i]["text"]])
        else:
            cells[-1].append(line[i]["text"])
    return [" ".join(c) for c in cells]


def _line_x_starts(line: list[dict]) -> list[int]:
    """Return column-start x-coords for a line, collapsing nearby starts.

    OCR sometimes splits a single cell into multiple adjacent words (e.g. "i"
    + "North" at slightly different x). Words whose x-start is within 30px of
    the previous start are merged into the same column.
    """
    starts = sorted(w["x0"] for w in line)
    collapsed = [starts[0]]
    for s in starts[1:]:
        if s - collapsed[-1] > 30:
            collapsed.append(s)
    return collapsed


def _detect_tables_from_lines(lines: list[list[dict]]) -> tuple[list[list[list[str]]], list[list[dict]]]:
    """Return (tables, prose_lines).

    A table region is a contiguous run of lines where each line has 2+ cells
    AND the column x-starts align with the previous line within tolerance.
    """
    tables = []
    prose_lines = []
    if not lines:
        return tables, prose_lines

    # Compute cells per line and x-starts.
    line_info = []
    for ln in lines:
        cells = _line_to_cells(ln)
        line_info.append({"cells": cells, "x_starts": _line_x_starts(ln), "line": ln})

    # Walk through line_info, grouping consecutive lines that share structure.
    i = 0
    while i < len(line_info):
        cur = line_info[i]
        if len(cur["cells"]) < 2:
            prose_lines.append(cur["line"])
            i += 1
            continue
        # Start of a candidate table at index i.
        n_cols = len(cur["cells"])
        block_rows: list[list[str]] = [list(cur["cells"])]
        # Tracks how many consecutive "OCR drop" (1-cell) rows we have skipped
        # within the candidate table; tolerate up to 2.
        drop_streak = 0
        prev_top = cur["line"][0]["top"]
        row_gaps: list[float] = []
        max_gap = 75.0  # absolute ceiling for "this row is still in the table"
        j = i + 1
        while j < len(line_info):
            nxt = line_info[j]
            cur_top = nxt["line"][0]["top"]
            gap = cur_top - prev_top
            if gap > max_gap:
                # Big visual gap -> row is no longer part of this table.
                break
            if len(nxt["cells"]) < 2:
                # Possible OCR drop: 1-cell row between multi-cell rows.
                if drop_streak >= 2:
                    break
                drop_streak += 1
                block_rows.append([nxt["cells"][0]] + [""] * (n_cols - 1))
                prev_top = cur_top
                j += 1
                continue
            drop_streak = 0
            ref = cur["x_starts"]
            cand = nxt["x_starts"]
            # Allow small column-count drift (OCR-induced) by matching the
            # shorter list to a subset of the longer one.
            shorter, longer = (ref, cand) if len(ref) <= len(cand) else (cand, ref)
            used = [False] * len(longer)
            aligned = 0
            for s in shorter:
                best_i = -1; best_d = 9999
                for k, lx in enumerate(longer):
                    if used[k]: continue
                    d = abs(lx - s)
                    if d < best_d:
                        best_d = d; best_i = k
                if best_i >= 0 and best_d <= 40:
                    used[best_i] = True
                    aligned += 1
            if aligned < len(shorter):
                break
            row_cells = list(nxt["cells"])
            while len(row_cells) < n_cols:
                row_cells.append("")
            block_rows.append(row_cells)
            row_gaps.append(cur_top - prev_top)
            # Tighten max_gap from observed median row spacing once we have 2+ rows.
            if len(row_gaps) >= 2:
                sorted_gaps = sorted(row_gaps)
                median_gap = sorted_gaps[len(sorted_gaps) // 2]
                # Use the smaller of (60px) and (median * 2) to avoid pulling in
                # distant prose.
                max_gap = min(75.0, max(35.0, median_gap * 1.8))
            prev_top = cur_top
            j += 1
        block_cells = block_rows
        if len(block_cells) >= OCR_TABLE_MIN_ROWS:
            tables.append(block_cells)
            i = j
        else:
            # Treat the first line as prose; advance one.
            prose_lines.append(cur["line"])
            i += 1
    return tables, prose_lines


def _format_ocr_table(rows: list[list[str]]) -> str:
    return _table_to_markdown(rows)


def _line_to_text(line: list[dict]) -> str:
    return " ".join(w["text"] for w in sorted(line, key=lambda w: w["x0"]))


def _ocr_page_to_items(page, page_index: int) -> list:
    """Process a scanned page: OCR -> (tables, prose) -> y-ordered items."""
    words = _ocr_page_words(page)
    if not words:
        return []
    lines = _group_words_into_lines(words)
    tables, prose_lines = _detect_tables_from_lines(lines)
    items: list = []
    # Group tables and prose by y-position.
    for tbl_rows in tables:
        # The "y" is the top of the first line in this block.
        first_line = lines[_first_line_index_of(lines, tbl_rows)]
        y_top = first_line[0]["top"]
        items.append(("table", y_top, tbl_rows))
    for ln in prose_lines:
        y_top = ln[0]["top"]
        items.append(("text", y_top, _line_to_text(ln)))
    items.sort(key=lambda x: x[1])
    return items


def _first_line_index_of(lines: list[list[dict]], tbl_rows: list[list[list[str]]]) -> int:
    """Locate the line index in `lines` whose cells match the first row of `tbl_rows`."""
    target = tbl_rows[0]
    for i, ln in enumerate(lines):
        cells = _line_to_cells(ln)
        if cells == target:
            return i
    return 0


def _has_any_text_layer(pdf) -> bool:
    """True if any page in the PDF yields non-empty text via pdfplumber."""
    for page in pdf.pages:
        if (page.extract_text() or "").strip():
            return True
    return False


def parse_pdf(path: str) -> dict:
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    parts: list[str] = []
    prev_header: list[str] | None = None

    try:
        with pdfplumber.open(path) as pdf:
            # Decide which path to use.
            # If no page has native text, treat as scanned -> OCR.
            use_ocr = not _has_any_text_layer(pdf)

            for i, page in enumerate(pdf.pages):
                if use_ocr:
                    items = _ocr_page_to_items(page, i)
                else:
                    items = _text_pdf_page_items(page, i)

                for kind, _, payload in items:
                    if kind == "table":
                        cleaned = payload
                        is_continuation = (
                            prev_header is not None
                            and parts
                            and _looks_like_continuation(prev_header, cleaned[0])
                        )
                        if is_continuation:
                            widths = _widths_of_md_table(parts[-1])
                            merged = _merge_table_into(parts[-1], cleaned, widths, drop_first=True)
                            parts[-1] = merged
                        else:
                            md = _table_to_markdown(cleaned)
                            if md:
                                parts.append(md)
                                prev_header = cleaned[0]
                    else:
                        text = (payload or "").strip()
                        if text:
                            parts.append(f"[P{i + 1}]\n{text}")
    except Exception as e:
        reader = PdfReader(path)
        pages_text = []
        for j, p in enumerate(reader.pages):
            txt = p.extract_text() or ""
            if txt.strip():
                pages_text.append(f"[P{j + 1}]\n{txt}")
        fallback = "\n\n".join(pages_text).strip()
        if not fallback:
            raise ValueError(f"PDF failed to parse: {type(e).__name__}: {e}")
        return {
            "title": os.path.basename(path),
            "content": fallback,
            "word_count": len(fallback),
            "page_count": len(reader.pages),
        }

    content = "\n\n".join(parts).strip()
    if not content:
        raise ValueError(f"PDF has no extractable content: {path}")
    return {"title": os.path.basename(path), "content": content}


def _text_pdf_page_items(page, page_index: int) -> list:
    """Existing text-PDF path: pdfplumber tables + masked prose, y-ordered."""
    tables = _find_tables_on_page(page)
    tables_sorted = sorted(tables, key=lambda t: (t.bbox[1], t.bbox[0]))

    items: list = []
    if not tables_sorted:
        text = page.extract_text() or ""
        if text.strip():
            items.append(("text", 0.0, text.strip()))
        return items

    boxes = [t.bbox for t in tables_sorted]
    table_payloads = []
    for t, bbox in zip(tables_sorted, boxes):
        rows_raw = t.extract()
        if not rows_raw:
            continue
        cleaned = [[(c or "").strip() for c in r] for r in rows_raw]
        if not any(any(c for c in r) for r in cleaned):
            continue
        table_payloads.append((bbox[1], cleaned))

    page_words = page.extract_words(use_text_flow=True)
    line_groups: dict = {}
    for w in page_words:
        in_table = False
        for (bx0, btop, bx1, bbot) in boxes:
            if w["x0"] < bx1 and w["x1"] > bx0 and w["top"] < bbot and w["bottom"] > btop:
                in_table = True
                break
        if in_table:
            continue
        key = round(w["top"], 1)
        line_groups.setdefault(key, []).append(w)

    line_keys = sorted(line_groups.keys())
    text_blocks = []
    cur_block_lines = []
    cur_block_y = None
    for ly in line_keys:
        if cur_block_y is None:
            cur_block_y = ly
            cur_block_lines = [ly]
        else:
            if ly - cur_block_y < 4:
                cur_block_lines.append(ly)
                cur_block_y = ly
            else:
                ws_all = sorted(
                    [w for k in cur_block_lines for w in line_groups[k]],
                    key=lambda w: (w["top"], w["x0"]),
                )
                seen_top = -1.0
                rendered = []
                for w in ws_all:
                    if abs(w["top"] - seen_top) > 2:
                        rendered.append([])
                        seen_top = w["top"]
                    rendered[-1].append(w["text"])
                block_text = "\n".join(" ".join(line) for line in rendered).strip()
                if block_text:
                    text_blocks.append((cur_block_lines[0], block_text))
                cur_block_y = ly
                cur_block_lines = [ly]
    if cur_block_lines:
        ws_all = sorted(
            [w for k in cur_block_lines for w in line_groups[k]],
            key=lambda w: (w["top"], w["x0"]),
        )
        seen_top = -1.0
        rendered = []
        for w in ws_all:
            if abs(w["top"] - seen_top) > 2:
                rendered.append([])
                seen_top = w["top"]
            rendered[-1].append(w["text"])
        block_text = "\n".join(" ".join(line) for line in rendered).strip()
        if block_text:
            text_blocks.append((cur_block_lines[0], block_text))

    items = [("table", y, rows) for (y, rows) in table_payloads]
    items += [("text", y, text) for (y, text) in text_blocks]
    items.sort(key=lambda x: x[1])
    return items
