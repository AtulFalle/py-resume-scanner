import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from resume_ai.ai.runtime import llm_runtime
from resume_ai.api.routes.ai import router as ai_router
from resume_ai.api.routes.health import router as health_router
from resume_ai.api.routes.resume import router as resume_router
from resume_ai.api.routes.search import router as search_router
from resume_ai.core.config import settings
from resume_ai.core.database import close_database, create_tables
from resume_ai.message_queue.publisher import publisher
from resume_ai.storage.qdrant import qdrant_storage
from resume_ai.storage.s3 import storage

logger = logging.getLogger(__name__)

STARTUP_ATTEMPTS = 30
STARTUP_RETRY_SECONDS = 2


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dependencies (Postgres, RabbitMQ, storage) may still be starting.
    for attempt in range(1, STARTUP_ATTEMPTS + 1):
        try:
            await storage.ensure_bucket()
            await create_tables()
            await qdrant_storage.ensure_collection()
            await publisher.connect()
            await llm_runtime.start()
            break
        except Exception:
            if attempt == STARTUP_ATTEMPTS:
                raise
            logger.warning(
                "Startup attempt %d/%d failed; retrying",
                attempt,
                STARTUP_ATTEMPTS,
                exc_info=True,
            )
            await asyncio.sleep(STARTUP_RETRY_SECONDS)

    try:
        yield
    finally:
        await llm_runtime.close()
        await publisher.close()
        await qdrant_storage.close()
        await close_database()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(resume_router)
app.include_router(ai_router)
app.include_router(search_router)


@app.get("/")
def hello() -> str:
    return "hello API"
