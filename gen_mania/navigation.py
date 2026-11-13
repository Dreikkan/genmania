"""Navigation stack: in-memory history per user."""
from __future__ import annotations


NAV_STACKS: dict[int, list[tuple[str, dict]]] = {}
NAV_STACK_LIMIT = 20


def reset_nav(user_id: int):
    NAV_STACKS.pop(user_id, None)


def push_nav(user_id: int, route: str, **params):
    stack = NAV_STACKS.setdefault(user_id, [])
    if stack and stack[-1][0] == route:
        return
    stack.append((route, params))
    if len(stack) > NAV_STACK_LIMIT:
        del stack[: len(stack) - NAV_STACK_LIMIT]


def pop_nav(user_id: int, fallback: str = "main") -> tuple[str, dict]:
    stack = NAV_STACKS.get(user_id)
    if stack:
        return stack.pop()
    return fallback, {}
