from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from booker_api.composition import seed_categories
from booker_api.config import settings, validate_runtime_config
from booker_api.db import SessionLocal, engine, init_schema
from booker_api.legal_registry import seed_draft_versions
from booker_api.ops_http import OpsHttpMiddleware
from booker_api.rate_limit import initialize_rate_limit_store
from booker_api.request_body_limit import AttachmentBodyLimitMiddleware
from booker_api.routers import (
    admin,
    analytics,
    briefs,
    catalog,
    data_subject,
    deals,
    favorites,
    health,
    identity,
    legal,
    payments,
    promo,
    reviews,
    saved_searches,
    services,
    shortlists,
    trust,
    venue_admin,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_runtime_config()
    init_schema(engine)
    initialize_rate_limit_store()
    db = SessionLocal()
    try:
        seed_draft_versions(db)
        seed_categories(db)
        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="Букер API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AttachmentBodyLimitMiddleware)
app.add_middleware(OpsHttpMiddleware)
app.include_router(health.router)
app.include_router(identity.router)
app.include_router(legal.router)
app.include_router(data_subject.router)
app.include_router(analytics.router)
app.include_router(catalog.router)
app.include_router(favorites.router)
app.include_router(services.router)
app.include_router(deals.router)
app.include_router(payments.router)
app.include_router(reviews.router)
app.include_router(briefs.router)
app.include_router(shortlists.router)
app.include_router(trust.router)
app.include_router(saved_searches.router)
app.include_router(promo.router)
app.include_router(admin.router)
app.include_router(venue_admin.router)
