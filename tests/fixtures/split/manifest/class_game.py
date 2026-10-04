"""Fixture: class mode (stay list, records, decorated members)."""

from pydantic import BaseModel, ConfigDict, field_validator


class Record(BaseModel):
    value: int = 0


def module_helper() -> int:
    return 1


class Game(BaseModel):
    model_config = ConfigDict(extra="forbid")
    life: int = 20

    @field_validator("life")
    @classmethod
    def check_life(cls, value: int) -> int:
        return value

    def named_stay(self) -> int:
        return self.life

    def combat_a(self) -> int:
        return self.combat_b() + self.shared_helper()

    def combat_b(self) -> int:
        return 1

    def draw_one(self) -> int:
        return self.shared_helper() + self.only_draw()

    def only_draw(self) -> int:
        return 2

    def shared_helper(self) -> int:
        return 3
