from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.v1.chat import router as chat_router
from api.v1.lesson import router as lesson_router

app = FastAPI(title="Chatbot Service Mock API")

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

@app.get("/")
def health_check():
    return {"status": "ok", "message": "Backend server is running"}