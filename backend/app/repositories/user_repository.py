"""UserRepositoryImpl — SQLAlchemy adapter for user accounts.

Implements the ``UserRepository`` port. Like the other repositories it never
commits — the Unit of Work owns the transaction. Email lookups are normalized to
lower-case to match how ``User.register`` stores them.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.repositories import UserRepository
from app.domain.entities.user import User
from app.infrastructure.database.mappers import model_to_user, user_to_model
from app.infrastructure.database.models.user import UserModel


class UserRepositoryImpl(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> User:
        self._session.add(user_to_model(user))
        await self._session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(UserModel).where(
            UserModel.id == user_id, UserModel.deleted_at.is_(None)
        )
        model = await self._session.scalar(stmt)
        return model_to_user(model) if model is not None else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(
            UserModel.email == email.strip().lower(), UserModel.deleted_at.is_(None)
        )
        model = await self._session.scalar(stmt)
        return model_to_user(model) if model is not None else None
