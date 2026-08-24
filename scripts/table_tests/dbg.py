"""Debug fixture generation for docx subtotal row."""
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

d = Document()
table = d.add_table(rows=4, cols=4)
table.style = "Table Grid"
table.rows[0].cells[0].text = "Region"
table.rows[0].cells[1].text = "Q1"
table.rows[0].cells[2].text = "Q2"
table.rows[0].cells[3].text = "Q3"
table.rows[1].cells[0].text = "North"
table.rows[1].cells[1].text = "120"
table.rows[2].cells[0].text = "South"
table.rows[2].cells[1].text = "98"
# Row 3: gridSpan=3 anchor + 370 at col 3
r3 = table.rows[3]
r3.cells[0].text = "Subtotal (N+S)"
def add_gridspan(tc, n):
    tcPr = tc.get_or_add_tcPr()
    gs = OxmlElement("w:gridSpan"); gs.set(qn("w:val"), str(n)); tcPr.append(gs)
add_gridspan(r3.cells[0]._tc, 3)
tr3 = r3._tr
tcs = tr3.findall(qn("w:tc"))
print('Initial tcs:', len(tcs))
for i, t in enumerate(tcs):
    print(f'  tcs[{i}]: text="{_extract(t)}"')
def _extract(tc):
    return "".join(t.text or "" for t in tc.iter(qn("w:t"))).strip()
tr3.remove(tcs[1])
tr3.remove(tcs[2])
tcs_after = tr3.findall(qn("w:tc"))
print('After remove:', len(tcs_after))
for i, t in enumerate(tcs_after):
    print(f'  tcs[{i}]: text="{_extract(t)}"')
