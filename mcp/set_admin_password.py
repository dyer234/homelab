# Run inside the contextforge container by `make admin-password`: sets the
# admin UI password to whatever arrives on stdin. The UI's forgot-password
# link can't work here (it emails a reset token and there is no SMTP), and
# PLATFORM_ADMIN_PASSWORD only seeds the account on first start.
import asyncio
import os
import sys

from mcpgateway.db import SessionLocal
from mcpgateway.services.email_auth_service import EmailAuthService

password = sys.stdin.read().rstrip("\n")
if not password:
    sys.exit("no password on stdin")
email = os.environ["PLATFORM_ADMIN_EMAIL"]


async def main():
    db = SessionLocal()
    try:
        await EmailAuthService(db).update_user(email, password=password, password_change_required=False)
    finally:
        db.close()


asyncio.run(main())
print(f"password updated for {email}")
