from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from functools import cache

import boto3
import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from shared import config, db

router = APIRouter(prefix="/api")


@dataclass
class User:
    user_id: int
    email: str
    name: str
    role: str
    student_id: str | None


class DevLogin(BaseModel):
    email: str


def issuer():
    return f"https://cognito-idp.{config.COGNITO_REGION}.amazonaws.com/{config.COGNITO_USER_POOL_ID}"


@cache
def jwks():
    return jwt.PyJWKClient(f"{issuer()}/.well-known/jwks.json")


def email_from_token(raw):
    if config.AUTH_MODE == "dev":
        claims = jwt.decode(raw, config.DEV_SECRET, algorithms=["HS256"])
    else:
        key = jwks().get_signing_key_from_jwt(raw).key
        claims = jwt.decode(raw, key, algorithms=["RS256"], audience=config.COGNITO_CLIENT_ID, issuer=issuer())
    return claims["email"].lower()


def user_from_token(raw):
    if not raw:
        raise HTTPException(401, "Sign in to continue.")
    try:
        email = email_from_token(raw)
    except (jwt.PyJWTError, KeyError):
        raise HTTPException(401, "Your session has expired. Sign in again.")
    with db.connection() as conn:
        row = conn.execute(
            "SELECT u.user_id, u.email, u.name, u.role, s.student_id "
            "FROM users u LEFT JOIN students s ON s.user_id = u.user_id WHERE u.email = %s",
            (email,),
        ).fetchone()
    if row is None:
        raise HTTPException(403, "This email hasn't been invited to Scribe-Check.")
    return User(**row)


def current_user(authorization: str = Header(default="")):
    return user_from_token(authorization.removeprefix("Bearer ").strip())


def require_teacher(user: User = Depends(current_user)):
    if user.role not in ("teacher", "admin"):
        raise HTTPException(403, "Only teachers can do this.")
    return user


def require_student(user: User = Depends(current_user)):
    if user.role != "student" or not user.student_id:
        raise HTTPException(403, "Only students can do this.")
    return user


def invite(email):
    if config.AUTH_MODE != "cognito":
        return
    client = boto3.client("cognito-idp", region_name=config.COGNITO_REGION)
    try:
        client.admin_create_user(
            UserPoolId=config.COGNITO_USER_POOL_ID,
            Username=email,
            UserAttributes=[{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": "true"}],
            DesiredDeliveryMediums=["EMAIL"],
        )
    except client.exceptions.UsernameExistsException:
        pass


@router.get("/config")
def public_config():
    return {
        "auth_mode": config.AUTH_MODE,
        "cognito_domain": config.COGNITO_DOMAIN,
        "cognito_client_id": config.COGNITO_CLIENT_ID,
    }


@router.post("/dev/login")
def dev_login(body: DevLogin):
    if config.AUTH_MODE != "dev":
        raise HTTPException(404)
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    return {"token": jwt.encode({"email": body.email.strip().lower(), "exp": expires}, config.DEV_SECRET, algorithm="HS256")}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return asdict(user)
