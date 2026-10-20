# enums.py — fixed value lists shared by several models.
import enum


class MediaType(str, enum.Enum):
    BOOK = "book"
    MANGA = "manga"
    TV = "tv"
    MOVIE = "movie"
    ANIME = "anime"
    GAME = "game"


class DataSource(str, enum.Enum):
    # Where a Work's data came from. CUSTOM = typed in by a user.
    TMDB = "tmdb"
    IGDB = "igdb"
    OPEN_LIBRARY = "open_library"
    GOOGLE_BOOKS = "google_books"
    CUSTOM = "custom"


class SeriesStatus(str, enum.Enum):
    ONGOING = "ongoing"      # more parts expected → the release checker watches it
    FINISHED = "finished"
    UNKNOWN = "unknown"


class DatePrecision(str, enum.Enum):
    # "Spring 2027" is not the same as "14 March 2027"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"
    UNKNOWN = "unknown"


def enum_values(enum_cls):
    # Reusable version of the lesson from the users table:
    # store the VALUES ("book"), not the NAMES ("BOOK").
    return [member.value for member in enum_cls]