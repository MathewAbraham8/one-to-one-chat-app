import os
import time
import logging
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status, Query, WebSocket, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

# Import project modules
from app.database import engine, Base, get_db
from app.models import User, Message
from app.schemas import (
    UserRegister, UserResponse, LoginRequest, LoginResponse, MessageResponse, MessageCreate
)
from app.auth import (
    hash_password, verify_password, create_jwt, decode_jwt, get_current_user
)
from app.websocket import manager

# Set up logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Ensure all database tables exist on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="One-to-One Chat API",
    description="Secure, authenticated one-to-one real-time chat application API.",
    version="1.0.0"
)

# --- CORS Configuration ---
# MUST only allow trusted origins to access your resources. Avoid wildcard origins.
origins_raw = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
origins = [origin.strip() for origin in origins_raw.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# --- In-Memory Rate Limiter ---
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 100
ip_request_counts = {}  # ip -> list of timestamps

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.scope.get("type") == "http":
        ip = request.client.host if request.client else "127.0.0.1"
        now = time.time()
        
        # Clean old timestamps outside the window
        ip_request_counts[ip] = [t for t in ip_request_counts.get(ip, []) if now - t < RATE_LIMIT_WINDOW_SECONDS]
        
        if len(ip_request_counts[ip]) >= RATE_LIMIT_MAX_REQUESTS:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests. Please try again later."}
            )
        ip_request_counts[ip].append(now)
        
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        logging.error(f"Unhandled system error: {str(exc)}")
        # MUST NOT expose system errors/tracebacks to users
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"}
        )

# --- Endpoints ---

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserRegister, db: Session = Depends(get_db)):
    """
    Public registration endpoint.
    Checks username collision, hashes password using scrypt, and creates user.
    """
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    pwd_hash, salt = hash_password(user_data.password)
    db_user = User(
        username=user_data.username,
        password_hash=pwd_hash,
        salt=salt
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@app.post("/login", response_model=LoginResponse)
def login(credentials: LoginRequest, db: Session = Depends(get_db)):
    """
    Public login endpoint.
    Verifies user password and issues JWT.
    """
    user = db.query(User).filter(User.username == credentials.username).first()
    if not user or not verify_password(credentials.password, user.salt, user.password_hash):
        # Generic error message to prevent username enumeration
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Generate token
    token = create_jwt(payload={"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/logout", status_code=status.HTTP_200_OK)
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Invalidates all active tokens for the current user.
    """
    current_user.last_logout_at = datetime.utcnow()
    db.commit()
    return {"detail": "Successfully logged out. All active sessions invalidated."}

@app.get("/users", response_model=list[UserResponse])
def get_users(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Returns list of all registered users. Authenticated users only.
    """
    users = db.query(User).all()
    return users

@app.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(user_data: UserRegister, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Administrative / authenticated user creation endpoint.
    """
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    pwd_hash, salt = hash_password(user_data.password)
    db_user = User(
        username=user_data.username,
        password_hash=pwd_hash,
        salt=salt
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@app.delete("/users/{id}", status_code=status.HTTP_200_OK)
def delete_user(id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Deletes user by ID.
    Enforces that users can only delete their own account (IDOR protection).
    """
    if current_user.id != id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this user."
        )
        
    db.delete(current_user)
    db.commit()
    return {"detail": "User account successfully deleted."}

@app.get("/messages/{user_id}", response_model=list[MessageResponse])
def get_messages(user_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Fetches message history between current user and target user_id.
    """
    # Verify target user exists
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target user not found."
        )

    # Fetch messages sent by current_user to user_id, or vice-versa
    messages = db.query(Message).filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp.asc()).all()
    
    return messages

@app.delete("/messages/{message_id}", status_code=status.HTTP_200_OK)
def delete_message(message_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Deletes a specific message by message ID.
    Enforces that users can only delete messages they themselves sent (IDOR protection).
    """
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found."
        )
        
    if msg.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this message."
        )
        
    db.delete(msg)
    db.commit()
    return {"detail": "Message deleted successfully."}

# --- WebSocket Realtime Chat Handler ---
@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT Bearer Token"),
    db: Session = Depends(get_db)
):
    """
    Real-time WebSocket chat connection endpoint.
    Decodes token, validates user existence and active session (logout timing check).
    """
    # 1. Authenticate Token manually (WebSockets handshake cannot use custom HTTP Auth headers easily)
    try:
        payload = decode_jwt(token)
        user_id = int(payload.get("sub"))
        token_iat = float(payload.get("iat"))
    except Exception as e:
        # Policy violation close code (1008)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid authentication token")
        return

    # 2. Get User and verify active status
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User not found")
        return
        
    token_iat_dt = datetime.utcfromtimestamp(token_iat)
    if token_iat_dt.replace(microsecond=0) < user.last_logout_at.replace(microsecond=0):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session expired. Please reconnect.")
        return

    # Accept the socket and join the manager
    await manager.connect(user.id, websocket)
    
    try:
        while True:
            # Expecting message input in JSON: {"receiver_id": int, "content": str}
            data = await websocket.receive_json()
            
            try:
                msg_create = MessageCreate(**data)
            except Exception as val_error:
                await websocket.send_json({"error": "Invalid format", "details": str(val_error)})
                continue
            
            # Verify target receiver exists
            receiver = db.query(User).filter(User.id == msg_create.receiver_id).first()
            if not receiver:
                await websocket.send_json({"error": f"Receiver with ID {msg_create.receiver_id} does not exist"})
                continue
            
            # Save message to database
            db_message = Message(
                sender_id=user.id,
                receiver_id=receiver.id,
                content=msg_create.content
            )
            db.add(db_message)
            db.commit()
            db.refresh(db_message)
            
            payload_response = {
                "id": db_message.id,
                "sender_id": db_message.sender_id,
                "receiver_id": db_message.receiver_id,
                "content": db_message.content,
                "timestamp": db_message.timestamp.isoformat()
            }
            
            # Broadcast to receiver
            await manager.send_to_user(receiver.id, {
                "type": "message",
                "data": payload_response
            })
            
            # Confirm back to sender
            await websocket.send_json({
                "type": "receipt",
                "data": payload_response
            })
            
    except Exception as e:
        logging.info(f"WebSocket connection closed or encountered error for user {user.id}: {str(e)}")
    finally:
        manager.disconnect(user.id, websocket)