"""Build-context detection: what does this build scale, and what's its role?

Two questions drive report framing:
  1. Damage basis -- hits, damage-over-time, or minions? (Recommendations
     differ: DoT builds scale gem levels/magnitude, not attack speed;
     minion builds don't care about personal accuracy.)
  2. Role -- DPS carry or group support? A support (aura/curse bot) should
     be judged on party contribution and staying alive, not personal DPS.

Gem classification is data-driven from the local wiki snapshot's page
categories (Curse/Buff/Aura/Herald/Persistent/Minion skill gems), with a
small name-heuristic fallback when the DuckDB store is unavailable.
Role auto-detection is conservative; the UI lets the user override it.
"""
from __future__ import annotations

import json

from app.build_parser import Build
from app.settings import SETTINGS

# name-heuristic fallback when the wiki DB is unavailable
FALLBACK_PREFIXES = {
    "aura_buff": ("Herald of", "Purity of"),
    "minion": ("Summon", "Raise", "Skeletal", "Reanimate"),
}
FALLBACK_CURSES = {"Despair", "Enfeeble", "Temporal Chains", "Flammability",
                   "Hypothermia", "Conductivity", "Vulnerability"}

ROLE_CATEGORIES = {
    "curse": ("Curse skill gems",),
    "aura_buff": ("Aura skill gems", "Herald skill gems", "Buff skill gems",
                  "Persistent skill gems"),
    "minion": ("Minion skill gems",),
    "attack": ("Attack skill gems",),
    "spell": ("Spell skill gems",),
}


def _gem_roles_from_wiki(names: list[str]) -> dict[str, set[str]]:
    """Map gem name -> roles using wiki page categories; {} on any failure."""
    if not names:
        return {}
    try:
        from app import db
        placeholders = ",".join("?" for _ in names)
        rows = db.run_query(
            f"SELECT title, categories FROM pages WHERE title IN ({placeholders})",
            list(names))
    except Exception:  # noqa: BLE001 -- DB missing pre-ingest
        return {}
    out: dict[str, set[str]] = {}
    for r in rows:
        cats = set(json.loads(r["categories"] or "[]"))
        roles = {role for role, needles in ROLE_CATEGORIES.items()
                 if any(f"Category:{n}" in cats for n in needles)}
        if roles:
            out[r["title"]] = roles
    return out


def _gem_roles_fallback(name: str) -> set[str]:
    roles: set[str] = set()
    if name in FALLBACK_CURSES:
        roles.add("curse")
    for role, prefixes in FALLBACK_PREFIXES.items():
        if name.startswith(prefixes):
            roles.add(role)
    return roles


def _stat(b: Build, name: str, default: float = 0.0) -> float:
    v = b.pob_stats.get(name)
    return default if v is None else v


def suggest_supports(main_skill: str, exclude: list[str],
                     limit: int = 8) -> list[str]:
    """Support-gem candidates for a skill, from wiki gem-tag overlap.

    Matches the skill's tag categories ("Fire skill gems", "Projectile
    skill gems", ...) against supports carrying the same tag ("<Tag>
    support gems"). Deterministic and local; returns [] when the DB is
    unavailable. Lineage supports are excluded (boss-drop rarities make
    poor generic advice).
    """
    try:
        from app import db
        rows = db.run_query(
            "SELECT categories FROM pages WHERE title = ? LIMIT 1",
            [main_skill])
        if not rows:
            return []
        skill_tags = {
            c.removeprefix("Category:").removesuffix(" skill gems").lower()
            for c in json.loads(rows[0]["categories"] or "[]")
            if c.endswith(" skill gems")
        }
        skill_tags -= {"strength", "dexterity", "intelligence", "buff",
                       "persistent", "remnant"}
        if not skill_tags:
            return []
        supports = db.run_query(
            "SELECT title, categories FROM pages "
            "WHERE document_type = 'support' AND NOT obsolete")
    except Exception:  # noqa: BLE001 -- DB missing pre-ingest
        return []
    excluded = {e.lower() for e in exclude}
    scored: list[tuple[int, str]] = []
    for r in supports:
        name = r["title"]
        if name.lower() in excluded or "(" in name:
            continue
        cats = json.loads(r["categories"] or "[]")
        if any(c == "Category:Lineage support gems" for c in cats):
            continue
        tags = {c.removeprefix("Category:").removesuffix(" support gems").lower()
                for c in cats if c.endswith(" support gems")}
        overlap = len(tags & skill_tags)
        if overlap:
            scored.append((-overlap, name))
    return [name for _, name in sorted(scored)[:limit]]


def detect_archetype(build: Build) -> dict:
    """Classify damage basis, scaling signals, and probable role."""
    active_gems = []
    for s in build.skills:
        for g in s.gems:
            if not g.is_support and g.enabled:
                active_gems.append(g.name)
        if not s.gems and s.skill:  # hand-written builds have no gem detail
            active_gems.append(s.skill)

    wiki_roles = _gem_roles_from_wiki(active_gems)
    gem_roles: dict[str, list[str]] = {}
    for name in active_gems:
        roles = wiki_roles.get(name) or _gem_roles_fallback(name)
        if roles:
            gem_roles[name] = sorted(roles)

    curses = [n for n, r in gem_roles.items() if "curse" in r]
    buffs = [n for n, r in gem_roles.items() if "aura_buff" in r
             and "curse" not in r]
    minions = [n for n, r in gem_roles.items() if "minion" in r]
    main_roles = set(gem_roles.get(build.main_skill, []))

    # ---- damage basis ----
    combined = _stat(build, "CombinedDPS") or _stat(build, "TotalDPS")
    full = _stat(build, "FullDPS")
    dot = max(_stat(build, "TotalDotDPS"), _stat(build, "WithDotDPS"))
    dot_kinds = [k for k, s in (("ignite", "IgniteDPS"), ("poison", "PoisonDPS"),
                                ("bleed", "BleedDPS"))
                 if combined and _stat(build, s) > 0.25 * combined]
    if "minion" in main_roles or (full > 0 and full > 1.5 * max(combined, 1)):
        basis = "minion"
    elif combined and dot > 0.6 * combined:
        basis = "dot"
    elif combined:
        basis = "hit"
    else:
        basis = "unknown"

    crit = _stat(build, "CritChance") >= 25
    attack = _stat(build, "HitChance") > 0

    # ---- role ----
    endgame = build.level >= SETTINGS["analysis"]["endgame_level"]
    low_dps = endgame and 0 < max(combined, full) < \
        SETTINGS["analysis"]["dps_tiers"]["campaign"]
    spirit = _stat(build, "Spirit")
    reserved_ratio = ((spirit - _stat(build, "SpiritUnreserved")) / spirit
                      if spirit else 0.0)
    score = 0
    score += 2 if len(curses) + len(buffs) >= 3 else 0
    score += 2 if low_dps else 0
    score += 1 if (spirit >= 100 and reserved_ratio > 0.9) else 0
    score += 1 if len(curses) >= 2 else 0
    role = "support" if score >= 4 else "dps"

    # ---- summary line ----
    basis_txt = {"minion": "minion-based", "dot":
                 f"damage-over-time ({', '.join(dot_kinds) or 'generic'})",
                 "hit": "hit-based", "unknown": ""}[basis]
    bits = [basis_txt,
            "crit-scaling" if crit else "",
            "attack" if attack else ("spell" if basis in ("hit", "dot") else ""),
            f"{len(buffs)} buff/aura + {len(curses)} curse gems"
            if (buffs or curses) else ""]
    summary = ", ".join(x for x in bits if x) or "not enough data to classify"
    if role == "support":
        summary = f"group-support archetype ({summary})"

    return {
        "basis": basis, "dot_kinds": dot_kinds, "crit": crit,
        "attack": attack, "role": role, "role_score": score,
        "curse_gems": curses, "buff_gems": buffs, "minion_gems": minions,
        "gem_roles": gem_roles, "summary": summary,
        "classified_from_wiki": bool(wiki_roles),
    }
