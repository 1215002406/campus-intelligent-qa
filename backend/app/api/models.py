from fastapi import APIRouter, HTTPException, status

from app.api.dependencies import AdminUser, LLMModelsDependency
from app.schemas import LLMModelStatus, LLMModelSwitchRequest, LLMRemoteConfigUpdate

router = APIRouter(prefix="/admin/models", tags=["admin models"])


@router.get("/status", response_model=LLMModelStatus)
def model_status(user: AdminUser, service: LLMModelsDependency):
    return service.status()


@router.post("/switch", response_model=LLMModelStatus)
def switch_model(
    payload: LLMModelSwitchRequest,
    user: AdminUser,
    service: LLMModelsDependency,
):
    try:
        return service.switch(payload.provider)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.patch("/remote", response_model=LLMModelStatus)
def configure_remote_model(
    payload: LLMRemoteConfigUpdate,
    user: AdminUser,
    service: LLMModelsDependency,
):
    try:
        return service.configure_remote(
            base_url=payload.base_url,
            model=payload.model,
            api_key=payload.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
