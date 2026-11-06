import pytest

from app.assistant_studio.website_tools import destination, install


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Sortly", "https://www.sortly.com/"),
        ("sortly.com", "https://sortly.com"),
        ("https://github.com/owner/repo", "https://github.com/owner/repo"),
    ],
)
def test_websites(value, expected):
    assert destination(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "http://sortly.com",
        "https://user:password@sortly.com",
        "unknownservice",
        "https://sortly.com:8443",
        "https://sortly.com\\evil",
    ],
)
def test_invalid_or_unknown(value):
    with pytest.raises(ValueError):
        destination(value)


@pytest.mark.asyncio
async def test_button_is_prepared_not_claimed_open():
    from app.services import assistant_tools as tools

    install()
    result = await tools.TOOLS["open_website"].run(None, {"website": "Sortly"})
    assert result.data["opened"] is False
    assert result.action == {"type": "open_website", "url": "https://www.sortly.com/"}
