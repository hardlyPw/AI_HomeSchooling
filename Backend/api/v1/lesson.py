import os
import time
from dotenv import load_dotenv
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import OpenAI

load_dotenv()

router = APIRouter()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


class TTSRequest(BaseModel):
    text: str


@router.post("/tts")
def text_to_speech(request: TTSRequest):
    t0 = time.perf_counter()
    response = openai_client.audio.speech.create(
        model="tts-1",
        voice="shimmer",
        input=request.text,
    )
    t1 = time.perf_counter()
    print(f"[TIMER] TTS 생성:       {t1 - t0:.2f}s  ({len(request.text)}자 입력)")
    return StreamingResponse(
        response.iter_bytes(),
        media_type="audio/mpeg",
    )
