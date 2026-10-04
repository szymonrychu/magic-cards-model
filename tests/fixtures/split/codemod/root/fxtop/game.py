"""Fixture: class mode with stay, records and self annotations."""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .helpers import ask_mulligan


class Record(BaseModel):
    value: int = 0


def module_helper() -> int:
    return 1


class Game(BaseModel):
    """Game docstring."""

    CURRENT_SCHEMA_VERSION: ClassVar[int] = 3
    model_config = ConfigDict(extra="forbid")
    life: int = 20
    records: list[Record] = []

    @field_validator("life")
    @classmethod
    def check_life(cls, value: int) -> int:
        return value

    @model_validator(mode="after")
    def check_all(self) -> "Game":
        return self

    def settle_pregame(self) -> str:
        return ask_mulligan(self)

    def combat_a(self) -> int:
        return self.combat_b() + module_helper()

    def combat_b(self) -> int:
        return 1

    # leading comment for draw_one
    def draw_one(self, n: int = 1) -> int:
        from .helpers import ask_mulligan as ask

        return n + self.draw_two() + len(ask(self))

    def draw_two(self) -> int:
        return 2

    @staticmethod
    def static_one() -> int:
        return 5

    @classmethod
    def cls_one(cls) -> int:
        return 6

    def combat_c(self: "Game") -> int:
        return 7


Game.model_rebuild()
