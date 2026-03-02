from sqlalchemy.orm import Session
from app.models.user import User
from typing import Dict


def get_or_create_user(db: Session, clerk_user: Dict) -> User:
    """Get or create user from Clerk auth data"""
    user = db.query(User).filter(User.clerk_id == clerk_user["user_id"]).first()

    if not user:
        user = User(
            clerk_id=clerk_user["user_id"],
            email=clerk_user.get("email"),
            first_name=clerk_user.get("first_name"),
            last_name=clerk_user.get("last_name")
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user
