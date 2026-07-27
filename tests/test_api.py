from types import SimpleNamespace

import pytest

from anime_sama_api.api import _catalogue_page


def catalogue(index: int):
    return SimpleNamespace(
        url=f"https://anime-sama.to/catalogue/anime-{index}/",
        name=f"Anime {index}",
        alternative_names=(),
        genres=(),
        categories=set(),
        languages=set(),
        image_url=f"https://img.example/{index}.jpg",
    )


class FakeAnimeSama:
    def __init__(self, count: int):
        self.count = count
        self.yielded = 0

    async def search_iter(self, query: str):
        for index in range(self.count):
            self.yielded += 1
            yield catalogue(index)


@pytest.mark.asyncio
async def test_catalogue_page_stops_after_requested_window():
    api = FakeAnimeSama(200)

    payload = await _catalogue_page(api, "", page=1, limit=48)

    assert len(payload["data"]) == 48
    assert payload["limit"] == 48
    assert payload["has_more"] is True
    assert api.yielded == 48


@pytest.mark.asyncio
async def test_catalogue_page_skips_previous_window():
    api = FakeAnimeSama(30)

    payload = await _catalogue_page(api, "", page=2, limit=10)

    assert [item["name"] for item in payload["data"]] == [
        f"Anime {index}" for index in range(10, 20)
    ]
    assert api.yielded == 20
