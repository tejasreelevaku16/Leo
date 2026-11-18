
import os
import re
import secrets
import hashlib

from datetime import datetime, timedelta, timezone

from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
    UploadFile,
    File
)

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from argon2 import PasswordHasher
from argon2.exceptions import (
    HashingError,
    VerifyMismatchError,
    VerificationError,
    InvalidHashError
)

from backend.database import get_db
from backend.models import User, UserSession


router = APIRouter(prefix="/auth", tags=["Authentication"])

password_hasher = PasswordHasher()

SESSION_COOKIE_NAME = "leo_session"
SESSION_DURATION_DAYS = 7

IS_PRODUCTION = os.getenv("LEO_ENV", "development").lower() == "production"

COOKIE_SECURE = IS_PRODUCTION
COOKIE_SAMESITE = "none" if IS_PRODUCTION else "lax"

MAX_PROFILE_PIC_SIZE = 5 * 1024 * 1024  # 5 MB
PROFILE_UPLOAD_DIR = Path("uploads/profile_pictures")
PROFILE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def validate_image_content(data: bytes) -> str | None:
    """
    Validate magic bytes for safe image formats (JPEG, PNG, WebP).
    Returns file extension if valid ('jpg', 'png', 'webp'), else None.
    """
    if len(data) < 12:
        return None

    # JPEG: \xff\xd8\xff
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"

    # PNG: \x89PNG\r\n\x1a\n
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"

    # WebP: RIFF....WEBP
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"

    return None


# -------------------------
# REQUEST MODELS
# -------------------------

class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=1, max_length=128)


# -------------------------
# SESSION HELPERS
# -------------------------

def get_session_hash(session_token: str) -> str:
    return hashlib.sha256(session_token.encode("utf-8")).hexdigest()


def get_current_time():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def set_session_cookie(response: Response, session_token: str):
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        max_age=SESSION_DURATION_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE,
        path="/"
    )


def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
):
    session_token = request.cookies.get(SESSION_COOKIE_NAME)

    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Please log in to continue."
        )

    token_hash = get_session_hash(session_token)

    user_session = (
        db.query(UserSession)
        .filter(
            UserSession.token_hash == token_hash,
            UserSession.expires_at > get_current_time()
        )
        .first()
    )

    if not user_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid. Please log in again."
        )

    user = db.query(User).filter(
        User.id == user_session.user_id
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found."
        )

    return user


# -------------------------
# REGISTER
# -------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED)
def register_user(
    data: SignupRequest,
    db: Session = Depends(get_db)
):

    full_name = data.full_name.strip()
    email = data.email.strip().lower()

    if len(full_name) < 2:
        raise HTTPException(
            status_code=400,
            detail="Enter a valid name."
        )

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(
            status_code=400,
            detail="Enter a valid email address."
        )

    existing_user = db.query(User).filter(
        User.email == email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists."
        )

    try:
        hashed_password = password_hasher.hash(data.password)

        new_user = User(
            full_name=full_name,
            email=email,
            password_hash=hashed_password
        )

        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return {
            "message": "Account created successfully.",
            "user_id": new_user.id,
            "full_name": new_user.full_name,
            "email": new_user.email
        }

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists."
        )

    except HashingError:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to securely process the password."
        )


# -------------------------
# LOGIN
# -------------------------

@router.post("/login")
def login_user(
    data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db)
):

    email = data.email.strip().lower()

    user = db.query(User).filter(
        User.email == email
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    try:
        password_hasher.verify(
            user.password_hash,
            data.password
        )

    except (VerifyMismatchError, VerificationError, InvalidHashError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    # Generate a cryptographically secure session token.
    session_token = secrets.token_urlsafe(32)

    # Store only its SHA-256 hash in MySQL.
    token_hash = get_session_hash(session_token)

    current_time = get_current_time()
    expires_at = current_time + timedelta(days=SESSION_DURATION_DAYS)

    new_session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at
    )

    try:
        db.add(new_session)
        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Unable to create your session."
        )

    set_session_cookie(response, session_token)

    return {
        "message": "Login successful.",
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "profile_picture": user.profile_picture
        }
    }


# -------------------------
# VERIFY CURRENT SESSION
# -------------------------

@router.get("/me")
def get_logged_in_user(
    current_user: User = Depends(get_current_user)
):

    return {
        "authenticated": True,
        "user": {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "profile_picture": current_user.profile_picture
        }
    }


# -------------------------
# PROFILE INFORMATION
# -------------------------

@router.get("/profile")
def get_user_profile(
    current_user: User = Depends(get_current_user)
):

    return {
        "status": "success",
        "user": {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "profile_picture": current_user.profile_picture,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None
        }
    }


# -------------------------
# PROFILE PICTURE MANAGEMENT
# -------------------------

@router.post("/profile-picture")
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    content = await file.read()

    if len(content) > MAX_PROFILE_PIC_SIZE:
        raise HTTPException(
            status_code=400,
            detail="Profile picture size exceeds maximum allowed limit of 5MB."
        )

    ext = validate_image_content(content)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="Invalid image format. Only genuine JPEG, PNG, and WebP images are allowed."
        )

    # Clean up old profile picture from disk if it exists
    if current_user.profile_picture:
        old_filename = Path(current_user.profile_picture).name
        old_file_path = PROFILE_UPLOAD_DIR / old_filename
        try:
            if old_file_path.is_file():
                old_file_path.unlink()
        except Exception:
            pass

    # Generate safe unique filename
    filename = f"avatar_{current_user.id}_{secrets.token_hex(8)}.{ext}"
    safe_file_path = PROFILE_UPLOAD_DIR / filename

    with open(safe_file_path, "wb") as f:
        f.write(content)

    relative_url = f"/uploads/profile_pictures/{filename}"
    current_user.profile_picture = relative_url
    db.commit()
    db.refresh(current_user)

    return {
        "status": "success",
        "message": "Profile picture updated successfully.",
        "profile_picture": relative_url
    }


@router.delete("/profile-picture")
def delete_profile_picture(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    if current_user.profile_picture:
        old_filename = Path(current_user.profile_picture).name
        old_file_path = PROFILE_UPLOAD_DIR / old_filename
        try:
            if old_file_path.is_file():
                old_file_path.unlink()
        except Exception:
            pass

        current_user.profile_picture = None
        db.commit()
        db.refresh(current_user)

    return {
        "status": "success",
        "message": "Profile picture removed successfully."
    }


# -------------------------
# LOGOUT
# -------------------------

@router.post("/logout")
def logout_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db)
):

    session_token = request.cookies.get(SESSION_COOKIE_NAME)

    if session_token:
        token_hash = get_session_hash(session_token)

        db.query(UserSession).filter(
            UserSession.token_hash == token_hash
        ).delete(synchronize_session=False)

        db.commit()

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=COOKIE_SECURE,
        samesite=COOKIE_SAMESITE
    )

    return {
        "message": "Logged out successfully."
    }
