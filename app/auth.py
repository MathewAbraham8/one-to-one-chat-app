import os
import hmac
import hashlib
import json
import base64
import time
import logging
import secrets
from datetime import datetime
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User

# Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    # Save an ephemeral key for local/testing. Log a warning.
    logging.warning("JWT_SECRET_KEY environment variable not set. Generating a dynamic secret key. Active sessions will not survive restarts.")
    JWT_SECRET_KEY = secrets.token_hex(32)

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# --- Base64URL Helpers ---
def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')

def base64url_decode(data: str) -> bytes:
    padding = '=' * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data + padding)

# --- Password Security ---
def hash_password(password: str) -> tuple[str, str]:
    """
    Hash a password using memory-hard scrypt.
    Returns: (password_hash_hex, salt_hex)
    """
    salt = os.urandom(16)
    pwd_hash = hashlib.scrypt(
        password.encode('utf-8'),
        salt=salt,
        n=16384,
        r=8,
        p=1,
        dklen=64
    )
    return pwd_hash.hex(), salt.hex()

def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """
    Verify a password against stored salt and hash.
    """
    try:
        salt = bytes.fromhex(salt_hex)
        stored_hash = bytes.fromhex(hash_hex)
        pwd_hash = hashlib.scrypt(
            password.encode('utf-8'),
            salt=salt,
            n=16384,
            r=8,
            p=1,
            dklen=64
        )
        return hmac.compare_digest(pwd_hash, stored_hash)
    except Exception:
        return False

# --- JWT Helpers ---
def create_jwt(payload: dict, expires_in_seconds: int = ACCESS_TOKEN_EXPIRE_MINUTES * 60) -> str:
    """
    Create a signed JWT token with exp and iat claims.
    """
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    
    token_payload = payload.copy()
    now = int(time.time())
    token_payload["iat"] = now
    token_payload["exp"] = now + expires_in_seconds
    
    header_json = json.dumps(header, separators=(',', ':')).encode('utf-8')
    payload_json = json.dumps(token_payload, separators=(',', ':')).encode('utf-8')
    
    signing_input = f"{base64url_encode(header_json)}.{base64url_encode(payload_json)}"
    signature = hmac.new(
        JWT_SECRET_KEY.encode('utf-8'),
        signing_input.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    return f"{signing_input}.{base64url_encode(signature)}"

def decode_jwt(token: str) -> dict:
    """
    Decode and validate a JWT token.
    Throws ValueError on failure.
    """
    parts = token.split('.')
    if len(parts) != 3:
        raise ValueError("Invalid token format")
    
    signing_input = f"{parts[0]}.{parts[1]}"
    signature = base64url_decode(parts[2])
    
    # Verify signature
    expected_signature = hmac.new(
        JWT_SECRET_KEY.encode('utf-8'),
        signing_input.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Signature verification failed")
    
    # Parse header and payload
    header = json.loads(base64url_decode(parts[0]).decode('utf-8'))
    payload = json.loads(base64url_decode(parts[1]).decode('utf-8'))
    
    # Reject 'none' algorithm and enforce expected algorithm
    if header.get("alg") != JWT_ALGORITHM:
        raise ValueError(f"Invalid signing algorithm: {header.get('alg')}")
        
    # Check expiration
    if payload.get("exp", 0) < time.time():
        raise ValueError("Token has expired")
        
    return payload

# --- Dependency for Authenticated Endpoints ---
security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    FastAPI dependency that decodes JWT and returns the User object.
    Checks user existence and token revocation.
    """
    token = credentials.credentials
    try:
        payload = decode_jwt(token)
        user_id = int(payload.get("sub"))
        token_iat = float(payload.get("iat"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired credentials: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user not found",
        )
        
    # Invalidation check: if the token was issued before the user's last logout time, reject it
    token_iat_dt = datetime.utcfromtimestamp(token_iat)
    if token_iat_dt.replace(microsecond=0) < user.last_logout_at.replace(microsecond=0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please log in again.",
        )
        
    return user
