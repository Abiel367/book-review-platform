from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status
from sqlmodel import Session, select
from database import get_session
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from models import User
import random

# Use HTTPBearer instead of OAuth2PasswordBearer
security = HTTPBearer(auto_error=False)

SECRET_KEY = "your-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24  # 24 hours 

# Store failed login attempts (in production, use Redis)
failed_attempts = {}

def generate_pin():
    """Generate random 4-digit PIN"""
    return str(random.randint(0, 9999)).zfill(4)

def check_failed_attempts(full_name: str):
    """Check if user has exceeded failed attempts"""
    if full_name in failed_attempts:
        attempts, lock_time = failed_attempts[full_name]
        if attempts >= 3:
            # Check if 30 minutes have passed since lockout
            if (datetime.utcnow() - lock_time).seconds < 1800:  # 30 minutes
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Account locked: Too many failed attempts. Try again later."
                )
            else:
                # Reset after 30 minutes
                del failed_attempts[full_name]

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire, "sub": data.get("full_name")})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    session: Session = Depends(get_session)
):
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        full_name: str = payload.get("sub")
        if full_name is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = session.exec(select(User).where(User.full_name == full_name)).first()
    if user is None:
        raise credentials_exception
    return user

def verify_pin(full_name: str, pin_code: str, session: Session):
    """Verify PIN and handle failed attempts"""
    check_failed_attempts(full_name)
    
    # Case-insensitive name matching
    user = session.exec(
        select(User).where(User.full_name.ilike(full_name))
    ).first()
    
    if not user or user.pin_code != pin_code:
        # Track failed attempt
        if full_name in failed_attempts:
            attempts, _ = failed_attempts[full_name]
            failed_attempts[full_name] = (attempts + 1, datetime.utcnow())
        else:
            failed_attempts[full_name] = (1, datetime.utcnow())
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN: Please check your PIN and try again"
        )
    
    # Reset failed attempts on successful login
    if full_name in failed_attempts:
        del failed_attempts[full_name]
    
    return user