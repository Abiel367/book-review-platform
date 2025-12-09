from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum

# Genre options
class Genre(str, Enum):
    FICTION = "Fiction"
    NON_FICTION = "Non-Fiction"
    MYSTERY = "Mystery"
    ROMANCE = "Romance"
    SCIENCE_FICTION = "Science Fiction"
    FANTASY = "Fantasy"
    BIOGRAPHY = "Biography"
    HISTORY = "History"
    SELF_HELP = "Self-Help"
    YOUNG_ADULT = "Young Adult"

# User model
class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    full_name: str = Field(index=True)
    pin_code: str = Field(min_length=4, max_length=4)  # 4-digit PIN
    role: str = Field(default="user")  # "user" or "admin"
    created_at: datetime = Field(default_factory=datetime.utcnow)

# Review model
class Review(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    book_title: str
    author: str
    rating: int = Field(ge=1, le=5)  # 1-5 stars
    review_text: str
    genre: Genre  # Using Enum
    is_archived: bool = Field(default=False)  # For admin soft delete
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

# Request/Response models
class UserRegister(SQLModel):
    full_name: str

class UserLogin(SQLModel):
    full_name: str
    pin_code: str

class ReviewCreate(SQLModel):
    book_title: str
    author: str
    rating: int
    review_text: str
    genre: Genre

class ReviewUpdate(SQLModel):
    book_title: Optional[str] = None
    author: Optional[str] = None
    rating: Optional[int] = None
    review_text: Optional[str] = None
    genre: Optional[Genre] = None

class UserResponse(SQLModel):
    id: int
    full_name: str
    role: str
    created_at: datetime

class ReviewResponse(SQLModel):
    id: int
    user_id: int
    book_title: str
    author: str
    rating: int
    review_text: str
    genre: str
    created_at: datetime
    updated_at: datetime
    user_name: str  # We'll populate this

class Token(SQLModel):
    access_token: str
    token_type: str
    user: UserResponse