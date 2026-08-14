import asyncio
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api import router
from .config import get_settings
from .database import SessionLocal
from .models import AuditLog
from .services.rag import embeddings

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    warmup_task = None
    if settings.embedding_warmup_on_startup:
        warmup_task = asyncio.create_task(asyncio.to_thread(embeddings.warmup))
        warmup_task.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
    yield
    if warmup_task and not warmup_task.done():
        warmup_task.cancel()


app = FastAPI(title="Raqobat AI Assistant", version="1.1.0", docs_url="/api/docs",
              openapi_url="/api/openapi.json", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/api/health")
def health():
    return {"status": "ishlayapti", "embedding": embeddings.status()["state"]}


@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        if request.url.path.startswith("/api/") and request.url.path not in {"/api/docs", "/api/openapi.json"}:
            user_id = None
            authorization = request.headers.get("authorization", "")
            if authorization.startswith("Bearer "):
                try:
                    payload = jwt.decode(authorization[7:], settings.secret_key, algorithms=["HS256"])
                    user_id = payload.get("sub")
                except Exception:
                    pass
            try:
                with SessionLocal() as db:
                    db.add(AuditLog(user_id=user_id, action=request.url.path.rsplit("/", 1)[-1] or "api",
                                    method=request.method, path=request.url.path,
                                    resource=request.path_params.get("document_id") or request.path_params.get("nhh_id") or request.path_params.get("task_id"),
                                    status_code=response.status_code if response else 500))
                    db.commit()
            except Exception:
                pass


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": "Tizimda kutilmagan xatolik yuz berdi"})
