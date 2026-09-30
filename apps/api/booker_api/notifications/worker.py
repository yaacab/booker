"""Bounded email queue worker. Without --deliver, prints counts only."""
import argparse
import json

from sqlalchemy import func

from booker_api.db import SessionLocal
from booker_api.models import EmailOutbox
from booker_api.notifications.outbox import retry_pending_outbox


def main():
    parser = argparse.ArgumentParser(description='Очередь email Букера')
    parser.add_argument('--deliver', action='store_true', help='Обработать сохранённую очередь через настроенный SMTP')
    parser.add_argument('--limit', type=int, default=50)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('--limit должен быть от 1 до 100')
    with SessionLocal() as db:
        result = retry_pending_outbox(db, limit=args.limit) if args.deliver else {
            'state': 'inspection', 'counts': dict(db.query(EmailOutbox.status, func.count(EmailOutbox.id)).group_by(EmailOutbox.status).all())}
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
