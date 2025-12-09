from sqlmodel import create_engine, Session

DATABASE_URL = "postgresql://user1:password1@localhost:54325/resilience_db"
engine = create_engine(DATABASE_URL)

def get_session():
    with Session(engine) as session:
        yield session