"""Generate a scanned-PDF fixture using reportlab's image embedding (image-only, no text layer)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.pagesizes import letter

OUT = Path(__file__).resolve().parent


def load_font(size):
    for cand in [
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\cour.ttf",
    ]:
        try:
            return ImageFont.truetype(cand, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_p1(path):
    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    fT = load_font(36); fB = load_font(20); fH = load_font(22)
    d.text((80, 80), "Quarterly Sales Report", fill="black", font=fT)
    table_y, table_x, row_h = 220, 80, 40
    col_w = [200, 130, 130, 130]
    rows = [
        ["Region", "Q1", "Q2", "Q3"],
        ["North", "120", "135", "150"],
        ["South", "98", "110", "90"],
        ["Total", "218", "245", "240"],
    ]
    table_w = sum(col_w); table_h = row_h * len(rows)
    d.rectangle([table_x, table_y, table_x + table_w, table_y + table_h], outline="black", width=2)
    cum = table_x
    for w in col_w[:-1]:
        cum += w
        d.line([(cum, table_y), (cum, table_y + table_h)], fill="black", width=2)
    for i in range(1, len(rows)):
        y = table_y + i * row_h
        d.line([(table_x, y), (table_x + table_w, y)], fill="black", width=2)
    for ri, row in enumerate(rows):
        cum = table_x
        for ci, cell in enumerate(row):
            d.text((cum + 10, table_y + ri * row_h + 8), cell, fill="black", font=fH)
            cum += col_w[ci]
    d.text((80, table_y + table_h + 40), "This table uses visible grid lines.", fill="black", font=fB)
    img.save(path, "PNG", dpi=(150, 150))


def make_p2(path):
    img = Image.new("RGB", (1240, 1754), "white")
    d = ImageDraw.Draw(img)
    fT = load_font(36); fM = load_font(22)
    d.text((80, 80), "Whitespace-Aligned Table", fill="black", font=fT)
    data = [("Item","Jan","Feb","Mar"),("Widgets","120","130","145"),
            ("Gizmos","85","92","78"),("Sprockets","44","50","55")]
    widths = [200, 100, 100, 100]
    y = 200
    for row in data:
        cum = 80
        for ci, cell in enumerate(row):
            d.text((cum, y), cell, fill="black", font=fM)
            cum += widths[ci]
        y += 50
    img.save(path, "PNG", dpi=(150, 150))


p1 = OUT / "scanned_p1.png"
p2 = OUT / "scanned_p2.png"
make_p1(p1); make_p2(p2)

# Build PDF by embedding images (no text layer = true scanned).
pdf_path = OUT / "sample_scanned.pdf"
c = rl_canvas.Canvas(str(pdf_path), pagesize=letter)
for png in [p1, p2]:
    c.drawImage(str(png), 0, 0, width=letter[0], height=letter[1])
    c.showPage()
c.save()
print(f"Wrote {pdf_path} ({pdf_path.stat().st_size} bytes)")

# Verify: should have ~0 native text
import pypdf
r = pypdf.PdfReader(str(pdf_path))
total = "".join(p.extract_text() or "" for p in r.pages)
print(f"Native text length: {len(total)} chars (should be ~0)")
