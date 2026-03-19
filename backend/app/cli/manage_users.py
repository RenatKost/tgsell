"""CLI utility for managing user roles.

Usage:
    # Make user admin by telegram_id:
    python -m app.cli.manage_users admin 123456789

    # Make user moderator:
    python -m app.cli.manage_users moderator 123456789

    # List all admins/moderators:
    python -m app.cli.manage_users list
"""
import asyncio
import sys

from sqlalchemy import select, or_

from app.database import async_session
from app.models.user import User, UserRole
# Import all models so relationships resolve
import app.models.channel  # noqa: F401
import app.models.deal  # noqa: F401


async def set_role(telegram_id: int, role: UserRole):
    async with async_session() as db:
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()

        if not user:
            print(f"Користувач з telegram_id={telegram_id} не знайдений.")
            print("Спочатку користувач повинен увійти на сайт.")
            return

        user.role = role
        await db.commit()
        print(f"Користувач @{user.username or user.first_name} (id={user.id}) — роль змінена на '{role.value}'")


async def list_staff():
    async with async_session() as db:
        result = await db.execute(
            select(User).where(
                or_(User.role == UserRole.admin, User.role == UserRole.moderator)
            )
        )
        users = result.scalars().all()

        if not users:
            print("Адміністраторів та модераторів не знайдено.")
            print("Використайте: python -m app.cli.manage_users admin <telegram_id>")
            return

        print(f"{'ID':<6} {'Telegram ID':<14} {'Username':<20} {'Роль':<12}")
        print("-" * 52)
        for u in users:
            print(f"{u.id:<6} {u.telegram_id:<14} @{u.username or '-':<19} {u.role.value:<12}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()

    if command == "list":
        asyncio.run(list_staff())
    elif command in ("admin", "moderator"):
        if len(sys.argv) < 3:
            print(f"Вкажіть telegram_id: python -m app.cli.manage_users {command} <telegram_id>")
            return
        telegram_id = int(sys.argv[2])
        role = UserRole.admin if command == "admin" else UserRole.moderator
        asyncio.run(set_role(telegram_id, role))
    elif command == "user":
        if len(sys.argv) < 3:
            print("Вкажіть telegram_id: python -m app.cli.manage_users user <telegram_id>")
            return
        telegram_id = int(sys.argv[2])
        asyncio.run(set_role(telegram_id, UserRole.user))
    else:
        print(f"Невідома команда: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()
