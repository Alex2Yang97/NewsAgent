import asyncio
from sqlalchemy import select
from db.database import AsyncSessionLocal
from models.models import User
from passlib.context import CryptContext

async def get_user_by_id(id: int = 1):
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).filter_by(id=id))
        return result.scalar_one()