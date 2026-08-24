"""Smoke test for all five parser paths (added scanned PDF)."""
import sys
import re

sys.path.insert(0, r'D:\one_agent\backend')

from app.tools.parse_xlsx import parse_xlsx
from app.tools.parse_doc import parse_docx
from app.tools.parse_pptx import parse_pptx
from app.tools.parse_pdf import parse_pdf


def contains_cell(label, content, cells):
    lines = content.splitlines()
    for cell in cells:
        pat = r'^\|\s*([^\n]*\s+)?' + re.escape(cell) + r'\s*\|'
        if not any(re.search(pat, ln) for ln in lines):
            print(f'  FAIL {label}: cell {cell!r} not found')
            return False
    print(f'  PASS {label}')
    return True


def check_xlsx():
    r = parse_xlsx(r'D:\one_agent\scripts\table_tests\sample.xlsx')
    return contains_cell('xlsx', r['content'], [
        'Quarterly Sales', 'Region', 'Q1', 'Q2', 'Q3',
        'North', '120', '135', '150', 'Subtotal', '218', '245', '240',
        'Note: figures in USD thousands',
    ])


def check_docx():
    r = parse_docx(r'D:\one_agent\scripts\table_tests\sample.docx')
    return contains_cell('docx', r['content'], [
        'Region', 'Q1', 'Q2', 'Q3',
        'North', '120', '135', '150',
        'South', '98', '110', '90',
        'Subtotal (N+S)', '370', 'Total', 'N/A',
    ])


def check_pptx():
    r = parse_pptx(r'D:\one_agent\scripts\table_tests\sample.pptx')
    ok = contains_cell('pptx', r['content'], [
        'Region', 'Q1', 'Q2', 'Q3',
        'North', '120', '135', '150',
        'South', '98', '110', '90',
        'Subtotal: all regions', '240',
    ])
    if any(re.match(r'^\|\s*\|\s*\|\s*\|\s*\|$', ln) for ln in r['content'].splitlines()):
        print('  FAIL pptx: spurious empty row')
        ok = False
    return ok


def check_pdf():
    r = parse_pdf(r'D:\one_agent\scripts\table_tests\sample.pdf')
    ok = contains_cell('pdf', r['content'], [
        'Region', 'Q1', 'Q2', 'Q3',
        'North', '120', '135', '150',
        'South', '98', '110', '90',
        'Total', '218', '245', '240',
        'Item', 'Jan', 'Feb', 'Mar',
        'Widgets', '120', '130', '145',
        'Gizmos', '85', '92', '78',
        'Sprockets',
    ])
    if any(re.match(r'^\|\s*\|\s*\|\s*\|\s*\|$', ln) for ln in r['content'].splitlines()):
        print('  FAIL pdf: spurious empty row')
        ok = False
    for prose in ['Quarterly Sales Report', 'Whitespace-Aligned Table']:
        if prose not in r['content']:
            print(f'  FAIL pdf: missing prose {prose!r}')
            ok = False
    return ok


def check_pdf_continued():
    r = parse_pdf(r'D:\one_agent\scripts\table_tests\sample_continued.pdf')
    headers = re.findall(r'^\|\s*Region\s*\|\s*Q1\s*\|', r['content'], re.MULTILINE)
    data = sum(1 for ln in r['content'].splitlines() if re.match(r'^\|\s*(North|South|East|West)\s*\|', ln))
    ok = len(headers) == 1 and data == 4
    if not ok:
        print(f'  FAIL pdf_continued: headers={len(headers)} data={data}')
    else:
        print('  PASS pdf_continued')
    return ok


def check_pdf_scanned():
    # Requires Tesseract to be installed and on PATH (or pytesseract.tesseract_cmd set).
    try:
        import pytesseract
        if not getattr(pytesseract.pytesseract, 'tesseract_cmd', None):
            import shutil
            for p in [r'C:\Program Files\Tesseract-OCR\tesseract.exe', '/usr/bin/tesseract']:
                import os
                if os.path.isfile(p):
                    pytesseract.pytesseract.tesseract_cmd = p
                    break
            if not getattr(pytesseract.pytesseract, 'tesseract_cmd', None) and not shutil.which('tesseract'):
                print('  SKIP pdf_scanned: tesseract not available')
                return True
    except ImportError:
        print('  SKIP pdf_scanned: pytesseract not installed')
        return True
    r = parse_pdf(r'D:\one_agent\scripts\table_tests\sample_scanned.pdf')
    # OCR has known limitations; only assert structural shape, not exact OCR text.
    ok = True
    # Both pages should have table-like rows.
    n_tables = r['content'].count('| Region |') + r['content'].count('| Item')
    if n_tables < 1:
        print('  FAIL pdf_scanned: no table detected')
        ok = False
    # Prose from each page should be present (OCR-clean parts).
    for prose in ['Quarterly Sales Report', 'Whitespace-Aligned Table']:
        if prose not in r['content']:
            print(f'  FAIL pdf_scanned: missing prose {prose!r}')
            ok = False
    if ok:
        print('  PASS pdf_scanned')
    return ok


def main():
    results = {
        'xlsx':         check_xlsx(),
        'docx':         check_docx(),
        'pptx':         check_pptx(),
        'pdf':          check_pdf(),
        'pdf_continued': check_pdf_continued(),
        'pdf_scanned':  check_pdf_scanned(),
    }
    print()
    print(' '.join(f'{k}={"PASS" if v else "FAIL"}' for k, v in results.items()))
    return 0 if all(results.values()) else 1


if __name__ == '__main__':
    sys.exit(main())
