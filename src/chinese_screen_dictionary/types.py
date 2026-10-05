from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["auto", "horizontal", "vertical"]


@dataclass(frozen=True)
class TextBox:
    text: str
    confidence: float
    points: tuple[tuple[float, float], ...]

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        xs, ys = zip(*self.points)
        return min(xs), min(ys), max(xs), max(ys)


@dataclass(frozen=True)
class Sense:
    pinyin: str
    definitions: tuple[str, ...]


@dataclass
class Vocabulary:
    key: str
    surface: str
    simplified: str
    traditional: str
    pinyin: str
    senses: list[Sense]
    start: int
    end: int
    save: bool = True


@dataclass
class Analysis:
    text: str
    pinyin: str
    translation: str
    words: list[Vocabulary] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    direction: str = "horizontal"
    elapsed: float = 0


class LookupSession:
    """UI-owned generation counter: cancelled/obsolete workers cannot commit."""

    def __init__(self):
        self.generation = 0
        self.lookup_id: str | None = None
        self.active = False

    def begin(self, lookup_id: str) -> int:
        self.lookup_id = lookup_id
        self.active = True
        return self.revise()

    def revise(self) -> int:
        self.generation += 1
        return self.generation

    def cancel(self):
        self.active = False
        self.lookup_id = None
        self.generation += 1

    def accepts(self, generation: int) -> bool:
        return self.active and generation == self.generation
