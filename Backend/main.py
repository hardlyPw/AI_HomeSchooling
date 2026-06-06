from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.chat import router as chat_router
from api.v1.lesson import router as lesson_router
from api.v1.autorater import router as autorater_router, _get_ar


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Eagerly load main_autorater (and its embedding model) at startup
    # so the first user request doesn't pay the cold-start penalty.
    try:
        _get_ar()
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Autorater warm-up failed: %s", exc)
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

@app.get("/")
def health_check():
    return {"status": "ok", "message": "Backend server is running"}