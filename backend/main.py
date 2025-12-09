from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime
import time  
from sqlalchemy.exc import OperationalError  

from models import (
    User, Review, UserRegister, UserLogin, ReviewCreate, 
    ReviewUpdate, UserResponse, ReviewResponse, Token, Genre
)
from database import engine, get_session
from auth import (
    create_access_token, get_current_user, 
    verify_pin, generate_pin
)
import sqlmodel

# Create tables
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Wait for database to be ready
    max_retries = 10
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            sqlmodel.SQLModel.metadata.create_all(engine)
            print("Database connected successfully!")
            break
        except OperationalError:
            if attempt < max_retries - 1:
                print(f"Database not ready, retrying in {retry_delay}s... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(retry_delay)
            else:
                print("Failed to connect to database after maximum retries")
                raise
    
    # Create default admin if not exists
    with Session(engine) as session:
        admin = session.exec(
            select(User).where(User.full_name == "Abiel Robinson")
        ).first()
        if not admin:
            admin = User(
                full_name="Abiel Robinson",
                pin_code="0000",
                role="admin"
            )
            session.add(admin)
            session.commit()
            print("Default admin user created")
    
    yield
app = FastAPI(
    title="Book Review Platform",
    description="API for book review platform with PIN-based authentication",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== AUTHENTICATION ENDPOINTS =====
@app.post("/auth/register", response_model=dict)
def register_user(
    user_data: UserRegister,
    session: Session = Depends(get_session)
):
    """Register a new user with auto-generated PIN"""
    # Generate unique PIN for this name
    pin = generate_pin()
    
    # Check if name+pin combo already exists
    existing = session.exec(
        select(User).where(
            (User.full_name == user_data.full_name) & 
            (User.pin_code == pin)
        )
    ).first()
    
    attempts = 0
    while existing and attempts < 100:
        pin = generate_pin()
        existing = session.exec(
            select(User).where(
                (User.full_name == user_data.full_name) & 
                (User.pin_code == pin)
            )
        ).first()
        attempts += 1
    
    if attempts >= 100:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate unique PIN"
        )
    
    # Create user
    user = User(
        full_name=user_data.full_name,
        pin_code=pin,
        role="user"
    )
    
    session.add(user)
    session.commit()
    session.refresh(user)
    
    return {
        "message": "Registration successful",
        "pin": pin,
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "role": user.role
        }
    }

@app.post("/auth/login", response_model=Token)
def login_user(
    login_data: UserLogin,
    session: Session = Depends(get_session)
):
    """Login with name and PIN"""
    user = verify_pin(login_data.full_name, login_data.pin_code, session)
    
    # Create token
    access_token = create_access_token({
        "full_name": user.full_name,
        "role": user.role,
        "user_id": user.id
    })
    
    user_response = UserResponse(
        id=user.id,
        full_name=user.full_name,
        role=user.role,
        created_at=user.created_at
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=user_response
    )

@app.post("/auth/admin/login", response_model=Token)
def admin_login(
    login_data: UserLogin,
    session: Session = Depends(get_session)
):
    """Admin login (same as user but checks role)"""
    user = verify_pin(login_data.full_name, login_data.pin_code, session)
    
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    access_token = create_access_token({
        "full_name": user.full_name,
        "role": user.role,
        "user_id": user.id
    })
    
    user_response = UserResponse(
        id=user.id,
        full_name=user.full_name,
        role=user.role,
        created_at=user.created_at
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        user=user_response
    )

# ===== USER ENDPOINTS =====
@app.get("/reviews", response_model=List[ReviewResponse])
def get_reviews(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    genre: Optional[Genre] = None,
    rating: Optional[int] = Query(None, ge=1, le=5),
    my_reviews: bool = False,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get reviews with search and filters"""
    query = select(Review, User.full_name).join(User)
    
    # Only show active reviews unless admin
    if current_user.role != "admin":
        query = query.where(Review.is_archived == False)
    
    # Filter by user's own reviews
    if my_reviews:
        query = query.where(Review.user_id == current_user.id)
    
    # Search in title, author, or review text
    if search:
        query = query.where(
            (Review.book_title.ilike(f"%{search}%")) |
            (Review.author.ilike(f"%{search}%")) |
            (Review.review_text.ilike(f"%{search}%"))
        )
    
    # Filter by genre
    if genre:
        query = query.where(Review.genre == genre)
    
    # Filter by rating
    if rating:
        query = query.where(Review.rating == rating)
    
    query = query.offset(skip).limit(limit)
    results = session.exec(query).all()
    
    return [
        ReviewResponse(
            id=review.id,
            user_id=review.user_id,
            book_title=review.book_title,
            author=review.author,
            rating=review.rating,
            review_text=review.review_text,
            genre=review.genre,
            created_at=review.created_at,
            updated_at=review.updated_at,
            user_name=user_name
        )
        for review, user_name in results
    ]

@app.get("/reviews/my-reviews", response_model=List[ReviewResponse])
def get_my_reviews(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get current user's reviews"""
    return get_reviews(my_reviews=True, session=session, current_user=current_user)

@app.post("/reviews", response_model=ReviewResponse)
def create_review(
    review_data: ReviewCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Create a new review"""
    review = Review(
        **review_data.dict(),
        user_id=current_user.id
    )
    
    session.add(review)
    session.commit()
    session.refresh(review)
    
    # Get user name for response
    user = session.get(User, review.user_id)
    
    return ReviewResponse(
        **review.dict(),
        user_name=user.full_name
    )

@app.put("/reviews/{review_id}", response_model=ReviewResponse)
def update_review(
    review_id: int,
    review_data: ReviewUpdate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Update a review (only owner can update)"""
    review = session.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # Check ownership
    if review.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only edit your own reviews"
        )
    
    # Update fields
    update_data = review_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(review, field, value)
    
    review.updated_at = datetime.utcnow()
    session.add(review)
    session.commit()
    session.refresh(review)
    
    # Get user name
    user = session.get(User, review.user_id)
    
    return ReviewResponse(
        **review.dict(),
        user_name=user.full_name
    )

@app.delete("/reviews/{review_id}")
def delete_review(
    review_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Delete a review (owner or admin)"""
    review = session.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    # Check ownership or admin
    if review.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only delete your own reviews"
        )
    
    session.delete(review)
    session.commit()
    
    return {"message": "Review deleted successfully"}

# ===== ADMIN ENDPOINTS =====
@app.get("/admin/reviews", response_model=List[ReviewResponse])
def get_all_reviews(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all reviews (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    return get_reviews(session=session, current_user=current_user)

@app.post("/admin/reviews/{review_id}/archive")
def archive_review(
    review_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Archive a review (admin only - soft delete)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    review = session.get(Review, review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    
    review.is_archived = True
    review.updated_at = datetime.utcnow()
    
    session.add(review)
    session.commit()
    
    return {"message": "Review archived successfully"}

@app.get("/admin/users", response_model=List[UserResponse])
def get_all_users(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Get all users (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    users = session.exec(select(User)).all()
    return users

@app.delete("/admin/users/{user_id}")
def delete_user(
    user_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user)
):
    """Delete a user (admin only)"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent admin from deleting themselves
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    session.delete(user)
    session.commit()
    
    return {"message": "User deleted successfully"}

# ===== HEALTH CHECK =====
@app.get("/")
def read_root():
    return {"message": "Book Review Platform API is running"}

@app.get("/health")
def health_check():
    return {"status": "healthy"}