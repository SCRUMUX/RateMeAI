"""Admin tool — grant image_credits to a user by external identity.

Reads ``DATABASE_URL`` from the environment (same source as the app) and
works against any environment: local dev, Railway ``app`` service, or a
Postgres URL pasted on the command line. Intentionally a standalone
script (not an HTTP endpoint) so it never accidentally becomes a public
attack surface.

Examples:

  # Dry-run against the currently configured DATABASE_URL — prints
  # candidates without touching anything.
  python -m scripts.grant_credits --provider telegram --username scrumux --amount 100 --dry-run

  # Grant 100 credits to the Telegram user @scrumux. If multiple users
  # match the username, the script exits with a list and asks for
  # --telegram-id to disambiguate.
  python -m scripts.grant_credits --provider telegram --username scrumux --amount 100 --yes

  # Grant 100 credits to a VK ID account whose first_name is Владимир.
  # If multiple candidates come back, pass --vk-id to lock in the exact
  # account (the script prints the external_id for each candidate).
  python -m scripts.grant_credits --provider vk_id --first-name "Владимир" --amount 100 --yes

Invariants:

  * Updates are transactional — credits and the audit row land in the
    same commit. A failure rolls everything back.
  * ``CreditTransaction.tx_type`` is ``"admin_grant"`` so these top-ups
    are filterable separately from paid ``"purchase"`` rows during
    reconciliation (``src/services/reconciliation.py``).
  * Nothing leaks PII to stdout beyond what the admin already typed in
    to look the user up.

Run ``python -m scripts.grant_credits --help`` for the full flag list.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.config import settings
from src.models.db import CreditTransaction, User, UserIdentity


_VALID_PROVIDERS = ("vk_id", "telegram")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="grant_credits",
        description=(
            "Grant image_credits to a user identified by provider + "
            "external_id / username / first_name."
        ),
    )
    p.add_argument(
        "--provider",
        required=True,
        choices=_VALID_PROVIDERS,
        help="Which external identity namespace to search in.",
    )
    p.add_argument(
        "--amount",
        type=int,
        default=100,
        help="How many image_credits to add (default: 100).",
    )
    p.add_argument(
        "--username",
        help=(
            "Telegram @username (without the leading @). For telegram "
            "provider, the script first checks UserIdentity.profile_data "
            "and then falls back to the legacy User.username column."
        ),
    )
    p.add_argument(
        "--first-name",
        help=(
            "VK first_name to match (case-insensitive prefix). Use this "
            "when you don't know the VK user_id yet. If multiple "
            "candidates match, the script lists them and exits."
        ),
    )
    p.add_argument(
        "--telegram-id",
        help=(
            "Exact Telegram numeric user id. Bypasses username search; "
            "always preferred for uniqueness."
        ),
    )
    p.add_argument(
        "--vk-id",
        dest="vk_id_value",
        help=(
            "Exact VK ID external_id. Use this to disambiguate when "
            "multiple --first-name candidates come back."
        ),
    )
    p.add_argument(
        "--database-url",
        help=(
            "Override DATABASE_URL. Handy for one-shot runs against a "
            "different environment without exporting the env var."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Look up candidates but do not write anything.",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt when exactly one user matches.",
    )
    return p.parse_args(argv)


async def _find_candidates(
    db, provider: str, args: argparse.Namespace
) -> list[tuple[User, UserIdentity | None]]:
    """Return a list of (User, UserIdentity) pairs matching the filters.

    Each branch uses the most specific key the caller supplied first.
    """
    candidates: list[tuple[User, UserIdentity | None]] = []

    if provider == "telegram":
        if args.telegram_id:
            ext_id = args.telegram_id.strip()
            q = (
                select(User, UserIdentity)
                .join(
                    UserIdentity,
                    UserIdentity.user_id == User.id,
                    isouter=True,
                )
                .where(
                    (UserIdentity.provider == "telegram")
                    & (UserIdentity.external_id == ext_id)
                )
            )
            for row in (await db.execute(q)).all():
                candidates.append((row[0], row[1]))
            if not candidates:
                try:
                    tg_int = int(ext_id)
                except ValueError:
                    tg_int = None
                if tg_int is not None:
                    q2 = select(User).where(User.telegram_id == tg_int)
                    for u in (await db.execute(q2)).scalars().all():
                        candidates.append((u, None))
            return candidates

        if args.username:
            uname = args.username.strip().lstrip("@").lower()
            q = (
                select(User, UserIdentity)
                .join(
                    UserIdentity,
                    UserIdentity.user_id == User.id,
                )
                .where(UserIdentity.provider == "telegram")
            )
            for row in (await db.execute(q)).all():
                identity: UserIdentity = row[1]
                data = identity.profile_data or {}
                pd_username = str(data.get("username") or "").strip().lstrip("@").lower()
                if pd_username == uname:
                    candidates.append((row[0], identity))

            q_legacy = select(User).where(
                User.username.isnot(None),
            )
            for u in (await db.execute(q_legacy)).scalars().all():
                if (u.username or "").strip().lstrip("@").lower() == uname and not any(
                    c[0].id == u.id for c in candidates
                ):
                    candidates.append((u, None))
            return candidates

        raise SystemExit(
            "--provider telegram requires --username or --telegram-id"
        )

    if args.vk_id_value:
        ext_id = args.vk_id_value.strip()
        q = (
            select(User, UserIdentity)
            .join(UserIdentity, UserIdentity.user_id == User.id)
            .where(
                (UserIdentity.provider == "vk_id")
                & (UserIdentity.external_id == ext_id)
            )
        )
        for row in (await db.execute(q)).all():
            candidates.append((row[0], row[1]))
        return candidates

    if args.first_name:
        needle = args.first_name.strip().lower()
        q = (
            select(User, UserIdentity)
            .join(UserIdentity, UserIdentity.user_id == User.id)
            .where(UserIdentity.provider == "vk_id")
        )
        for row in (await db.execute(q)).all():
            identity: UserIdentity = row[1]
            data = identity.profile_data or {}
            first = str(data.get("first_name") or "").strip().lower()
            if first == needle or first.startswith(needle):
                candidates.append((row[0], identity))
        return candidates

    raise SystemExit("--provider vk_id requires --first-name or --vk-id")


def _format_candidate(user: User, identity: UserIdentity | None) -> str:
    parts: list[str] = [f"user_id={user.id}"]
    if user.telegram_id is not None:
        parts.append(f"telegram_id={user.telegram_id}")
    if user.username:
        parts.append(f"username=@{user.username}")
    if user.first_name:
        parts.append(f"first_name={user.first_name!r}")
    parts.append(f"credits={user.image_credits}")
    if identity is not None:
        parts.append(f"provider={identity.provider}")
        parts.append(f"external_id={identity.external_id}")
        data: dict[str, Any] = identity.profile_data or {}
        for key in ("username", "first_name", "last_name"):
            val = data.get(key)
            if val:
                parts.append(f"{key}={val!r}")
    return ", ".join(parts)


async def _grant(db, user: User, amount: int) -> int:
    user.image_credits = (user.image_credits or 0) + amount
    db.add(
        CreditTransaction(
            user_id=user.id,
            amount=amount,
            balance_after=user.image_credits,
            tx_type="admin_grant",
            payment_id=None,
        )
    )
    await db.commit()
    await db.refresh(user)
    return user.image_credits


async def _run(args: argparse.Namespace) -> int:
    database_url = (
        args.database_url
        or os.environ.get("DATABASE_URL")
        or settings.database_url
    )
    if not database_url:
        print("ERROR: DATABASE_URL is empty. Set it in env or pass --database-url.", file=sys.stderr)
        return 1

    engine = create_async_engine(database_url, pool_size=1, max_overflow=0)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with maker() as db:
            candidates = await _find_candidates(db, args.provider, args)
            if not candidates:
                print(
                    f"No user found for provider={args.provider} "
                    f"username={args.username!r} first_name={args.first_name!r} "
                    f"telegram_id={args.telegram_id!r} vk_id={args.vk_id_value!r}"
                )
                return 2

            if len(candidates) > 1:
                print(f"Found {len(candidates)} candidates — please disambiguate:")
                for u, ident in candidates:
                    print(f"  • {_format_candidate(u, ident)}")
                print(
                    "\nRe-run with --telegram-id <id> or --vk-id <external_id> "
                    "to pick exactly one."
                )
                return 3

            user, identity = candidates[0]
            print(f"Match: {_format_candidate(user, identity)}")
            print(f"About to add {args.amount} image_credits "
                  f"(new balance would be {user.image_credits + args.amount}).")

            if args.dry_run:
                print("--dry-run: no changes made.")
                return 0

            if not args.yes:
                reply = input("Confirm (y/N)? ").strip().lower()
                if reply not in ("y", "yes"):
                    print("Aborted.")
                    return 0

            new_balance = await _grant(db, user, args.amount)
            print(
                f"OK. user_id={user.id} credits: "
                f"{new_balance - args.amount} → {new_balance} "
                f"(+{args.amount}, tx_type=admin_grant)."
            )
            return 0
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
