import asyncio
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
from resume_ai.storage.s3 import storage
from resume_ai.models.research import ResumeResearch 


@asynccontextmanager
async def lifespan(app: FastAPI):
    for attempt in range(30):
        try:
            await storage.ensure_bucket()
            await create_tables()
            await publisher.connect()
            await llm_runtime.start()
            break
        except RuntimeError:
            if attempt == 29:
                raise
            await asyncio.sleep(2)
    else:
        raise RuntimeError("Application startup failed")

    try:
        yield
    finally:
        await llm_runtime.close()
        await close_database()
        await publisher.close()


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
def hello():
    return "hello API"
