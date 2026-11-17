from functools import lru_cache

from app.catalogue.base import CatalogueAdapter
from app.catalogue.http import create_client
from app.catalogue.open_library import OpenLibraryAdapter
from app.catalogue.tmdb import TmdbAdapter
from app.config import settings
from app.models import MediaType


class Catalogue:
    def __init__(self, adapters: dict[MediaType, CatalogueAdapter]) -> None:
        self._adapters = adapters

    def adapter_for(self, media_type: MediaType) -> CatalogueAdapter | None:
        return self._adapters.get(media_type)


@lru_cache
def get_catalogue() -> Catalogue:
    client = create_client(settings.catalogue_user_agent)
    open_library = OpenLibraryAdapter(client)
    adapters: dict[MediaType, CatalogueAdapter] = {
        MediaType.BOOK: open_library,
        MediaType.MANGA: open_library,
    }
    if settings.tmdb_api_token is not None:
        tmdb = TmdbAdapter(client, settings.tmdb_api_token.get_secret_value())
        adapters.update({MediaType.MOVIE: tmdb, MediaType.TV: tmdb, MediaType.ANIME: tmdb})
    return Catalogue(adapters)
