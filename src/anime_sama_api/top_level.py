import asyncio
import logging
import re
from collections.abc import AsyncIterator, Generator
from dataclasses import dataclass
from html import unescape
from typing import Any, cast

from httpx import AsyncClient

from .catalogue import Catalogue, Category
from .episode import Episode
from .langs import Lang, flags
from .network_guard import safe_redirect_location
from .utils import filter_literal, is_Literal

logger = logging.getLogger(__name__)


async def find_site_url(
    client: AsyncClient | None = None, provider_url="https://anime-sama.pw/"
) -> str | None:
    client = client or AsyncClient()

    response = await client.get(provider_url)

    if response.is_error:
        return None

    # * Sometimes need to check for the great word "anime-sama" in lowercase or uppercase but if add re.IGNORECASE it will work
    match = re.search(
        r"href=\"(.+?)\">Accéder à Anime-Sama", response.text, re.IGNORECASE
    )

    # * Ajouter un suive de redirection d'url au match au cas ou le site n'est pas a jour et redirige vers une autre url, puis garder l'url finale

    if match:
        redirected = await client.get(match.group(1), follow_redirects=False)
        if redirected.has_redirect_location:
            location = safe_redirect_location(
                redirected.headers.get("location", ""), match.group(1)
            )
            return location.rstrip("/") + "/" if location else None
        return match.group(1)


@dataclass(frozen=True)
class PlanningEntry:
    """Une entrée du planning (anime ou scan) avec titre, type, heure et langue."""

    title: str
    kind: str  # "Anime" | "Scans"
    time: str  # ex. "15h00" ou ""
    lang: str  # "VOSTFR" | "VF" | "VJ"
    url: str

    def display_line(self) -> str:
        time_part = f" {self.time}" if self.time else ""
        return f"{self.title} — {self.kind} {self.lang}{time_part}"


@dataclass(frozen=True)
class PlanningDay:
    """Un jour du planning avec sa date et la liste des sorties."""

    day_name: str  # Lundi, Mardi, ...
    date: str  # ex. "02/03"
    entries: tuple[PlanningEntry, ...]


@dataclass(frozen=True)
class EpisodeRelease:
    page_url: str
    image_url: str
    serie_name: str
    categories: tuple[Category]
    language: Lang
    descriptive: str

    def get_real_episodes(self) -> list[Episode]:
        raise NotImplementedError

    @property
    def fancy_name(self) -> str:
        return f"{self.serie_name} - {self.descriptive} {flags.get(self.language, '')}"


class AnimeSama:
    def __init__(self, site_url: str, client: AsyncClient | None = None) -> None:
        self.site_url = site_url
        self.client = client or AsyncClient()

    async def _get_homepage_section(self, section_name: str, how_many: int = 1) -> str:
        homepage = await self.client.get(self.site_url)

        if homepage.is_error:
            return ""

        sections = homepage.text.split("<!--")
        for index, section in enumerate(sections):
            comment_end_pos = section.find("-->")
            if section_name in section[:comment_end_pos]:
                return "<!--" + "<!--".join(sections[index : index + how_many])

        return ""

    def _yield_catalogues_from(self, html: str) -> Generator[Catalogue]:
        text_without_script = re.sub(r"<script[\W\w]+?</script>", "", html)
        for card_match in re.finditer(
            r'<div[^>]*class="[^"]*catalog-card[^"]*"[^>]*>[\s\S]*?</a>\s*</div>',
            text_without_script,
            re.IGNORECASE,
        ):
            card_html = card_match.group()

            url_m = re.search(r'href="([^"]+)"', card_html)
            if not url_m:
                continue
            url = unescape(url_m.group(1))

            image_m = re.search(r'src="([^"]+)"', card_html)
            image_url = unescape(image_m.group(1)) if image_m else ""

            name_m = re.search(r'card-title[^>]*>(.*?)</h2>', card_html, re.IGNORECASE)
            name = unescape(name_m.group(1).strip()) if name_m else ""

            alt_m = re.search(
                r'alternate-titles[^>]*>(.*?)</p>', card_html, re.IGNORECASE
            )
            alt_names_raw = unescape(alt_m.group(1)) if alt_m else ""
            alternative_names = (
                [a.strip() for a in alt_names_raw.split(",") if a.strip()]
                if alt_names_raw
                else []
            )

            genres: list[str] = []
            genre_rows = re.findall(
                r'<div class="info-row">[\s\S]*?</div>\s*</div>', card_html
            )
            for row in genre_rows:
                label_m = re.search(
                    r'info-label[^>]*>[\s\S]*?Genres[\s\S]*?</span>', row, re.IGNORECASE
                )
                if label_m:
                    genres = [
                        unescape(t.strip())
                        for t in re.findall(
                            r'genre-tag[^>]*>([^<]+)', row
                        )
                        if t.strip()
                    ]
                    break

            categories: list[str] = []
            for row in genre_rows:
                label_m = re.search(
                    r'info-label[^>]*>[\s\S]*?Types?[\s\S]*?</span>',
                    row,
                    re.IGNORECASE,
                )
                if label_m:
                    type_vals = re.findall(r'info-value[^>]*>([^<]+)', row)
                    for val in type_vals:
                        parts = [v.strip() for v in val.split(",") if v.strip()]
                        categories.extend(parts)
                    break

            languages: list[str] = []
            for row in genre_rows:
                label_m = re.search(
                    r'info-label[^>]*>[\s\S]*?Langues[\s\S]*?</span>',
                    row,
                    re.IGNORECASE,
                )
                if label_m:
                    flag_titles = re.findall(r'lang-flag[^>]*title="([^"]+)"', row)
                    for title in flag_titles:
                        lang = self._flag_title_to_lang(title)
                        if lang:
                            languages.append(lang)
                    break

            _category_fix = {"Autre": "Autres", "Animes": "Anime", "Films": "Film"}
            categories = [_category_fix.get(c.strip(), c.strip()) for c in categories if c.strip()]

            def not_in_literal(value: Any) -> None:
                logger.warning(
                    "Erreur lors du parsing de « %s ». Signaler avec l'URL : %s", value, url
                )

            categories_checked = cast(
                set[Category], set(filter_literal(categories, Category, not_in_literal))
            )
            languages_checked = cast(
                set[Lang], set(filter_literal(languages, Lang, lambda _: None))
            )

            yield Catalogue(
                url=url,
                name=name,
                alternative_names=alternative_names,
                genres=genres,
                categories=categories_checked,
                languages=languages_checked,
                image_url=image_url,
                client=self.client,
            )

    @staticmethod
    def _flag_title_to_lang(title: str) -> str | None:
        from .langs import flagid2lang
        return flagid2lang.get(title.strip().lower())

    def _yield_release_episodes_from(self, html: str) -> Generator[EpisodeRelease]:
        for card_match in re.finditer(
            r'<div[^>]*class="[^"]*anime-card-premium[^"]*"[^>]*>[\s\S]*?</a>\s*</div>',
            html,
            re.IGNORECASE,
        ):
            card_html = card_match.group()
            url_m = re.search(r'href="([^"]+)"', card_html)
            if not url_m:
                continue
            season_url = unescape(url_m.group(1))

            image_m = re.search(r'src="([^"]+)"', card_html)
            image_url = unescape(image_m.group(1)) if image_m else ""

            alt_m = re.search(r'alt="([^"]*)"', card_html)
            serie_name = unescape(alt_m.group(1).strip()) if alt_m else ""

            badge_m = re.search(
                r'badge-text[^>]*>([^<]+)', card_html, re.IGNORECASE
            )
            category_raw = unescape(badge_m.group(1).strip()) if badge_m else "Anime"

            lang_m = re.search(
                r'language-badge-top[\s\S]*?badge-text[^>]*>([^<]+)',
                card_html,
                re.IGNORECASE,
            )
            language = unescape(lang_m.group(1).strip()) if lang_m else "VOSTFR"

            info_m = re.search(
                r'info-text[^>]*>([^<]+)', card_html, re.IGNORECASE
            )
            descriptive = unescape(info_m.group(1).strip()) if info_m else ""

            categories = [category_raw]
            _category_fix = {"Autre": "Autres", "Animes": "Anime", "Films": "Film"}
            categories = [_category_fix.get(c.strip(), c.strip()) for c in categories if c.strip()]

            def not_in_literal(value: Any) -> None:
                logger.warning(
                    "Erreur lors du parsing de « %s » (accueil). URL : %s", value, season_url
                )

            categories_checked = cast(
                tuple[Category],
                tuple(filter_literal(categories, Category, not_in_literal)),
            )
            is_Literal(language, Lang, not_in_literal)

            yield EpisodeRelease(
                page_url=season_url,
                image_url=image_url,
                serie_name=serie_name,
                categories=categories_checked,
                language=cast(Lang, language),
                descriptive=descriptive,
            )

    async def search(self, query: str) -> list[Catalogue]:
        response = (
            await self.client.get(f"{self.site_url}catalogue/?search={query}")
        ).raise_for_status()

        pages_regex = re.findall(r"page=(\d+)", response.text)

        if not pages_regex:
            last_page = 1
        else:
            last_page = int(pages_regex[-1])

        responses = [response] + await asyncio.gather(
            *(
                self.client.get(f"{self.site_url}catalogue/?search={query}&page={num}")
                for num in range(2, last_page + 1)
            )
        )

        catalogues = []
        for response in responses:
            if response.is_error:
                continue

            catalogues += list(self._yield_catalogues_from(response.text))

        return catalogues

    async def search_iter(self, query: str) -> AsyncIterator[Catalogue]:
        response = (
            await self.client.get(f"{self.site_url}catalogue/?search={query}")
        ).raise_for_status()

        pages_regex = re.findall(r"page=(\d+)", response.text)

        if not pages_regex:
            return

        last_page = int(pages_regex[-1])

        for catalogue in self._yield_catalogues_from(response.text):
            yield catalogue

        for number in range(2, last_page + 1):
            response = await self.client.get(
                f"{self.site_url}catalogue/?search={query}&page={number}"
            )

            if response.is_error:
                continue

            for catalogue in self._yield_catalogues_from(response.text):
                yield catalogue

    async def catalogues_iter(self) -> AsyncIterator[Catalogue]:
        async for catalogue in self.search_iter(""):
            yield catalogue

    async def all_catalogues(self) -> list[Catalogue]:
        return await self.search("")

    def _parse_planning(self, html: str) -> list[PlanningDay]:
        """Parse la page planning et retourne la liste des jours avec leurs entrées."""
        text = re.sub(r"<script[\W\w]+?</script>", "", html)
        base_url = self.site_url.rstrip("/")
        days_order = (
            "Lundi",
            "Mardi",
            "Mercredi",
            "Jeudi",
            "Vendredi",
            "Samedi",
            "Dimanche",
        )
        result: list[PlanningDay] = []

        # Trouver les sections par jour : <h2 ...>Lundi</h2> etc.
        day_pattern = re.compile(
            r'<h2[^>]*titreJours[^>]*>\s*('
            + "|".join(re.escape(d) for d in days_order)
            + r')\s*</h2>',
            re.IGNORECASE,
        )
        day_matches = list(day_pattern.finditer(text))

        for i, day_match in enumerate(day_matches):
            day_name = day_match.group(1).strip()
            start = day_match.end()
            end = day_matches[i + 1].start() if i + 1 < len(day_matches) else len(text)
            section = text[start:end]

            # Date du jour (DD/MM)
            date_match = re.search(r"(\d{1,2}/\d{1,2})", section)
            date_str = date_match.group(1) if date_match else ""

            # Cartes : uniquement Anime (pas les Scans)
            card_pattern = re.compile(
                r'<div[^>]*\b(Anime|Scans)\s+(VOSTFR|VF|VJ)[^>]*\bplanning-card\b'
                r'[^>]*data-title="([^"]*)"[^>]*>'
                r'[\s\S]*?href="(/catalogue/[^"]+)"'
                r'[\s\S]*?card-title[^>]*>([^<]+)'
                r'(?:[\s\S]*?info-text[^>]*>([^<]+))?',
                re.IGNORECASE,
            )
            entries_list: list[PlanningEntry] = []
            for card in card_pattern.finditer(section):
                kind, lang, _data_title, path, title, time_str = card.groups()
                if (kind or "").strip().lower() != "anime":
                    continue
                title = unescape(title).strip() if title else ""
                time_str = (time_str or "").strip()
                full_url = path if path.startswith("http") else base_url + path
                entries_list.append(
                    PlanningEntry(
                        title=title,
                        kind="Anime",
                        time=time_str,
                        lang=lang or "VOSTFR",
                        url=full_url,
                    )
                )
            result.append(
                PlanningDay(
                    day_name=day_name,
                    date=date_str,
                    entries=tuple(entries_list),
                )
            )
        return result

    async def planning(self) -> list[PlanningDay]:
        """Récupère le planning de la semaine depuis la page planning du site."""
        response = await self.client.get(f"{self.site_url}planning/")
        if response.is_error:
            return []
        return self._parse_planning(response.text)

    async def new_episodes(self) -> list[EpisodeRelease]:
        """
        Return the new available episodes on anime-sama using the homepage sorted from oldest to newest.
        """
        section = await self._get_homepage_section("ajouts animes", 4)
        release_episodes = list(self._yield_release_episodes_from(section))
        return list(reversed(release_episodes))

    """async def new_scans(self) -> list[Scan]:
        raise NotImplementedError"""

    async def new_content(self) -> list[Catalogue]:
        raise NotImplementedError

    async def classics(self) -> list[Catalogue]:
        raise NotImplementedError

    async def highlights(self) -> list[Catalogue]:
        raise NotImplementedError
