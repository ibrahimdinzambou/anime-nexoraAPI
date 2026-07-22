"""HTTP API for the anime-sama client.

The API deliberately delegates scraping and parsing to the existing async
client, so the CLI and the HTTP interface always expose the same data.
"""

from __future__ import annotations

import asyncio
import os
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar
from urllib.parse import unquote

from flask import Flask, jsonify, render_template, request
from httpx import HTTPError

from .catalogue import Catalogue
from .episode import Episode
from .season import Season
from .top_level import AnimeSama

T = TypeVar("T")


def _run(operation: Callable[[AnimeSama], Awaitable[T]], site_url: str) -> T:
    async def execute() -> T:
        api = AnimeSama(site_url)
        try:
            return await operation(api)
        finally:
            await api.client.aclose()

    return asyncio.run(execute())


def _catalogue_json(catalogue: Catalogue) -> dict[str, Any]:
    return {
        "url": catalogue.url,
        "name": catalogue.name,
        "alternative_names": list(catalogue.alternative_names),
        "genres": list(catalogue.genres),
        "categories": sorted(catalogue.categories),
        "languages": sorted(catalogue.languages),
        "image_url": catalogue.image_url,
    }


def _season_json(season: Season) -> dict[str, str]:
    return {"url": season.url, "name": season.name, "serie_name": season.serie_name}


def _episode_json(episode: Episode) -> dict[str, Any]:
    return {
        "index": episode.index,
        "name": episode.name,
        "long_name": episode.long_name,
        "short_name": episode.short_name,
        "season_name": episode.season_name,
        "serie_name": episode.serie_name,
        "languages": {
            language: [player for players in language_players for player in players]
            for language, language_players in episode.languages.availables.items()
        },
    }


def _slug_to_catalogue(api: AnimeSama, slug: str) -> Catalogue:
    # The route accepts a catalogue slug, e.g. "one-piece".
    # Full URLs are intentionally rejected to avoid turning this API into a
    # generic server-side request proxy.
    clean_slug = unquote(slug).strip("/")
    if clean_slug.startswith("catalogue/"):
        clean_slug = clean_slug.removeprefix("catalogue/")
    if not clean_slug or clean_slug.startswith(("http:", "https:")):
        raise ValueError("slug de catalogue invalide")
    return Catalogue(api.site_url.rstrip("/") + "/catalogue/" + clean_slug + "/", client=api.client)


def create_app() -> Flask:
    app = Flask(__name__, static_folder="web/static", template_folder="web/templates")
    site_url = os.getenv("ANIME_SAMA_SITE_URL", "https://anime-sama.to/")
    if not site_url.endswith("/"):
        site_url += "/"

    def endpoint_errors(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return view(*args, **kwargs)
            except ValueError as exc:
                return jsonify(error=str(exc)), 400
            except HTTPError as exc:
                return jsonify(error="anime-sama est inaccessible", details=str(exc)), 502
            except Exception:
                app.logger.exception("API request failed")
                return jsonify(error="erreur interne"), 500
        return wrapped

    @app.get("/health")
    def health() -> Any:
        return jsonify(status="ok", service="anime-sama-api")

    @app.get("/")
    def player() -> str:
        return render_template("index.html")

    @app.get("/api/v1/search")
    @endpoint_errors
    def search() -> Any:
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify(error="Le paramètre q est requis"), 400
        result = _run(lambda api: api.search(query), site_url)
        return jsonify(data=[_catalogue_json(item) for item in result], count=len(result))

    @app.get("/api/v1/catalogues")
    @endpoint_errors
    def catalogues() -> Any:
        query = request.args.get("q", "").strip()
        page = max(request.args.get("page", 1, type=int), 1)
        limit = min(max(request.args.get("limit", 24, type=int), 1), 100)
        result = _run(lambda api: api.search(query), site_url)
        start = (page - 1) * limit
        selected = result[start : start + limit]
        return jsonify(data=[_catalogue_json(item) for item in selected], count=len(result), page=page, limit=limit)

    @app.get("/api/v1/planning")
    @endpoint_errors
    def planning() -> Any:
        days = _run(lambda api: api.planning(), site_url)
        return jsonify(data=[{"day_name": day.day_name, "date": day.date, "entries": [entry.__dict__ for entry in day.entries]} for day in days])

    @app.get("/api/v1/new-episodes")
    @endpoint_errors
    def new_episodes() -> Any:
        releases = _run(lambda api: api.new_episodes(), site_url)
        return jsonify(data=[{
            "page_url": release.page_url, "image_url": release.image_url,
            "serie_name": release.serie_name, "categories": list(release.categories),
            "language": release.language, "descriptive": release.descriptive,
        } for release in releases])

    @app.get("/api/v1/catalogue/<slug>")
    @endpoint_errors
    def catalogue_details(slug: str) -> Any:
        async def operation(api: AnimeSama) -> dict[str, Any]:
            catalogue = _slug_to_catalogue(api, slug)
            result = _catalogue_json(catalogue)
            result.update({"synopsis": await catalogue.synopsis(), "advancement": await catalogue.advancement(), "correspondence": await catalogue.correspondence(), "is_mature": await catalogue.is_mature()})
            return result
        return jsonify(data=_run(operation, site_url))

    @app.get("/api/v1/catalogue/<slug>/seasons")
    @endpoint_errors
    def seasons(slug: str) -> Any:
        async def operation(api: AnimeSama) -> list[dict[str, str]]:
            return [_season_json(item) for item in await _slug_to_catalogue(api, slug).seasons()]
        return jsonify(data=_run(operation, site_url))

    @app.get("/api/v1/catalogue/<slug>/seasons/<season>/episodes")
    @endpoint_errors
    def episodes(slug: str, season: str) -> Any:
        async def operation(api: AnimeSama) -> list[dict[str, Any]]:
            catalogue = _slug_to_catalogue(api, slug)
            season_obj = Season(catalogue.url + unquote(season).strip("/") + "/", serie_name=catalogue.name, client=api.client)
            return [_episode_json(item) for item in await season_obj.episodes()]
        return jsonify(data=_run(operation, site_url))

    return app


app = create_app()


def main() -> None:
    app.run(host=os.getenv("FLASK_HOST", "0.0.0.0"), port=int(os.getenv("PORT", "5000")))


if __name__ == "__main__":
    main()
