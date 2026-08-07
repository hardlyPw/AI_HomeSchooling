from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request

from application.dependencies import get_autorater_service
from application.services.autorater_service import AutoraterService
from schemas.autorater_schema import (
    ChatRequest,
    ChatResponse,
    ExampleImagesResponse,
    PreloadRequest,
    PreloadResponse,
    StartRequest,
    StartResponse,
)


router = APIRouter()


def _get_ar():
    return get_autorater_service().get_legacy_module()


def preload_first_example_background() -> str:
    return get_autorater_service().preload_first_example_background()


@router.get("/debug-mode")
def autorater_debug_mode(
    service: AutoraterService = Depends(get_autorater_service),
):
    try:
        return service.debug_state()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Autorater unavailable: {exc}")


@router.get("/examples", response_model=ExampleImagesResponse)
def autorater_examples(
    request: Request,
    practice_set: Literal["focused", "full"] = "focused",
    service: AutoraterService = Depends(get_autorater_service),
):
    return ExampleImagesResponse(
        images=[
            str(request.url_for("assets", path=f"{path.parent.name}/{path.name}"))
            for path in service.example_image_paths(practice_set)
        ],
    )


@router.post("/preload", response_model=PreloadResponse)
def autorater_preload(
    req: PreloadRequest,
    service: AutoraterService = Depends(get_autorater_service),
):
    try:
        return PreloadResponse(status=service.preload_image(req.image_b64))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to queue preload: {exc}")


@router.post("/preload-first", response_model=PreloadResponse)
def autorater_preload_first(
    practice_set: Literal["focused", "full"] = "focused",
    service: AutoraterService = Depends(get_autorater_service),
):
    try:
        return PreloadResponse(
            status=service.preload_first_example_background(practice_set)
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to queue first example preload: {exc}")


@router.post("/start", response_model=StartResponse)
def autorater_start(
    req: StartRequest,
    service: AutoraterService = Depends(get_autorater_service),
):
    try:
        result = service.start(req.image_b64)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Autorater unavailable: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start autorater: {exc}")

    return StartResponse(
        opener=result.opener,
        total_problems=result.total_problems,
        mode=result.mode,
    )


@router.post("/chat", response_model=ChatResponse)
def autorater_chat(
    req: ChatRequest,
    service: AutoraterService = Depends(get_autorater_service),
):
    try:
        result = service.chat(req.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Autorater unavailable: {exc}")

    return ChatResponse(
        reply=result.reply,
        next_opener=result.next_opener,
        mode=result.mode,
        next_mode=result.next_mode,
        is_done=result.is_done,
    )
