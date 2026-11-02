from fastapi import APIRouter

from app.api.dependencies import CurrentUser, SessionDependency, SettingsDependency
from app.schemas import LoginRequest, LoginResponse, RegisterRequest, UserOut
from app.services.accounts import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, session: SessionDependency, settings: SettingsDependency):
    token, user = AuthService(session, settings).login(payload.username, payload.password)
    return LoginResponse(access_token=token, user=UserOut.model_validate(user))


@router.post("/register", response_model=LoginResponse, status_code=201)
def register(payload: RegisterRequest, session: SessionDependency, settings: SettingsDependency):
    token, user = AuthService(session, settings).register(
        payload.username,
        payload.password,
        payload.role,
        payload.admin_code,
    )
    return LoginResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser):
    return user
