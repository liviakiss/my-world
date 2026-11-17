import logging
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.catalogue.base import CatalogueAdapter, CatalogueError
from app.catalogue.registry import Catalogue, get_catalogue
from app.database import get_db
from app.models import DataSource, MediaType, User, Work
from app.schemas.catalogue import CatalogueResult, ImportRequest
from app.schemas.works import WorkResponse
from app.security.rate_limit import search_limiter, write_limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/catalogue", tags=["catalogue"])

UPSTREAM_ERROR = "The catalogue is not responding right now. Please try again later."


def _adapter_for(catalogue: Catalogue, media_type: MediaType) -> CatalogueAdapter:
    adapter = catalogue.adapter_for(media_type)
    if adapter is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Search for this media type is not available yet.",
        )
    return adapter


def _upstream_failed(source: DataSource, exc: CatalogueError) -> HTTPException:
    logger.warning("Catalogue %s failed: %s", source.value, exc)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UPSTREAM_ERROR)


def _find_cached(db: Session, source: DataSource, external_id: str) -> Work | None:
    return db.scalar(select(Work).where(Work.source == source, Work.external_id == external_id))


@router.get("/search", response_model=list[CatalogueResult], dependencies=[Depends(search_limiter)])
def search(
    q: str = Query(min_length=2, max_length=100),
    media_type: MediaType = Query(),
    user: User = Depends(get_current_user),
    catalogue: Catalogue = Depends(get_catalogue),
) -> list[CatalogueResult]:
    adapter = _adapter_for(catalogue, media_type)
    try:
        items = adapter.search(q.strip(), media_type)
    except CatalogueError as exc:
        raise _upstream_failed(adapter.source, exc) from None
    return [CatalogueResult.from_item(item) for item in items]


@router.post("/import", response_model=WorkResponse, dependencies=[Depends(write_limiter)])
def import_work(
    payload: ImportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    catalogue: Catalogue = Depends(get_catalogue),
) -> Work:
    adapter = _adapter_for(catalogue, payload.media_type)

    cached = _find_cached(db, adapter.source, payload.external_id)
    if cached is not None:
        return cached

    try:
        item = adapter.fetch(payload.external_id, payload.media_type)
    except CatalogueError as exc:
        raise _upstream_failed(adapter.source, exc) from None
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found in the catalogue.")

    work = Work(**asdict(item))
    db.add(work)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _find_cached(db, adapter.source, payload.external_id)
    return work
