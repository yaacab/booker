"""Bounded lifecycle expiry work; no external notification transports."""
import argparse
import json

from booker_api.commerce.promotions import expire_campaigns
from booker_api.commerce.service import expire_subscriptions
from booker_api.db import SessionLocal
from booker_api.models import BookingHold, PromotionCampaign, Subscription
from booker_api.routers.deals import expire_holds
from booker_api.security import now


def run_maintenance(db, limit=100):
    if not 1 <= limit <= 100:
        raise ValueError('limit должен быть от 1 до 100')
    return {'subscriptions_expired': expire_subscriptions(db, limit=limit),
        'promotions_expired': expire_campaigns(db, limit=limit), 'holds_expired': expire_holds(db, limit=limit)}


def main():
    parser = argparse.ArgumentParser(description='Истечение сроков и in-app уведомления Букера')
    parser.add_argument('--run', action='store_true', help='Применить истечение сроков и сохранить уведомления')
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('--limit должен быть от 1 до 100')
    with SessionLocal() as db:
        if args.run:
            result = run_maintenance(db, args.limit); db.commit()
        else:
            result = {'state': 'inspection',
                'subscriptions_due': db.query(Subscription).filter(Subscription.status.in_(['active', 'trial', 'past_due']), Subscription.current_period_end <= now()).count(),
                'promotions_due': db.query(PromotionCampaign).filter(PromotionCampaign.status.in_(['active', 'scheduled']), PromotionCampaign.ends_at <= now()).count(),
                'holds_due': db.query(BookingHold).filter(BookingHold.status == 'active', BookingHold.expires_at <= now()).count()}
        print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
