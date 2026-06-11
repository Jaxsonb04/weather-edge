from __future__ import annotations

import os
from dataclasses import dataclass


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
GRAY = "\033[90m"


@dataclass(frozen=True)
class Color:
    enabled: bool

    @classmethod
    def from_no_color(cls, no_color: bool) -> "Color":
        return cls(enabled=not no_color and "NO_COLOR" not in os.environ)

    def apply(self, value: object, code: str) -> str:
        text = str(value)
        if not self.enabled:
            return text
        return f"{code}{text}{RESET}"

    def bold(self, value: object) -> str:
        return self.apply(value, BOLD)

    def dim(self, value: object) -> str:
        return self.apply(value, DIM)

    def green(self, value: object) -> str:
        return self.apply(value, GREEN)

    def red(self, value: object) -> str:
        return self.apply(value, RED)

    def yellow(self, value: object) -> str:
        return self.apply(value, YELLOW)

    def cyan(self, value: object) -> str:
        return self.apply(value, CYAN)

    def gray(self, value: object) -> str:
        return self.apply(value, GRAY)
