from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import InvalidTokenError, create_access_token, decode_access_token
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserPublic
from app.services.auth import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    authenticate_user,
    create_user,
    get_user_by_id,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

# auto_error=False so we always answer 401 (not 403) when the header is missing.
bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserPublic:
    """Reusable dependency: resolves the Bearer token to the authenticated user's safe profile."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing authentication token",
        headers=_UNAUTHORIZED_HEADERS,
    )
    if credentials is None:
        raise unauthorized
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidTokenError:
        raise unauthorized from None

    user = await get_user_by_id(user_id)
    if user is None:  # e.g. account deleted after the token was issued
        raise unauthorized
    return user


@router.post("/signup", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest):
    try:
        return await create_user(
            name=payload.name,
            email=payload.email,
            password=payload.password.get_secret_value(),
        )
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from None


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest):
    try:
        user = await authenticate_user(payload.email, payload.password.get_secret_value())
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers=_UNAUTHORIZED_HEADERS,
        ) from None
    return TokenResponse(access_token=create_access_token(user.id), user=user)


@router.get("/me", response_model=UserPublic)
async def me(current_user: UserPublic = Depends(get_current_user)):
    return current_user