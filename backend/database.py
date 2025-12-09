import os
from sqlmodel import create_engine, Session

# Use environment variable for Docker, fallback to local
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://user1:password1@localhost:54325/resilience_db"
)

engine = create_engine(DATABASE_URL)

def get_session():
    with Session(engine) as session:
        yield session