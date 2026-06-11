from contextlib import asynccontextmanager
import logging
from pathlib import Path
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.v1.chat import router as chat_router
from api.v1.lesson import router as lesson_router
from api.v1.autorater import (
    router as autorater_router,
    _get_ar,
    preload_first_example_background,
)
from api.v1.friend import router as friend_router


ASSETS_DIR = Path(__file__).resolve().parent / "assets"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm the autorater in the background so static assets and /examples can
    # respond immediately while the embedding model loads.
    def warm_up_autorater() -> None:
        try:
            _get_ar()
            preload_first_example_background()
        except Exception as exc:
            logging.getLogger(__name__).warning("Autorater warm-up failed: %s", exc)

    threading.Thread(
        target=warm_up_autorater,
        daemon=True,
        name="autorater-warmup",
    ).start()
    yield


app = FastAPI(title="Chatbot Service Mock API", lifespan=lifespan)

# CORS 설정: React(8080)에서 오는 요청 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록 (버전 관리 포함)
app.include_router(chat_router, prefix="/api/v1", tags=["Chat"])
app.include_router(lesson_router, prefix="/api/v1/lesson", tags=["Lesson"])
app.include_router(autorater_router, prefix="/api/v1/autorater", tags=["Autorater"])
app.include_router(friend_router, prefix="/api/v1/friend", tags=["Friend"])
app.mount("/assets", StaticFiles(directory=ASSETS_DIR, check_dir=False), name="assets")

@app.get("/")
def health_check():
    return {"status": "ok", "message": "Backend server is running"}