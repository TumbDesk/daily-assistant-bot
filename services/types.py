"""Shared DTOs without circular imports between parser and calendar."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryDTO:
    id: int
    name: str
    is_global: bool = False
