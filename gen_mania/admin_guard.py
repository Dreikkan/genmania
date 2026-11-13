"""Owner-only guard for admin modals."""
from __future__ import annotations

from typing import Callable


def guard_admin_modal(
    modal_cls,
    is_owner: Callable,
    message: str,
):
    """Оборачивает on_submit модалки проверкой владельца бота."""
    original = modal_cls.on_submit

    async def guarded(self, interaction):
        guild = getattr(interaction, "guild", None)
        if guild is not None and getattr(guild, "owner_id", None) is not None:
            if not await is_owner(interaction):
                return await interaction.response.send_message(
                    message, ephemeral=True
                )
        return await original(self, interaction)

    guarded.__name__ = getattr(original, "__name__", "on_submit")
    modal_cls.on_submit = guarded
    return modal_cls
