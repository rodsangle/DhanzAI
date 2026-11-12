import io
import json
from types import SimpleNamespace

import httpx
import pytest
from openpyxl import load_workbook
from PIL import Image, ImageDraw

from app.assistant_studio.pdf_excel import Cell, Page, workbook
from app.assistant_studio.pdf_handwriting import apply, apply_response
from app.assistant_studio.pdf_table_layout import LABELS, columns, extract_rows, geometry


def tsv(items):
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    return header + "".join(
        f"5\t1\t1\t1\t1\t1\t{x}\t{y}\t{w}\t{h}\t{conf}\t{text}\n" for text, x, y, w, h, conf in items
    )


def test_rule_rows_keep_crossing_handwriting_in_cells(tmp_path):
    image = Image.new("RGB", (900, 800), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((15, 60, 885, 100), fill=(10, 90, 140))
    for y in range(100, 431, 30):
        draw.line((15, y, 885, y), fill=(20, 100, 150), width=2)
    draw.text((30, 112), "ALPHA", fill="black")
    draw.text((500, 109), "Signature", fill="black")
    path = tmp_path / "form.png"
    image.save(path)
    header = [
        ("Apprentice", 50, 78, 70, 14, 99),
        ("Name", 125, 78, 35, 14, 99),
        ("Apprentice", 260, 78, 70, 14, 99),
        ("Level", 340, 78, 35, 14, 99),
        ("Signature", 490, 78, 80, 14, 99),
        ("Date", 705, 78, 35, 14, 99),
        ("Hours", 810, 78, 40, 14, 99),
    ]
    data = tsv(
        header
        + [
            ("ALPHA", 30, 112, 70, 14, 95),
            ("Level 1", 250, 113, 100, 14, 95),
            ("Crossing", 500, 105, 70, 37, 60),
            ("9/18", 710, 112, 35, 15, 55),
            ("3", 820, 112, 15, 15, 80),
        ]
    )
    shape = geometry(path, data)
    assert shape is not None
    cropped = [(text, x - shape["left"], y - shape["header_top"], w, h, conf) for text, x, y, w, h, conf in header]
    bounds = columns(tsv(cropped), shape)
    assert len(bounds) == 6
    rows = extract_rows(path, data, shape, bounds)
    assert rows[0][0]["text"] == "ALPHA"
    assert rows[0][2]["text"] == "Crossing" and rows[0][3]["text"] == "9/18" and rows[0][4]["text"] == "3"
    assert rows[0][2]["review_note"]
    assert all(len(row) == 5 for row in rows)


def sample():
    rows = [[Cell(i, label) for i, label in enumerate(LABELS)]]
    rows.append(
        [
            Cell(0, "Printed name", 99, 1),
            Cell(1, "Printed level", 99, 1),
            Cell(2, "OCR?", 20, 1),
            Cell(3, "9/?", 20, 1),
            Cell(4, "?", 10, 1),
        ]
    )
    return Page(1, rows, True, LABELS.copy(), {"status": "not_requested"}, b"PNG")


def test_grid_mapping_does_not_guess_new_columns():
    page = sample()
    result, _ = workbook([("form.pdf", [page])])
    sheet = load_workbook(io.BytesIO(result)).active
    assert sheet.max_column == 5
    assert [sheet.cell(2, i).value for i in range(1, 6)] == ["Printed name", "Printed level", "OCR?", "9/?", "?"]
    assert "Printed table row 1" in sheet["D2"].comment.text


def test_bad_vision_row_ids_cannot_shift_or_partially_update_data():
    page = sample()
    with pytest.raises(ValueError):
        apply_response(
            page, json.dumps({"rows": [{"row": 2, "signature": "Other", "date": "9/18", "hours": "3", "unclear": []}]})
        )
    assert page.rows[1][2].text == "OCR?"


@pytest.mark.asyncio
async def test_vision_uses_numbered_rows_without_changing_printed_fields():
    calls = []

    async def response(request):
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "rows": [
                                        {
                                            "row": 1,
                                            "signature": None,
                                            "date": "9/18",
                                            "hours": "3",
                                            "unclear": ["signature"],
                                        }
                                    ]
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20},
            },
        )

    page = sample()
    settings = SimpleNamespace(
        openai_api_key="fake-test-key", openai_models="gpt-4.1-mini", openai_base_url="https://api.openai.com/v1"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        used = await apply([page], settings, client=client)
    assert used == 1 and len(calls) == 1
    assert "tools" not in calls[0]
    assert page.rows[1][0].text == "Printed name" and page.rows[1][1].text == "Printed level"
    assert page.rows[1][3].text == "9/18" and page.rows[1][4].text == "3"
    assert "could not confirm" in page.rows[1][2].review_note
    assert page.vision["status"] == "complete" and page.vision["input_tokens"] == 100
    assert page.vision_input is None


@pytest.mark.asyncio
async def test_provider_error_is_not_retried_and_preserves_local_values():
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"code": "insufficient_quota"}})

    page = sample()
    settings = SimpleNamespace(
        openai_api_key="fake-test-key", openai_models="gpt-4.1-mini", openai_base_url="https://api.openai.com/v1"
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
        await apply([page], settings, client=client)
    assert len(calls) == 1 and page.vision["status"] == "provider_http_429"
    assert page.rows[1][3].text == "9/?"


def test_invalid_late_record_does_not_mutate_earlier_rows():
    page = sample()
    second = [Cell(i, "second", 80, 2) for i in range(5)]
    page.rows.append(second)
    records = [
        {"row": 1, "signature": "changed", "date": "9/18", "hours": "3", "unclear": []},
        {"row": 2, "signature": "changed", "date": "9/18", "hours": 3, "unclear": []},
    ]
    with pytest.raises(ValueError):
        apply_response(page, json.dumps({"rows": records}))
    assert page.rows[1][2].text == "OCR?"


@pytest.mark.asyncio
async def test_no_key_or_exhausted_budget_makes_no_provider_call():
    def unexpected(request):
        raise AssertionError("Provider must not be called")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected)) as client:
        page = sample()
        assert await apply([page], SimpleNamespace(openai_api_key=None), client=client) == 0
        assert page.vision["status"] == "openai_key_unavailable"
        page = sample()
        assert await apply([page], SimpleNamespace(openai_api_key="fake"), budget=0, client=client) == 0
        assert page.vision["status"] == "vision_page_limit_reached"


def test_roster_without_date_column_uses_printed_baselines(tmp_path):
    from app.assistant_studio.pdf_table_layout import roster_geometry

    image = Image.new("L", (900, 700), 255)
    header = [
        ("Name", 120, 60, 35, 14, 99),
        ("Level", 350, 60, 35, 14, 99),
        ("Signature", 540, 60, 75, 14, 99),
        ("Hours", 760, 60, 40, 14, 99),
    ]
    items = header + [
        item
        for i in range(6)
        for item in [
            ("NAME", 60, 100 + i * 30, 80, 14, 99),
            ("Pipefitter", 290, 100 + i * 30, 65, 14, 99),
            ("3", 770, 100 + i * 30, 15, 14, 99),
        ]
    ]
    from app.assistant_studio.pdf_table_layout import words

    shape = roster_geometry(image, words(tsv(items)))
    assert shape and len(shape["rows"]) == 7
    path = tmp_path / "roster.png"
    image.save(path)
    rows = extract_rows(path, tsv(items), shape, shape["roster_columns"])
    assert len(rows) == 6
    assert rows[0][0]["text"] == "NAME"
    assert rows[0][3]["text"] == "" and rows[0][4]["text"] == "3"


def test_vision_cannot_add_per_person_date_on_shared_date_roster():
    page = sample()
    page.rows[1][3].text = ""
    page.rows[1][3].review_note = "Date is page-level metadata on this roster."
    apply_response(
        page,
        json.dumps(
            {"rows": [{"row": 1, "signature": None, "date": "invented", "hours": "3", "unclear": ["signature"]}]}
        ),
    )
    assert page.rows[1][3].text == ""
