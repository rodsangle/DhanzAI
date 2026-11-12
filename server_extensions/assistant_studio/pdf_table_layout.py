"""Read ruled apprentice-training forms by physical row bands and header columns."""

import bisect
import csv
import io
import re
import statistics

LABELS = ["Apprentice Name", "Apprentice Level", "Signature", "Date", "Hours"]


def words(tsv):
    result = []
    for item in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        if item.get("level") != "5" or not (item.get("text") or "").strip():
            continue
        try:
            result.append(
                {
                    "text": item["text"].strip(),
                    "x": float(item["left"]),
                    "y": float(item["top"]),
                    "w": float(item["width"]),
                    "h": float(item["height"]),
                    "confidence": float(item["conf"]),
                }
            )
        except (KeyError, ValueError):
            continue
    return result


def _ruled_geometry(image_path, tsv):
    from PIL import Image, ImageChops

    with Image.open(image_path) as source:
        gray = source.convert("L")
    width, height = gray.size
    # Expand thin/slightly sloping rules; long page-wide strokes remain distinct
    # from handwriting. Projection uses C-backed Pillow operations, no GPU.
    expanded = gray
    for offset in (-4, -3, -2, -1, 1, 2, 3, 4):
        expanded = ImageChops.darker(expanded, ImageChops.offset(gray, 0, offset))
    left, right = round(width * 0.01), round(width * 0.985)
    threshold = (right - left) * 0.65
    groups = []
    for y in range(height):
        count = sum(expanded.crop((left, y, right, y + 1)).histogram()[:150])
        if count >= threshold:
            if not groups or y > groups[-1][-1] + 2:
                groups.append([y])
            else:
                groups[-1].append(y)
    text = words(tsv)
    header = [
        w
        for w in text
        if re.sub("[^a-z]", "", w["text"].lower()) in {"name", "level", "signature"} and w["y"] < height * 0.4
    ]
    if len(header) < 2:
        return None
    candidates = []
    for group in groups:
        matching = [w for w in header if group[0] <= w["y"] + w["h"] / 2 <= group[-1]]
        if len(matching) >= 2 and 12 <= len(group) <= height * 0.08:
            candidates.append(group)
    if not candidates:
        return roster_geometry(gray, text)
    band = max(candidates, key=lambda group: sum(group[0] <= w["y"] + w["h"] / 2 <= group[-1] for w in header))
    centers = [statistics.mean(g) for g in groups if g[0] > band[-1] + 6 and len(g) < height * 0.025]
    if len(centers) < 5:
        return roster_geometry(gray, text)
    gaps = [b - a for a, b in zip(centers, centers[1:], strict=False) if 12 < (b - a) < height * 0.1]
    if not gaps:
        return None
    pitch = statistics.median(gaps)
    if sum(abs(gap - pitch) < pitch * 0.25 for gap in gaps) < len(gaps) * 0.7:
        return None
    # The lower edge of the colored header is the first data-row boundary.
    first = centers[0] - pitch
    edges = [first] + centers
    if first < band[0] or first > band[-1] + pitch * 0.3:
        return None
    center = round(statistics.mean(band))
    pixels = list(gray.crop((0, center, width, center + 1)).getdata())
    dark = [x for x, value in enumerate(pixels) if value < 150]
    if not dark:
        return None
    x0, x1 = min(dark), max(dark) + 1
    if x1 - x0 < width * 0.65:
        return None
    return {
        "header_top": max(0, band[0]),
        "header_bottom": min(height, band[-1] + 1),
        "left": x0,
        "right": x1,
        "rows": edges,
        "width": width,
        "height": height,
    }


def columns(header_tsv, shape):
    if shape.get("roster_columns"):
        bounds = shape["roster_columns"].copy()
        date = [w for w in words(header_tsv) if w["text"].lower().strip(".:") == "date"]
        if len(date) == 1:
            bounds[3] = shape["left"] + date[0]["x"] - 12
        return bounds
    tokens = words(header_tsv)
    if sum("apprentice" in w["text"].lower() for w in tokens) < 2:
        return None
    names = ["name", "level", "signature", "date", "hours"]
    found = []
    for name in names:
        matches = [w for w in tokens if re.sub("[^a-z]", "", w["text"].lower()).endswith(name)]
        if len(matches) != 1:
            return None
        item = matches[0]
        start = item["x"]
        end = item["x"] + item["w"]
        if name in ("name", "level"):
            preceding = [w for w in tokens if "apprentice" in w["text"].lower() and 0 < start - (w["x"] + w["w"]) < 40]
            if preceding:
                start = max(preceding, key=lambda w: w["x"])["x"]
        found.append(shape["left"] + (start + end) / 2)
    if found != sorted(found):
        return None
    return [shape["left"]] + [(a + b) / 2 for a, b in zip(found, found[1:], strict=False)] + [shape["right"]]


def extract_rows(image_path, tsv, shape, x_edges):
    from PIL import Image

    with Image.open(image_path) as source:
        gray = source.convert("L")
    edges = shape["rows"]
    assigned = [[[] for _ in LABELS] for _ in range(len(edges) - 1)]
    ambiguous = set()
    for word in words(tsv):
        cx = word["x"] + word["w"] / 2
        col = bisect.bisect_right(x_edges, cx) - 1
        if not 0 <= col < 5:
            continue
        overlaps = [
            max(0, min(word["y"] + word["h"], end) - max(word["y"], start))
            for start, end in zip(edges, edges[1:], strict=False)
        ]
        if not overlaps or max(overlaps) <= 0:
            continue
        row = max(range(len(overlaps)), key=overlaps.__getitem__)
        assigned[row][col].append(word)
        if sum(value > word["h"] * 0.25 for value in overlaps) > 1:
            ambiguous.add((row, col))
    result = []
    for row, fields in enumerate(assigned):
        record = []
        for col, tokens in enumerate(fields):
            tolerance = max(3, statistics.median(w["h"] for w in tokens) * 0.5) if tokens else 3
            lines = []
            for word in sorted(tokens, key=lambda w: (w["y"] + w["h"] / 2, w["x"])):
                center = word["y"] + word["h"] / 2
                if not lines or abs(center - lines[-1][0]) > tolerance:
                    lines.append((center, [word]))
                else:
                    lines[-1][1].append(word)
            value = " ".join(" ".join(w["text"] for w in sorted(line, key=lambda w: w["x"])) for _, line in lines)
            confidence = min((w["confidence"] for w in tokens), default=None)
            x0, x1 = x_edges[col], x_edges[col + 1]
            y0, y1 = edges[row], edges[row + 1]
            if x1 <= x0:
                record.append(
                    {
                        "column": col,
                        "text": "",
                        "confidence": None,
                        "source_row": row + 1,
                        "review_note": "Date is page-level metadata on this roster.",
                    }
                )
                continue
            crop = gray.crop(
                (
                    max(0, round(x0 + 4)),
                    max(0, round(y0 + 7)),
                    min(gray.width, round(x1 - 4)),
                    min(gray.height, round(y1 - 5)),
                )
            )
            ink = sum(crop.histogram()[:110]) > max(12, crop.width * crop.height * 0.002)
            note = ""
            if not value and ink:
                value = "[Unreadable entry — verify against PDF]"
                confidence = 0
                note = "Ink is present but OCR did not recover readable text. No value was guessed."
            elif col >= 2 and (value or ink):
                note = "Handwritten field: OCR is not verified. Compare with this source row."
            if col == 2 and shape.get("inferred_signature"):
                note += (
                    " Signature heading was obscured; this column position uses the recognized roster layout. Verify."
                )
            if (row, col) in ambiguous:
                note += " The OCR box crosses a printed row boundary; verify its row assignment."
            record.append(
                {"column": col, "text": value, "confidence": confidence, "source_row": row + 1, "review_note": note}
            )
        # Some signatures extend into the level field. Keep the printed level intact
        # and move only explicitly recognized trailing OCR tokens to Signature.
        level = record[1]["text"]
        match = re.match(r"^(.*?\(\s*\d+\s*%\s*\))\s+(.+)$", level)
        if match and "apprentice" in match[1].lower():
            record[1]["text"] = match[1]
            record[2]["text"] = (match[2] + " " + record[2]["text"]).strip()
            record[2]["review_note"] += " OCR text extended left of the signature column; verify the placement."
        result.append(record)
    # Blank template slots at page ends are not data; preserve interior blank rows.
    while result and not any(cell["text"] for cell in result[-1]):
        result.pop()
    return result


def metadata(tsv, top, *, after=False):
    items = [word for word in words(tsv) if (word["y"] > top if after else word["y"] + word["h"] < top)]
    if not items:
        return []
    tolerance = max(4, statistics.median(word["h"] for word in items) * 0.5)
    lines = []
    for word in sorted(items, key=lambda w: (w["y"] + w["h"] / 2, w["x"])):
        center = word["y"] + word["h"] / 2
        if not lines or abs(center - lines[-1][0]) > tolerance:
            lines.append((center, [word]))
        else:
            lines[-1][1].append(word)
    return [" ".join(word["text"] for word in sorted(line, key=lambda w: w["x"])) for _, line in lines]


def roster_geometry(gray, text):
    """Four-field roster: printed level baselines define rows, not signature ink."""
    width, height = gray.size
    headers = {}
    for name in ("name", "level", "signature", "hours"):
        hits = [w for w in text if w["y"] < height * 0.22 and re.sub("[^a-z]", "", w["text"].lower()) == name]
        if not hits:
            if name == "signature":
                continue
            return None
        headers[name] = min(hits, key=lambda word: word["y"])
    inferred_signature = "signature" not in headers
    if inferred_signature:
        if not any(w["text"].lower() == "roster" and w["y"] < height * 0.2 for w in text):
            return None
        headers["signature"] = {
            "x": (headers["level"]["x"] + headers["hours"]["x"]) / 2,
            "y": headers["level"]["y"],
            "w": 0,
            "h": headers["level"]["h"],
        }
    if max(w["y"] for w in headers.values()) - min(w["y"] for w in headers.values()) > height * 0.025:
        return None
    top = min(w["y"] for w in headers.values())
    bottom = max(w["y"] + w["h"] for w in headers.values())
    levels = [
        w
        for w in text
        if w["y"] > bottom + 4
        and w["x"] < headers["signature"]["x"]
        and re.sub("[^a-z]", "", w["text"].lower()) == "pipefitter"
    ]
    centers = sorted(w["y"] + w["h"] / 2 for w in levels)
    if len(centers) < 5:
        return None
    initial_pitch = statistics.median(b - a for a, b in zip(centers, centers[1:], strict=False))
    left_words = [
        w
        for w in text
        if w["x"] < min(item["x"] for item in levels) - 12
        and bottom + 4 < w["y"] < centers[-1] + initial_pitch * 0.5
        and len(re.sub("[^A-Z]", "", w["text"])) >= 2
        and w["text"] == w["text"].upper()
    ]
    name_centers = []
    for word in sorted(left_words, key=lambda w: w["y"] + w["h"] / 2):
        center = word["y"] + word["h"] / 2
        if not name_centers or center - name_centers[-1] > max(5, word["h"] * 0.6):
            name_centers.append(center)
    if len(name_centers) >= len(centers):
        centers = name_centers
    gaps = [b - a for a, b in zip(centers, centers[1:], strict=False)]
    pitch = statistics.median(gaps)
    if not all(abs(g - pitch) < pitch * 0.2 for g in gaps):
        return None
    # A missing OCR baseline would double a gap and reject this layout.
    edges = [centers[0] - pitch / 2] + [(a + b) / 2 for a, b in zip(centers, centers[1:], strict=False)]
    edges.append(centers[-1] + pitch / 2)
    boundaries = [min(w["x"] for w in levels) - 12, headers["signature"]["x"] - 12, headers["hours"]["x"] - 12]
    left = width * 0.01
    date_hits = [
        w
        for w in text
        if re.sub("[^a-z]", "", w["text"].lower()) == "date"
        and abs(w["y"] - top) < max(10, height * 0.012)
        and headers["signature"]["x"] < w["x"] < headers["hours"]["x"]
    ]
    date_edge = min(date_hits, key=lambda w: w["y"])["x"] - 12 if date_hits else boundaries[2]
    # Normalize this roster to the workbook's five columns: Date is intentionally
    # empty because its date is page-level metadata, never inferred per person.
    return {
        "header_top": int(top - 3),
        "header_bottom": int(bottom + 3),
        "left": int(left),
        "right": int(width * 0.985),
        "rows": edges,
        "width": width,
        "height": height,
        "roster_columns": [left, *boundaries[:2], date_edge, boundaries[2], width * 0.985],
        "inferred_signature": inferred_signature,
    }


def geometry(image_path, tsv):
    result = _ruled_geometry(image_path, tsv)
    if result:
        return result
    from PIL import Image

    with Image.open(image_path) as image:
        return roster_geometry(image.convert("L"), words(tsv))
