"""Operational cohorts by creation date; never infer bank settlement from a quote."""
from datetime import timedelta

from sqlalchemy import case, exists, func

from booker_api.business_reporting import MOSCOW, period
from booker_api.models import BillingOrder, Booking, BookingHold, Offer, OfferVersion, Payment
from booker_api.security import now


def revenue(db, date_from=None, date_to=None):
    today = now().astimezone(MOSCOW).date()
    first, last, start, end = period(date_from or today-timedelta(days=29), date_to or today)
    def payment_groups(model, extra=()):
        columns = [*extra, model.provider, model.status]
        rows = db.query(*columns, func.count(model.id), func.sum(model.amount_rub)).filter(
            model.created_at >= start, model.created_at < end).group_by(*columns).all()
        return [{**dict(zip([c.key for c in columns], row[:-2])), 'count': row[-2], 'amount_rub': int(row[-1] or 0),
            'source': 'test' if row[len(extra)] == 'stub' else 'recorded' if row[len(extra)] == 'external' else 'unverified'} for row in rows]
    external = exists().where(Payment.booking_id == Booking.id, Payment.status == 'succeeded', Payment.provider == 'external')
    test_payment = exists().where(Payment.booking_id == Booking.id, Payment.status == 'succeeded', Payment.provider == 'stub')
    source = case((external & test_payment, 'mixed'), (external, 'recorded'), (test_payment, 'test'), else_='unpaid')
    accruals = []
    for label, states in [('accrued', ['Confirmed', 'InProgress', 'Completed']), ('projected', ['DateHeld', 'AwaitingContract', 'AwaitingPayment'])]:
        query = db.query(func.count(Booking.id), func.sum(OfferVersion.honorarium_rub), func.sum(OfferVersion.platform_revenue_rub),
            func.count(OfferVersion.platform_revenue_rub), func.count(OfferVersion.id)).select_from(Booking).join(Offer, Offer.id == Booking.offer_id).outerjoin(
                OfferVersion, OfferVersion.id == Offer.active_version_id).filter(Booking.created_at >= start, Booking.created_at < end, Booking.status.in_(states))
        if label == "projected":
            query = query.filter(exists().where(BookingHold.booking_id == Booking.id, BookingHold.status == "active", BookingHold.expires_at > now()))
        rows = query.add_columns(source.label('source')).group_by(source).all()
        for row in rows or [(0, 0, 0, 0, 0, 'unpaid')]:
            accruals.append({'kind': label, 'source': row[5], 'bookings': row[0], 'gmv_known_rub': int(row[1] or 0), 'platform_fee_known_rub': int(row[2] or 0),
            'missing_quotes': row[0]-row[4], 'missing_fee_snapshots': row[0]-row[3]})
    return {'period': {'from': first.isoformat(), 'to': last.isoformat(), 'timezone': 'Europe/Moscow', 'basis': 'created_at'},
        'as_of': now().isoformat(), 'currency': 'RUB', 'payments': payment_groups(Payment),
        'orders': payment_groups(BillingOrder, (BillingOrder.product_kind,)), 'booking_values': accruals,
        'notes': ['Когорта записей, созданных за период; показан их текущий статус, а не денежный поток по датам списания.',
            'GMV — гонорар из сохранённых условий. Начисленная комиссия по подтверждённым сделкам не означает поступление денег.',
            'Тестовые и неизвестные провайдеры отделены от подтверждённых API внешних платежей. Банковская сверка и частичные возвраты здесь не восстанавливаются.',
            'Стоимость сделок разделена по наличию внешних, тестовых, смешанных подтверждений или отсутствию подтверждённой оплаты; она не складывается с оплатами. При отсутствии snapshot показана только известная часть.']}
