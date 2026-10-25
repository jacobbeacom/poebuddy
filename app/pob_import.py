"""Import a canonical Build from Path of Building.

Accepts either:
  - a pobb.in share link (https://pobb.in/<id>) -- fetched over the network
    via the site's documented /<id>/raw endpoint, which is the one exception
    to this project's "nothing leaves your machine" design (see README).
  - a raw PoB export code (the base64 blob from PoB's "Export Build" button)
    -- decoded entirely offline, no network call.

The export code is URL-safe base64 without padding, wrapping a zlib-deflated
XML document. XML element/attribute names below (Build, PlayerStat, Skill,
Gem, Items, Slot, Tree/Spec) match the Path of Building Community fork's
save format (shared by the PoE1 and PoE2 forks).

Support-gem detection has no explicit "is support" flag in the export; we
infer it from the gem's internal id containing "Support" (a stable PoE
naming convention), with the first non-support enabled gem in a group
treated as the active skill. This is a best-effort heuristic, in keeping
with build_parser's permissive design -- verify against the source build
if a skill/support split looks wrong.
"""
from __future__ import annotations

import base64
import re
import zlib
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import requests

from app.build_parser import Build, EquipmentSlot, GemDetail, SkillSetup

POBB_IN_HOST = "pobb.in"

STAT_MAP = {"life": "life", "energyshield": "energy_shield"}
RESIST_MAP = {
    "fireresist": "fire", "coldresist": "cold",
    "lightningresist": "lightning", "chaosresist": "chaos",
}
ATTR_MAP = {
    "str": "str", "dex": "dex", "int": "int",
    "strength": "str", "dexterity": "dex", "intelligence": "int",
}

_MOD_TAG_RE = re.compile(r"^\{[^}]*\}\s*")
_REQUIRES_RE = re.compile(
    r"Requires Level (\d+)(?:,\s*(\d+)\s*Str)?(?:,\s*(\d+)\s*Dex)?(?:,\s*(\d+)\s*Int)?"
)
_SKIP_LINE_PREFIXES = (
    "Item Level:", "Quality:", "Sockets:", "LevelReq:",
    "Implicits:", "Unique ID:", "Selected Variant:",
)


def _decode_pob_code(code: str) -> str:
    """Decode a PoB export code (url-safe base64 + zlib) into XML text."""
    code = code.strip()
    padded = code + "=" * (-len(code) % 4)
    raw = base64.urlsafe_b64decode(padded)
    return zlib.decompress(raw).decode("utf-8")


def _fetch_pobb_in_code(url: str) -> str:
    """Fetch the raw export code from a pobb.in share link."""
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    if host != POBB_IN_HOST and not host.endswith("." + POBB_IN_HOST):
        raise ValueError(f"Unsupported host for a PoB link: {parsed.netloc!r}")
    build_id = parsed.path.strip("/").split("/")[0]
    if not build_id:
        raise ValueError("Could not find a build id in the pobb.in link.")
    raw_url = f"https://{POBB_IN_HOST}/{build_id}/raw"
    resp = requests.get(raw_url, timeout=10,
                         headers={"User-Agent": "poebuddy/0.1"})
    resp.raise_for_status()
    return resp.text


def _parse_item_text(raw: str):
    """Best-effort parse of PoB/in-game copy-paste item text."""
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    name_lines: list[str] = []
    mods: list[str] = []
    level_req = str_req = dex_req = int_req = 0
    in_mods = False
    for line in lines:
        if line.startswith("Rarity:"):
            continue
        m = _REQUIRES_RE.search(line)
        if m:
            level_req = int(m.group(1) or 0)
            str_req = int(m.group(2) or 0)
            dex_req = int(m.group(3) or 0)
            int_req = int(m.group(4) or 0)
            continue
        if line == "--------":
            in_mods = True
            continue
        if line.startswith(_SKIP_LINE_PREFIXES):
            continue
        if in_mods:
            mods.append(_MOD_TAG_RE.sub("", line))
        elif len(name_lines) < 2:
            name_lines.append(line)
    name = name_lines[0] if name_lines else ""
    base_type = name_lines[1] if len(name_lines) > 1 else name
    return name, base_type, level_req, str_req, dex_req, int_req, mods


def parse_pob_xml(xml_text: str) -> Build:
    root = ET.fromstring(xml_text)
    build_el = root if root.tag == "Build" else root.find("Build")
    if build_el is None:
        raise ValueError("PoB export is missing a <Build> element.")

    build = Build(
        char_class=build_el.get("className", ""),
        ascendancy=build_el.get("ascendClassName", ""),
        level=int(build_el.get("level") or 0),
        game_version=build_el.get("targetVersion", ""),
    )

    for stat_el in build_el.findall("PlayerStat"):
        stat = stat_el.get("stat") or ""
        value = stat_el.get("value")
        if not stat or value is None:
            continue
        try:
            fvalue = float(value)
        except ValueError:
            continue
        build.pob_stats[stat] = fvalue
        low = stat.lower()
        if low in STAT_MAP:
            setattr(build, STAT_MAP[low], fvalue)
        elif low in RESIST_MAP:
            build.resistances[RESIST_MAP[low]] = fvalue
        elif low in ATTR_MAP:
            build.attributes[ATTR_MAP[low]] = int(fvalue)

    main_group = int(build_el.get("mainSocketGroup") or 0)

    skills_el = root.find("Skills")
    if skills_el is not None:
        # Newer PoB wraps socket groups in SkillSet elements; use the active
        # set if marked, else the first, else the bare Skill list.
        skill_sets = skills_el.findall("SkillSet")
        if skill_sets:
            active_id = skills_el.get("activeSkillSet")
            container = next(
                (s for s in skill_sets if s.get("id") == active_id), skill_sets[0])
        else:
            container = skills_el
        for group_idx, skill_el in enumerate(container.findall("Skill"), start=1):
            group_enabled = skill_el.get("enabled", "true").lower() != "false"
            active: GemDetail | None = None
            gems: list[GemDetail] = []
            supports: list[str] = []
            for gem_el in skill_el.findall("Gem"):
                label = gem_el.get("nameSpec") or gem_el.get("skillId") or ""
                if not label:
                    continue
                gem_id = gem_el.get("gemId") or gem_el.get("skillId") or ""
                gem = GemDetail(
                    name=label,
                    level=int(gem_el.get("level") or 0),
                    quality=int(gem_el.get("quality") or 0),
                    enabled=gem_el.get("enabled", "true").lower() != "false",
                    is_support="support" in gem_id.lower(),
                )
                gems.append(gem)
                if not gem.enabled:
                    continue
                if gem.is_support:
                    supports.append(gem.name)
                elif active is None:
                    active = gem
                else:
                    supports.append(gem.name)
            if active:
                build.skills.append(SkillSetup(
                    skill=active.name, supports=supports,
                    enabled=group_enabled, slot=skill_el.get("slot", ""),
                    gems=gems,
                ))
                if group_idx == main_group:
                    build.main_skill = active.name
        if not build.main_skill and build.skills:
            build.main_skill = build.skills[0].skill

    items_el = root.find("Items")
    if items_el is not None:
        item_by_id = {
            item_el.get("id"): item_el
            for item_el in items_el.findall("Item")
            if item_el.get("id")
        }
        item_set = items_el.find("ItemSet")
        for slot_el in (item_set.findall("Slot") if item_set is not None else []):
            item_id = slot_el.get("itemId")
            if not item_id or item_id == "0":
                continue
            item_el = item_by_id.get(item_id)
            if item_el is None or not (item_el.text or "").strip():
                continue
            name, base_type, lvl, s, d, i, mods = _parse_item_text(item_el.text)
            build.equipment.append(EquipmentSlot(
                slot=slot_el.get("name", ""), name=name, item_class=base_type,
                required_level=lvl, required_str=s, required_dex=d,
                required_int=i, mods=mods,
            ))

    tree_el = root.find("Tree")
    if tree_el is not None:
        spec_el = tree_el.find("Spec")
        nodes = spec_el.get("nodes") if spec_el is not None else None
        if nodes:
            build.passives = [n for n in nodes.split(",") if n]

    return build


def import_pob(text: str) -> Build:
    """Import a Build from either a pobb.in link or a raw PoB export code."""
    text = text.strip()
    if not text:
        raise ValueError("Paste a pobb.in link or a Path of Building export code.")
    code = _fetch_pobb_in_code(text) if re.match(r"^https?://", text) else text
    xml_text = _decode_pob_code(code)
    return parse_pob_xml(xml_text)
