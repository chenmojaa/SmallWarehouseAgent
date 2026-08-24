"""Generate a fixture where a table spans 2 pages (header repeated)."""
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

OUT = Path(__file__).resolve().parent

pdf_path = OUT / "sample_continued.pdf"
doc_pdf = SimpleDocTemplate(str(pdf_path), pagesize=letter)
styles = getSampleStyleSheet()
story = [Paragraph("Multi-page Sales Report", styles["Title"]), Spacer(1, 12)]

# First page: header + 2 data rows
data1 = [
    ["Region", "Q1", "Q2", "Q3"],
    ["North", "120", "135", "150"],
    ["South", "98", "110", "90"],
]
t1 = Table(data1, hAlign="LEFT")
t1.setStyle(TableStyle([
    ("GRID", (0,0), (-1,-1), 0.5, colors.black),
    ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
]))
story.append(t1)
story.append(PageBreak())

# Second page: same header repeated + 2 more rows -> should be detected as continuation
data2 = [
    ["Region", "Q1", "Q2", "Q3"],
    ["East",  "75", "82", "90"],
    ["West",  "55", "60", "70"],
]
t2 = Table(data2, hAlign="LEFT")
t2.setStyle(TableStyle([
    ("GRID", (0,0), (-1,-1), 0.5, colors.black),
    ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
    ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
]))
story.append(t2)
story.append(Spacer(1, 24))
story.append(Paragraph("End of report.", styles["BodyText"]))

doc_pdf.build(story)
print(f"Wrote {pdf_path} ({pdf_path.stat().st_size} bytes)")
