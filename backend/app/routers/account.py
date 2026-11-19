"""Registration, email confirmation, password reset and the account page (FR89-FR92)."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from .. import account_service
from ..database import Database, get_db
from ..security import client_ip, get_current_user

router = APIRouter(prefix="/api/account", tags=["account"])

SENT = "If an account with this address needs it, we have sent an email. Please check your inbox."


class RegisterIn(BaseModel):
    username: str = Field("", max_length=100)
    email: str = Field("", max_length=320)
    display_name: str = Field("", max_length=200)
    password: str = Field("", max_length=200)
    password_confirm: str = Field("", max_length=200)


class TokenIn(BaseModel):
    token: str = Field("", max_length=200)


class EmailIn(BaseModel):
    email: str = Field("", max_length=320)


class ResetIn(BaseModel):
    token: str = Field("", max_length=200)
    password: str = Field("", max_length=200)
    password_confirm: str = Field("", max_length=200)


class ProfileIn(BaseModel):
    display_name: str = Field("", max_length=200)


class PasswordChangeIn(BaseModel):
    current_password: str = Field("", max_length=200)
    new_password: str = Field("", max_length=200)
    new_password_confirm: str = Field("", max_length=200)


# --- Open to visitors -------------------------------------------------------------


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, conn: Database = Depends(get_db)):
    account_service.register(conn, **body.model_dump(), ip=client_ip(request))
    return {"message": "Almost done! We have sent you an email with a link to confirm your address."}


@router.post("/verify-email")
def verify_email(body: TokenIn, conn: Database = Depends(get_db)):
    account_service.verify_email(conn, body.token)
    return {"message": "Your email address is confirmed. You can now log in."}


@router.post("/resend-verification")
def resend_verification(body: EmailIn, request: Request, conn: Database = Depends(get_db)):
    account_service.resend_verification(conn, body.email, client_ip(request))
    return {"message": SENT}


@router.post("/forgot-password")
def forgot_password(body: EmailIn, request: Request, conn: Database = Depends(get_db)):
    account_service.request_password_reset(conn, body.email, client_ip(request))
    return {"message": SENT}


@router.post("/reset-password")
def reset_password(body: ResetIn, conn: Database = Depends(get_db)):
    account_service.reset_password(conn, body.token, body.password, body.password_confirm)
    return {"message": "Your password has been changed. Please log in with your new password."}


# --- Logged in ------------------------------------------------------------------


@router.get("")
def my_account(user=Depends(get_current_user), conn: Database = Depends(get_db)):
    return account_service.account_view(conn, user)


@router.patch("")
def update_profile(body: ProfileIn, user=Depends(get_current_user), conn: Database = Depends(get_db)):
    account_service.update_display_name(conn, user, body.display_name)
    return {**account_service.account_view(conn, user), "message": "Your display name has been saved."}


@router.post("/password")
def change_password(body: PasswordChangeIn, request: Request, user=Depends(get_current_user), conn: Database = Depends(get_db)):
    account_service.change_password(
        conn, user, body.current_password, body.new_password, body.new_password_confirm, client_ip(request)
    )
    return {"message": "Your password has been changed. You have been logged out everywhere else."}
