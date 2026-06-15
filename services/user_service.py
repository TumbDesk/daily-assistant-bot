"""Global user profiles and messenger identities."""
import os
import uuid
from typing import Optional

from sqlalchemy import func, select

from database import User, UserIdentity, get_session

PLATFORM_TELEGRAM = "telegram"


def visible_context_chat_id(chat_id: int, platform_user_id: int) -> int:
    """Visibility scope: group (negative id) or private Telegram chat."""
    return chat_id if chat_id < 0 else platform_user_id


def event_source_label(
    event_context_chat_id: int,
    view_context_chat_id: int,
) -> str | None:
    if event_context_chat_id == view_context_chat_id:
        return None
    from services.chat_membership_service import get_chat_membership_service

    return get_chat_membership_service().get_chat_display_name(event_context_chat_id)


class UserService:
    def __init__(self) -> None:
        self.admin_platform_user_id = str(int(os.environ["ADMIN_ID"]))

    def _whitelist_empty(self, session) -> bool:
        count = session.scalar(select(func.count()).select_from(User))
        return count == 0

    def get_identity(
        self, platform: str, platform_user_id: str
    ) -> Optional[UserIdentity]:
        with get_session() as session:
            stmt = select(UserIdentity).where(
                UserIdentity.platform == platform,
                UserIdentity.platform_user_id == platform_user_id,
            )
            return session.scalars(stmt).first()

    def get_global_user_id(
        self, platform: str, platform_user_id: str
    ) -> Optional[str]:
        with get_session() as session:
            stmt = select(UserIdentity.user_id).where(
                UserIdentity.platform == platform,
                UserIdentity.platform_user_id == platform_user_id,
            )
            return session.scalar(stmt)

    def is_allowed(self, platform: str, platform_user_id: str) -> bool:
        if (
            platform == PLATFORM_TELEGRAM
            and platform_user_id == self.admin_platform_user_id
        ):
            return True
        with get_session() as session:
            if self._whitelist_empty(session):
                return False
            stmt = select(UserIdentity.id).where(
                UserIdentity.platform == platform,
                UserIdentity.platform_user_id == platform_user_id,
            )
            return session.scalar(stmt) is not None

    def is_admin(self, platform: str, platform_user_id: str) -> bool:
        if (
            platform == PLATFORM_TELEGRAM
            and platform_user_id == self.admin_platform_user_id
        ):
            return True
        with get_session() as session:
            stmt = (
                select(User.is_admin)
                .join(UserIdentity, UserIdentity.user_id == User.id)
                .where(
                    UserIdentity.platform == platform,
                    UserIdentity.platform_user_id == platform_user_id,
                )
            )
            return bool(session.scalar(stmt))

    def ensure_bootstrap_admin(
        self, platform: str, platform_user_id: str, display_name: Optional[str]
    ) -> Optional[str]:
        """Create admin user and identity; returns global user_id."""
        if platform != PLATFORM_TELEGRAM or platform_user_id != self.admin_platform_user_id:
            return None
        name = display_name or f"Admin {platform_user_id}"
        with get_session() as session:
            stmt = select(UserIdentity).where(
                UserIdentity.platform == platform,
                UserIdentity.platform_user_id == platform_user_id,
            )
            identity = session.scalars(stmt).first()
            if identity:
                user = session.get(User, identity.user_id)
                if user:
                    user.name = name
                    user.is_admin = True
                return identity.user_id

            user = User(name=name, is_admin=True)
            session.add(user)
            session.flush()
            session.add(
                UserIdentity(
                    user_id=user.id,
                    platform=platform,
                    platform_user_id=platform_user_id,
                )
            )
            return user.id

    def resolve_user_id(
        self, platform: str, platform_user_id: str, display_name: Optional[str]
    ) -> Optional[str]:
        if not self.is_allowed(platform, platform_user_id):
            return None
        admin_id = self.ensure_bootstrap_admin(platform, platform_user_id, display_name)
        if admin_id:
            return admin_id
        return self.get_global_user_id(platform, platform_user_id)

    def add_allowed_user(
        self,
        admin_platform_user_id: str,
        target_platform_user_id: str,
        name: str,
        *,
        platform: str = PLATFORM_TELEGRAM,
    ) -> tuple[bool, str]:
        if not self.is_admin(platform, admin_platform_user_id):
            from views.message_factory import MessageFactory

            return False, MessageFactory.allow_denied(
                locale=MessageFactory.DEFAULT_LOCALE
            )

        with get_session() as session:
            stmt = select(UserIdentity).where(
                UserIdentity.platform == platform,
                UserIdentity.platform_user_id == target_platform_user_id,
            )
            identity = session.scalars(stmt).first()
            if identity:
                user = session.get(User, identity.user_id)
                if user:
                    user.name = name
            else:
                user = User(name=name, is_admin=False)
                session.add(user)
                session.flush()
                session.add(
                    UserIdentity(
                        user_id=user.id,
                        platform=platform,
                        platform_user_id=target_platform_user_id,
                    )
                )

        from views.message_factory import MessageFactory

        return True, MessageFactory.allow_success(
            int(target_platform_user_id),
            name,
            locale=MessageFactory.DEFAULT_LOCALE,
        )

    def get_platform_user_id_for_owner(
        self, owner_id: str, platform: str = PLATFORM_TELEGRAM
    ) -> Optional[str]:
        with get_session() as session:
            stmt = select(UserIdentity.platform_user_id).where(
                UserIdentity.user_id == owner_id,
                UserIdentity.platform == platform,
            )
            return session.scalar(stmt)

    def has_home_location(self, user_id: str) -> bool:
        return self.get_home_location(user_id) is not None

    def get_home_location(
        self, user_id: str
    ) -> Optional[tuple[float, float, str]]:
        with get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                return None
            if (
                user.home_latitude is None
                or user.home_longitude is None
                or not user.home_location_name
            ):
                return None
            return (user.home_latitude, user.home_longitude, user.home_location_name)

    def set_home_location(
        self,
        user_id: str,
        latitude: float,
        longitude: float,
        location_name: str,
    ) -> bool:
        with get_session() as session:
            user = session.get(User, user_id)
            if user is None:
                return False
            user.home_latitude = latitude
            user.home_longitude = longitude
            user.home_location_name = location_name
            return True


_user_service: Optional[UserService] = None


def get_user_service() -> UserService:
    global _user_service
    if _user_service is None:
        _user_service = UserService()
    return _user_service
