"""Group membership for cross-channel visibility in direct chat."""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from telegram import ChatMember
from telegram.error import TelegramError

from database import BotChat, Event, UserChatMembership, get_session
from services.source_label import SOURCE_GROUP_FALLBACK, SOURCE_PRIVATE_INTERNAL
from services.timezone_util import now

logger = logging.getLogger(__name__)

_ACTIVE_MEMBER_STATUSES = frozenset(
    {
        ChatMember.MEMBER,
        ChatMember.ADMINISTRATOR,
        ChatMember.OWNER,
    }
)


class ChatMembershipService:
    def record_bot_joined(self, context_chat_id: int, title: str | None = None) -> None:
        if context_chat_id >= 0:
            return
        with get_session() as session:
            existing = session.get(BotChat, context_chat_id)
            if existing is None:
                session.add(
                    BotChat(
                        context_chat_id=context_chat_id,
                        title=title,
                    )
                )
            elif title and existing.title != title:
                existing.title = title

    def record_user_seen(self, platform_user_id: int, context_chat_id: int) -> None:
        if context_chat_id >= 0:
            return
        self.record_bot_joined(context_chat_id)
        pid = str(platform_user_id)
        with get_session() as session:
            existing = session.scalar(
                select(UserChatMembership)
                .where(UserChatMembership.platform_user_id == pid)
                .where(UserChatMembership.context_chat_id == context_chat_id)
            )
            if existing is None:
                session.add(
                    UserChatMembership(
                        platform_user_id=pid,
                        context_chat_id=context_chat_id,
                        verified_at=now(),
                    )
                )
            else:
                existing.verified_at = now()

    def _upsert_membership(
        self, platform_user_id: int, context_chat_id: int, verified_at: datetime
    ) -> None:
        pid = str(platform_user_id)
        with get_session() as session:
            existing = session.scalar(
                select(UserChatMembership)
                .where(UserChatMembership.platform_user_id == pid)
                .where(UserChatMembership.context_chat_id == context_chat_id)
            )
            if existing is None:
                session.add(
                    UserChatMembership(
                        platform_user_id=pid,
                        context_chat_id=context_chat_id,
                        verified_at=verified_at,
                    )
                )
            else:
                existing.verified_at = verified_at

    def _remove_membership(self, platform_user_id: int, context_chat_id: int) -> None:
        pid = str(platform_user_id)
        with get_session() as session:
            row = session.scalar(
                select(UserChatMembership)
                .where(UserChatMembership.platform_user_id == pid)
                .where(UserChatMembership.context_chat_id == context_chat_id)
            )
            if row is not None:
                session.delete(row)

    def list_member_group_ids(self, platform_user_id: int) -> list[int]:
        pid = str(platform_user_id)
        with get_session() as session:
            rows = session.scalars(
                select(UserChatMembership.context_chat_id)
                .where(UserChatMembership.platform_user_id == pid)
                .order_by(UserChatMembership.context_chat_id.asc())
            ).all()
            return list(rows)

    def get_visible_context_ids(self, platform_user_id: int) -> frozenset[int]:
        group_ids = self.list_member_group_ids(platform_user_id)
        return frozenset([platform_user_id, *group_ids])

    def get_chat_display_name(self, context_chat_id: int) -> str:
        if context_chat_id >= 0:
            return SOURCE_PRIVATE_INTERNAL
        with get_session() as session:
            row = session.get(BotChat, context_chat_id)
            if row is not None and row.title:
                return row.title
        return SOURCE_GROUP_FALLBACK

    async def _refresh_group_title(self, bot, group_id: int) -> None:
        with get_session() as session:
            row = session.get(BotChat, group_id)
            if row is not None and row.title:
                return
        try:
            chat = await bot.get_chat(group_id)
        except TelegramError:
            logger.debug(
                "Gruppentitel nicht abrufbar: group=%s", group_id, exc_info=True
            )
            return
        if chat.title:
            self.record_bot_joined(group_id, chat.title)

    def bootstrap_bot_chats_from_events(self) -> None:
        """Adopt known groups from existing events (migration)."""
        with get_session() as session:
            group_ids = session.scalars(
                select(Event.context_chat_id)
                .where(Event.context_chat_id < 0)
                .distinct()
            ).all()
        for group_id in group_ids:
            if group_id is not None:
                self.record_bot_joined(group_id)

    async def sync_memberships(self, bot, platform_user_id: int) -> frozenset[int]:
        self.bootstrap_bot_chats_from_events()
        verified_at = now()
        with get_session() as session:
            group_ids = list(
                session.scalars(select(BotChat.context_chat_id)).all()
            )

        active_groups: list[int] = []
        for group_id in group_ids:
            await self._refresh_group_title(bot, group_id)
            try:
                member = await bot.get_chat_member(group_id, platform_user_id)
            except TelegramError:
                logger.debug(
                    "Mitgliedschaftsprüfung fehlgeschlagen: user=%s group=%s",
                    platform_user_id,
                    group_id,
                    exc_info=True,
                )
                self._remove_membership(platform_user_id, group_id)
                continue

            if member.status in _ACTIVE_MEMBER_STATUSES:
                self._upsert_membership(platform_user_id, group_id, verified_at)
                active_groups.append(group_id)
            else:
                self._remove_membership(platform_user_id, group_id)

        return frozenset([platform_user_id, *active_groups])


_chat_membership_service: Optional[ChatMembershipService] = None


def get_chat_membership_service() -> ChatMembershipService:
    global _chat_membership_service
    if _chat_membership_service is None:
        _chat_membership_service = ChatMembershipService()
    return _chat_membership_service
