import logging

from app.catalogue.registry import get_release_checkers
from app.database import SessionLocal
from app.jobs.check_releases import check_releases
from app.jobs.send_reminders import send_reminders
from app.mailer.sender import get_email_sender

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as db:
        releases = check_releases(db, get_release_checkers())
        logger.info("Release check finished: %s", releases)
        reminders = send_reminders(db, get_email_sender())
        logger.info("Reminders finished: %s", reminders)


if __name__ == "__main__":
    main()
