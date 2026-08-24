import zipfile, re
z = zipfile.ZipFile(r'D:\one_agent\scripts\table_tests\sample.pptx')
xml = z.read('ppt/slides/slide1.xml').decode('utf-8')
matches = list(re.finditer(r'<a:tc[ >].*?</a:tc>', xml, re.DOTALL))
print(f'TCs: {len(matches)}')
for i, m in enumerate(matches):
    body = m.group(0)
    gs = re.search(r'gridSpan="(\d+)"', body)
    rs = re.search(r'rowSpan="(\d+)"', body)
    hm = re.search(r'hMerge="(true|1)"', body)
    vm = re.search(r'vMerge="(true|1)"', body)
    text = ' '.join(re.findall(r'<a:t>([^<]*)</a:t>', body))
    print(f'  tc#{i}: text={text!r} gridSpan={gs and gs.group(1)} rowSpan={rs and rs.group(1)} hMerge={bool(hm)} vMerge={bool(vm)}')
