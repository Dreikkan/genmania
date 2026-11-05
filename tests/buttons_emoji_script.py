import importlib.util
import pathlib
import sys

import discord

BOT_PATH = pathlib.Path(__file__).resolve().parent.parent / "bot.py"
spec = importlib.util.spec_from_file_location("gen_mania_button_test", BOT_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)

views = [
    m.MainMenuView(1),
    m.PrestigeView(1),
    m.SeasonView(
        1,
        {
            "premium": False,
            "claimable_free": [1],
            "claimable_premium": [],
        },
    ),
    m.SeasonPremiumConfirmView(1, m.SEASON_PREMIUM_COST_GEMS),
    m.SocialView(1),
    m.RaidMenuView(1),
    m.RaidPartyView(1, 1),
    m.RaidInviteView(1, 1, 2),
    m.DuelChallengeView(1, 2, 100, "dice"),
    m.ShopHubView(1),
    m.MarketView(1),
    m.MarketFiltersView(1, None, "change"),
    m.MarketHistorySelectView(
        1,
        [
            discord.SelectOption(
                label="test",
                value="basic_gen",
                emoji=m.parse_emoji_safe(m.get_emoji("_market")),
            )
        ],
        0,
        1,
        None,
        "change",
    ),
    m.MarketOrdersView(
        1,
        0,
        1,
        [
            (
                1,
                2,
                "sell",
                "basic_gen",
                0,
                150,
                3,
                0,
                (
                    m.datetime.datetime.now() + m.datetime.timedelta(hours=1)
                ).isoformat(),
                "Базовый",
                "📦",
            )
        ],
        "all",
        1,
    ),
    m.MarketOrderFillConfirmView(1, 1, 0, "all"),
    m.MarketMyOrdersView(
        1,
        [
            discord.SelectOption(
                label="test",
                value="1",
                emoji=m.parse_emoji_safe(m.get_emoji("_market")),
            )
        ],
        1,
    ),
    m.MarketOrderCreateView(
        1,
        "sell",
        [
            discord.SelectOption(
                label="test",
                value="basic_gen",
                emoji=m.parse_emoji_safe(m.get_emoji("_market")),
            )
        ],
        0,
        1,
    ),
    m.QuestsHubView(1),
    m.ProfileView(1),
    m.SetsView(1),
    m.BankView(1, False, False),
    m.BankView(1, True, True),
    m.BankHistoryView(1),
    m.BankLoanSelectView(
        1,
        [
            discord.SelectOption(
                label="test",
                value="basic_gen:0",
                emoji=m.parse_emoji_safe(m.get_emoji("_bank")),
            )
        ],
        0,
        1,
    ),
    m.BankRepayConfirmView(1),
    m.AuctionView(
        1,
        0,
        1,
        [
            (
                1,
                2,
                "basic_gen",
                0,
                100,
                None,
                500,
                (
                    m.datetime.datetime.now() + m.datetime.timedelta(hours=1)
                ).isoformat(),
                "Базовый",
                "📦",
            )
        ],
        1,
        500,
    ),
    m.AuctionBuyoutConfirmView(1, 1),
    m.GuideView(1),
    m.TopView(1, "coins", 10),
    m.AdventView(1),
    m.TitlesView(
        1,
        [
            discord.SelectOption(
                label="test",
                value="x",
                emoji=m.parse_emoji_safe(m.get_emoji("_title")),
            )
        ],
        0,
        1,
    ),
    m.CatalystSelectView(1),
    m.BuyItemQuantityView(1, "basic_gen"),
    m.SettingsCommandsView(1),
]

count = 0
problems = []
for view in views:
    for child in view.children:
        if isinstance(child, discord.ui.Button):
            count += 1
            if child.emoji is None:
                problems.append(f"{type(view).__name__}: button {child.label!r} без emoji")
            elif isinstance(child.emoji, str):
                problems.append(
                    f"{type(view).__name__}: button {child.label!r} unicode emoji {child.emoji!r}"
                )
        elif isinstance(child, discord.ui.Select):
            for option in child.options:
                if option.emoji is None:
                    problems.append(
                        f"{type(view).__name__}: SelectOption {option.label!r} без emoji"
                    )

print(f"checked buttons: {count}")
if problems:
    print("PROBLEMS:")
    print("\n".join(problems))
    raise SystemExit(1)
print("BUTTON EMOJI TEST: OK")
