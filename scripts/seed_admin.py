"""Seed the first BarnSight admin user.

Usage:
  uv run python scripts/seed_admin.py
"""

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
  sys.path.insert(0, str(SRC))

from app.core.database import MongoClient  # noqa: E402
from app.core.schemas.admin import AdminCreate  # noqa: E402
from app.crud import UserCRUD  # noqa: E402


async def main() -> None:
  username = os.getenv("BARNSIGHT_ADMIN_USERNAME", "admin")
  email = os.getenv("BARNSIGHT_ADMIN_EMAIL", "admin@barnsight.local")
  password = os.getenv("BARNSIGHT_ADMIN_PASSWORD")
  if not password:
    raise RuntimeError("Set BARNSIGHT_ADMIN_PASSWORD before running the seed script.")

  await MongoClient.connect()
  try:
    db = MongoClient._client.get_database("users")
    crud = UserCRUD(db)
    if await crud.find(username=username):
      print(f"Admin user {username!r} already exists.")
      return
    admin = AdminCreate(
      username=username,
      email=email,
      password=password,
      first_name=os.getenv("BARNSIGHT_ADMIN_FIRST_NAME", "BarnSight"),
      middle_name="",
      last_name=os.getenv("BARNSIGHT_ADMIN_LAST_NAME", "Admin"),
      role="admins",
      scopes=["admin"],
    )
    await crud.create(admin)
    print(f"Created admin user {username!r}.")
  finally:
    await MongoClient.close()


if __name__ == "__main__":
  asyncio.run(main())
