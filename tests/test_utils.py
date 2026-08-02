from anime_sama_api.episode import Players
from anime_sama_api.network_guard import safe_redirect_location
from anime_sama_api.utils import remove_some_js_comments, split_and_strip, zip_varlen


def test_zip_varlen():
    data = [(11, 12, 13), (21, 22, 23, 24), (31, 32), (41, 42, 43, 44)]
    expected = [[11, 21, 31, 41], [12, 22, 32, 42], [13, 23, 43], [24, 44]]
    assert zip_varlen(*data) == expected


def test_split_and_strip():
    data = "some\t \ngood\r\f\v\ntext"
    assert split_and_strip(data, (" ", "\r")) == ["some", "good", "text"]


def test_remove_some_js_comments():
    # assert remove_some_js_comments("<p>Hello</p> // end of line\nNew"), "<p>Hello</p> \nNew"
    assert remove_some_js_comments("<p>Hello</p> /* end of line\nNew */"), (
        "<p>Hello</p>"
    )
    assert remove_some_js_comments("<!-- <p>Hello</p> -->\nNew"), "\nNew"


def test_players_filters_ad_and_unknown_redirect_hosts():
    players = Players([
        "https://vidmoly.to/embed-abc",
        "https://ads.example/redirect",
        "https://unknown-player.example/embed",
        "javascript:alert(1)",
    ])

    assert players == ["https://vidmoly.net/embed-abc"]


def test_safe_redirect_location_keeps_anime_sama_only():
    assert safe_redirect_location("/catalogue/one-piece", "https://anime-sama.to/") == (
        "https://anime-sama.to/catalogue/one-piece"
    )
    assert safe_redirect_location("https://tracker.example/out", "https://anime-sama.to/") is None
