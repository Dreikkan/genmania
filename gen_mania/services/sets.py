"""Generator set synergy calculations and embed."""
from __future__ import annotations

import logging
from typing import Any, Callable


class SetRuntime:
    """Адаптер между bot.py и сервисом сетов."""

    def __init__(self):
        self._db_getter: Callable[[], Any] = lambda: None
        self._grid_size_getter: Callable[[], Callable] = lambda: None
        self._embed_factory: Callable[..., Any] = lambda **kwargs: None
        self._emoji_getter: Callable[[], Callable] = lambda: None
        self._emoji_fixer: Callable[[Any], Any] = lambda embed: embed
        self.set_definitions: dict = {}
        self.item_set: dict = {}
        self.adjacency_bonus = 0.005
        self.adjacency_max = 0.10
        self.floor_bonus = 0.01
        self.floor_max = 0.10
        self.total_max = 0.40
        self.logger = logging.getLogger("gen_mania")

    def configure(
        self,
        *,
        db_getter: Callable[[], Any],
        grid_size_getter: Callable[[], Callable],
        embed_factory: Callable[..., Any],
        emoji_getter: Callable[[], Callable],
        emoji_fixer: Callable[[Any], Any],
        set_definitions: dict,
        item_set: dict,
        adjacency_bonus: float,
        adjacency_max: float,
        floor_bonus: float,
        floor_max: float,
        total_max: float,
        logger: logging.Logger,
    ) -> None:
        self._db_getter = db_getter
        self._grid_size_getter = grid_size_getter
        self._embed_factory = embed_factory
        self._emoji_getter = emoji_getter
        self._emoji_fixer = emoji_fixer
        self.set_definitions = set_definitions
        self.item_set = item_set
        self.adjacency_bonus = adjacency_bonus
        self.adjacency_max = adjacency_max
        self.floor_bonus = floor_bonus
        self.floor_max = floor_max
        self.total_max = total_max
        self.logger = logger

    @property
    def db(self):
        return self._db_getter()

    async def get_grid_size(self, user_id: int):
        return await self._grid_size_getter()(user_id)

    def embed(self, **kwargs):
        return self._embed_factory(**kwargs)

    def emoji(self, key: str):
        return self._emoji_getter()(key)

    async def fix_emojis(self, embed):
        return await self._emoji_fixer(embed)


def make_set_layer(runtime: SetRuntime):
    """Возвращает функции сетов, привязанные к runtime."""

    def get_set_tier(set_id: str, count: int) -> tuple[int, float]:
        tiers = runtime.set_definitions.get(set_id, {}).get(
            "tiers", ()
        )
        for threshold, bonus in tiers:
            if count >= threshold:
                return threshold, bonus
        return 0, 0.0

    def compute_set_synergy(rows, grid_size: int) -> dict:
        """Считает бонусы сетов по раскладке энергостанции."""
        set_items: dict[str, set] = {
            set_id: set() for set_id in runtime.set_definitions
        }
        slot_sets = {}

        for slot, item_id in rows:
            set_id = runtime.item_set.get(item_id)
            if not set_id:
                continue
            set_items[set_id].add(item_id)
            slot_sets[int(slot)] = set_id

        set_counts = {
            set_id: len(items)
            for set_id, items in set_items.items()
        }
        set_tiers = {}
        set_bonus = 0.0
        for set_id, count in set_counts.items():
            threshold, bonus = get_set_tier(set_id, count)
            set_tiers[set_id] = (threshold, bonus)
            set_bonus += bonus

        width = max(1, int(grid_size ** 0.5))
        adjacency_pairs = 0
        for slot, set_id in slot_sets.items():
            right = slot + 1
            if (
                right < grid_size
                and slot % width != width - 1
            ):
                if slot_sets.get(right) == set_id:
                    adjacency_pairs += 1
            down = slot + width
            if (
                down < grid_size
                and slot_sets.get(down) == set_id
            ):
                adjacency_pairs += 1

        full_rows = 0
        for start in range(0, grid_size, width):
            row_sets = [
                slot_sets.get(slot)
                for slot in range(
                    start, min(start + width, grid_size)
                )
            ]
            if (
                row_sets
                and all(row_sets)
                and len(set(row_sets)) == 1
            ):
                full_rows += 1

        adjacency_bonus = min(
            adjacency_pairs * runtime.adjacency_bonus,
            runtime.adjacency_max,
        )
        floor_bonus = min(
            full_rows * runtime.floor_bonus,
            runtime.floor_max,
        )
        total = min(
            set_bonus + adjacency_bonus + floor_bonus,
            runtime.total_max,
        )

        return {
            "set_counts": set_counts,
            "set_tiers": set_tiers,
            "set_bonus": set_bonus,
            "adjacency_pairs": adjacency_pairs,
            "adjacency_bonus": adjacency_bonus,
            "full_rows": full_rows,
            "floor_bonus": floor_bonus,
            "total": total,
        }

    async def get_set_synergy_details(user_id: int) -> dict:
        grid_size = await runtime.get_grid_size(user_id)
        async with runtime.db.execute(
            "SELECT slot, item_id FROM inventory "
            "WHERE user_id = ? AND location = 'profile'",
            (user_id,),
        ) as c:
            rows = await c.fetchall()
        return compute_set_synergy(rows, grid_size)

    async def get_set_bonus(user_id: int) -> float:
        details = await get_set_synergy_details(user_id)
        return details["total"]

    async def build_sets_embed(user_id: int):
        details = await get_set_synergy_details(user_id)
        embed = runtime.embed(
            title=f"{runtime.emoji('_inventory')} Сеты генераторов",
            description=(
                "Сеты дают бонус за разные генераторы одного "
                "набора, соседство и полностью заполненные ряды."
            ),
            color=0x9B59B6,
        )

        set_lines = []
        for (
            set_id,
            set_def,
        ) in runtime.set_definitions.items():
            count = details["set_counts"].get(set_id, 0)
            total = len(set_def["items"])
            _, current_bonus = details["set_tiers"].get(
                set_id, (0, 0.0)
            )
            line = (
                f"{set_def['emoji']} **{set_def['name']}** — "
                f"{count}/{total} (+{int(current_bonus * 100)}%)"
            )
            if count < total:
                next_tier = None
                for threshold, bonus in reversed(
                    set_def["tiers"]
                ):
                    if count < threshold:
                        next_tier = (threshold, bonus)
                        break
                if next_tier:
                    line += (
                        f" · след. {next_tier[0]} → "
                        f"+{int(next_tier[1] * 100)}%"
                    )
            set_lines.append(line)

        embed.add_field(
            name="Наборы",
            value="\n".join(set_lines),
            inline=False,
        )
        embed.add_field(
            name="Синергия",
            value=(
                f"Сеты: **+{int(details['set_bonus'] * 100)}%**\n"
                f"Соседство: **{details['adjacency_pairs']}** "
                f"пар → "
                f"+{int(details['adjacency_bonus'] * 100)}%\n"
                f"Этажи: **{details['full_rows']}** рядов → "
                f"+{int(details['floor_bonus'] * 100)}%\n"
                f"**Итого: +{int(details['total'] * 100)}%**"
            ),
            inline=False,
        )
        embed.add_field(
            name="Как усилить",
            value=(
                "Собери 2/4/6 разных генераторов одного сета, "
                "ставь их соседними слотами и заполняй целые ряды."
            ),
            inline=False,
        )
        embed.set_footer(
            text=(
                f"Соседство: "
                f"+{int(runtime.adjacency_bonus * 1000)}‰ за пару · "
                f"ряд: +{int(runtime.floor_bonus * 100)}%"
            )
        )
        return await runtime.fix_emojis(embed)

    return (
        get_set_tier,
        compute_set_synergy,
        get_set_synergy_details,
        get_set_bonus,
        build_sets_embed,
    )
