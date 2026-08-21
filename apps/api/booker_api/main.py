from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from booker_api.config import settings
from booker_api.db import Base, engine
from booker_api.routers import admin, catalog, deals, health, identity, payments


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Букер API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(identity.router)
app.include_router(catalog.router)
app.include_router(deals.router)
app.include_router(payments.router)
app.include_router(admin.router)
