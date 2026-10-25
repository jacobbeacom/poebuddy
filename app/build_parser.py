"""Canonical build schema + parsing helpers (design doc section 11).

The schema is deliberately permissive: real PoE2 imports are messy, so we
validate structure but keep values as-provided. Numeric validation lives in
calculations.py.
"""
from __future__ import annotations

import json

from pydantic import BaseModel, Field


class GemDetail(BaseModel):
    name: str
    level: int = 0
    quality: int = 0
    enabled: bool = True
    is_support: bool = False


class SkillSetup(BaseModel):
    skill: str
    supports: list[str] = Field(default_factory=list)
    # richer PoB-derived detail (optional; empty for hand-written builds)
    enabled: bool = True
    slot: str = ""
    gems: list[GemDetail] = Field(default_factory=list)


class EquipmentSlot(BaseModel):
    slot: str
    name: str = ""
    item_class: str = ""
    required_level: int = 0
    required_str: int = 0
    required_dex: int = 0
    required_int: int = 0
    mods: list[str] = Field(default_factory=list)


class Build(BaseModel):
    game_version: str = ""
    league: str = ""
    char_class: str = Field(default="", alias="class")
    ascendancy: str = ""
    level: int = 0
    attributes: dict[str, int] = Field(default_factory=dict)  # str/dex/int
    skills: list[SkillSetup] = Field(default_factory=list)
    passives: list[str] = Field(default_factory=list)
    equipment: list[EquipmentSlot] = Field(default_factory=list)
    buffs: list[str] = Field(default_factory=list)
    debuffs: list[str] = Field(default_factory=list)
    party_members: list[str] = Field(default_factory=list)
    content_target: str = ""
    budget: str = ""
    constraints: list[str] = Field(default_factory=list)

    # convenience derived-stat inputs (optional; used by calculations.py)
    life: float = 0.0
    energy_shield: float = 0.0
    resistances: dict[str, float] = Field(default_factory=dict)  # fire/cold/lightning/chaos
    reservations: dict[str, float] = Field(default_factory=dict)  # aura -> % reserved

    # full PoB-computed stat sheet (PlayerStat name -> value), populated by
    # pob_import; the analysis engine reads these instead of recomputing.
    pob_stats: dict[str, float] = Field(default_factory=dict)
    main_skill: str = ""  # active skill PoB marks as the main DPS skill

    model_config = {"populate_by_name": True}


def parse_build(data: str | dict) -> Build:
    """Parse a JSON string or dict into a validated Build."""
    if isinstance(data, str):
        data = json.loads(data)
    return Build.model_validate(data)


def empty_build() -> dict:
    """A blank canonical build dict for the UI editor."""
    return Build().model_dump(by_alias=True)
