"""Apply cell edits to original OOXML parts, preserving unrelated Excel extensions."""

import io
import posixpath
import zipfile
from copy import deepcopy

from lxml import etree as XML
from openpyxl.utils.cell import coordinate_to_tuple

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
RID = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
ORDER = "sheetPr dimension sheetViews sheetFormatPr cols sheetData sheetCalcPr sheetProtection protectedRanges scenarios autoFilter sortState dataConsolidate customSheetViews mergeCells phoneticPr conditionalFormatting dataValidations hyperlinks printOptions pageMargins pageSetup headerFooter rowBreaks colBreaks customProperties cellWatches ignoredErrors smartTags drawing legacyDrawing legacyDrawingHF picture oleObjects controls webPublishItems tableParts extLst".split()  # noqa: E501


def parse(data):
    return XML.fromstring(data, XML.XMLParser(resolve_entities=False, no_network=True, load_dtd=False))


def encode(root):
    return XML.tostring(root, encoding="UTF-8", xml_declaration=True)


def tag(name):
    return "{" + NS + "}" + name


def insert(root, child):
    name = XML.QName(child).localname
    rank = ORDER.index(name) if name in ORDER else len(ORDER)
    for i, node in enumerate(root):
        other = XML.QName(node).localname
        if other in ORDER and ORDER.index(other) > rank:
            root.insert(i, child)
            return
    root.append(child)


def sheets(parts):
    rels = {n.get("Id"): n.get("Target") for n in parse(parts["xl/_rels/workbook.xml.rels"])}
    result = {}
    for node in parse(parts["xl/workbook.xml"]).find(tag("sheets")):
        path = rels[node.get("{" + RID + "}id")]
        result[node.get("name")] = path.lstrip("/") if path.startswith("/") else posixpath.normpath("xl/" + path)
    return result


def merge_styles(original, generated):
    """Append styles; never renumber or replace styles used by original parts."""
    old, new = parse(original), parse(generated)
    mapping = {}
    for group in ("numFmts", "fonts", "fills", "borders", "cellStyleXfs", "cellXfs"):
        existing, source = old.find(tag(group)), new.find(tag(group))
        if source is None:
            continue
        if existing is None:
            existing = XML.Element(tag(group))
            # Match the generated ordering without moving existing styles/extension nodes.
            order = "numFmts fonts fills borders cellStyleXfs cellXfs cellStyles dxfs tableStyles colors extLst".split()
            index = next(
                (
                    i
                    for i, n in enumerate(old)
                    if XML.QName(n).localname in order and order.index(XML.QName(n).localname) > order.index(group)
                ),
                len(old),
            )  # noqa: E501
            old.insert(index, existing)
        lookup = {XML.tostring(n, method="c14n"): i for i, n in enumerate(existing)}
        mapped = {}
        for i, element in enumerate(source):
            candidate = deepcopy(element)
            if group == "numFmts":
                match = next((n for n in existing if n.get("formatCode") == element.get("formatCode")), None)
                if match is None:
                    identifier = max([163] + [int(n.get("numFmtId")) for n in existing]) + 1
                    candidate.set("numFmtId", str(identifier))
                    existing.append(candidate)
                else:
                    identifier = int(match.get("numFmtId"))
                mapped[int(element.get("numFmtId"))] = identifier
                continue
            if group in ("cellStyleXfs", "cellXfs"):
                for key, collection in (
                    ("fontId", "fonts"),
                    ("fillId", "fills"),
                    ("borderId", "borders"),
                    ("xfId", "cellStyleXfs"),
                    ("numFmtId", "numFmts"),
                ):
                    if key in candidate.attrib:
                        current = int(candidate.get(key))
                        candidate.set(key, str(mapping.get(collection, {}).get(current, current)))
            key = XML.tostring(candidate, method="c14n")
            if key not in lookup:
                lookup[key] = len(existing)
                existing.append(candidate)
            mapped[i] = lookup[key]
        existing.set("count", str(len(existing)))
        mapping[group] = mapped
    return encode(old), mapping["cellXfs"]


def preserve(original_bytes, rendered_bytes, actions, rectangle):
    with zipfile.ZipFile(io.BytesIO(original_bytes)) as z:
        original = {n: z.read(n) for n in z.namelist()}
    with zipfile.ZipFile(io.BytesIO(rendered_bytes)) as z:
        rendered = {n: z.read(n) for n in z.namelist()}
    output = original.copy()
    output["xl/styles.xml"], styles = merge_styles(original["xl/styles.xml"], rendered["xl/styles.xml"])
    paths, generated_paths = sheets(original), sheets(rendered)
    roots = {}
    generated = {}
    for name in {a["sheet"] for a in actions}:
        generated[name] = parse(rendered[generated_paths[name]])
        if name in paths:
            roots[name] = parse(original[paths[name]])
        else:
            roots[name] = deepcopy(generated[name])
            for cell in roots[name].iter(tag("c")):
                if cell.get("s") is not None:
                    cell.set("s", str(styles[int(cell.get("s"))]))
            index = len(paths) + 1
            path = f"xl/worksheets/dhanz-sheet-{index}.xml"
            while path in output:
                index += 1
                path = f"xl/worksheets/dhanz-sheet-{index}.xml"
            paths[name] = path
            workbook = parse(output["xl/workbook.xml"])
            rels = parse(output["xl/_rels/workbook.xml.rels"])
            identifier = "rIdDhanz" + str(index)
            while any(n.get("Id") == identifier for n in rels):
                identifier += "x"
            XML.SubElement(rels, "{" + REL + "}Relationship", Id=identifier, Type=RID + "/worksheet", Target=path[3:])
            element = deepcopy(
                next(n for n in parse(rendered["xl/workbook.xml"]).find(tag("sheets")) if n.get("name") == name)
            )
            element.set("{" + RID + "}id", identifier)
            element.set("sheetId", str(max(int(n.get("sheetId")) for n in workbook.find(tag("sheets"))) + 1))
            workbook.find(tag("sheets")).append(element)
            types = parse(output["[Content_Types].xml"])
            XML.SubElement(
                types,
                "{" + CT + "}Override",
                PartName="/" + path,
                ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
            )
            output["xl/workbook.xml"] = encode(workbook)
            output["xl/_rels/workbook.xml.rels"] = encode(rels)
            output["[Content_Types].xml"] = encode(types)
    for action in actions:
        name, kind = action["sheet"], action["type"]
        if kind == "add_sheet":
            continue
        target, source = roots[name], generated[name]
        a, b, c, d = rectangle(action.get("range", "A1"))
        rows = target.find(tag("sheetData"))
        source_cells = {n.get("r"): n for n in source.iter(tag("c"))}
        rowmap = {int(n.get("r")): n for n in rows}
        cells = {n.get("r"): n for n in rows.iter(tag("c"))}
        if kind in ("set_cells", "set_formula", "format_range"):
            for y in range(b, d + 1):
                row = rowmap.get(y)
                if row is None:
                    row = XML.Element(tag("row"), r=str(y))
                    # Append now and order once at serialization. Scanning/counting
                    # the XML siblings for every row makes a full-column copy O(n²).
                    rows.append(row)
                    rowmap[y] = row
                for x in range(a, c + 1):
                    from openpyxl.utils import get_column_letter

                    address = get_column_letter(x) + str(y)
                    old = cells.get(address)
                    new = source_cells.get(address)
                    if new is None:
                        if kind in ("set_cells", "set_formula") and old is not None:
                            for child in list(old):
                                if child.tag in (tag("v"), tag("f"), tag("is")):
                                    old.remove(child)
                            old.attrib.pop("t", None)
                        continue
                    if old is None:
                        old = XML.Element(tag("c"), r=address)
                        index = next(
                            (
                                i
                                for i, n in enumerate(row)
                                if n.tag == tag("c") and coordinate_to_tuple(n.get("r"))[1] > x
                            ),
                            len(row),
                        )
                        row.insert(index, old)
                        cells[address] = old
                    if "s" in new.attrib:
                        old.set("s", str(styles[int(new.get("s"))]))
                    else:
                        old.attrib.pop("s", None)
                    if kind in ("set_cells", "set_formula"):
                        for child in list(old):
                            if child.tag in (tag("v"), tag("f"), tag("is")):
                                old.remove(child)
                        old.attrib.pop("t", None)
                        if new.get("t"):
                            old.set("t", new.get("t"))
                        for child in new:
                            if child.tag in (tag("v"), tag("f"), tag("is")):
                                old.append(deepcopy(child))
            options = action.get("format", {}) if kind == "format_range" else {}
            if "row_height" in options:
                for y in range(b, d + 1):
                    rowmap[y].set("ht", str(options["row_height"]))
                    rowmap[y].set("customHeight", "1")
            if "column_width" in options:
                cols = target.find(tag("cols"))
                if cols is None:
                    cols = XML.Element(tag("cols"))
                    insert(target, cols)
                before = list(cols)
                for node in before:
                    low, high = int(node.get("min")), int(node.get("max"))
                    if low > c or high < a:
                        continue
                    cols.remove(node)
                    for left, right in ((low, min(high, a - 1)), (max(low, c + 1), high)):
                        if left <= right:
                            item = deepcopy(node)
                            item.set("min", str(left))
                            item.set("max", str(right))
                            cols.append(item)
                for x in range(a, c + 1):
                    match = next((n for n in before if int(n.get("min")) <= x <= int(n.get("max"))), None)
                    node = deepcopy(match) if match is not None else XML.Element(tag("col"))
                    node.set("min", str(x))
                    node.set("max", str(x))
                    node.set("width", str(options["column_width"]))
                    node.set("customWidth", "1")
                    cols.append(node)
                cols[:] = sorted(cols, key=lambda n: int(n.get("min")))
        elif kind == "freeze_panes":
            old = target.find(tag("sheetViews"))
            new = source.find(tag("sheetViews"))
            if old is not None:
                target.remove(old)
            if new is not None:
                insert(target, deepcopy(new))
        elif kind == "auto_filter":
            old = target.find(tag("autoFilter"))
            if old is not None:
                target.remove(old)
            new = source.find(tag("autoFilter"))
            if new is not None:
                insert(target, deepcopy(new))
        dimension = target.find(tag("dimension"))
        new = source.find(tag("dimension"))
        if dimension is not None and new is not None:
            dimension.set("ref", new.get("ref"))
    for name, root in roots.items():
        data = root.find(tag("sheetData"))
        data[:] = sorted(data, key=lambda row: int(row.get("r")))
        output[paths[name]] = encode(root)
    workbook = parse(output["xl/workbook.xml"])
    calc = workbook.find(tag("calcPr"))
    if calc is None:
        calc = XML.SubElement(workbook, tag("calcPr"))
    calc.set("calcMode", "auto")
    calc.set("fullCalcOnLoad", "1")
    calc.set("forceFullCalc", "1")
    output["xl/workbook.xml"] = encode(workbook)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in output.items():
            z.writestr(name, data)
    return stream.getvalue()
