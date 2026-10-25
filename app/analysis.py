"""Deterministic build analysis: PoB-computed stats vs PoE2 benchmarks.

Every finding is produced by an explicit rule with its inputs attached --
the LLM never invents or adjusts these numbers, it only narrates them.

Game-rule facts (res caps, chaos-vs-ES, support sockets, block cap) come
from the bundled wiki snapshot; page titles are attached to findings as
`wiki_refs` so the report can cite them. Tier thresholds (pool / max-hit /
DPS bands) are community heuristics read from settings.yaml `analysis:` --
tune them there, not here.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from app.archetype import detect_archetype
from app.build_parser import Build, parse_build
from app.settings import SETTINGS

ACFG = SETTINGS["analysis"]

SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2, "info": 3, "good": 4}
SEVERITY_WEIGHT = {"critical": 25, "major": 10, "minor": 4, "info": 0, "good": 0}

CORE_SLOTS = ["Weapon 1", "Helmet", "Body Armour", "Gloves", "Boots",
              "Amulet", "Ring 1", "Ring 2", "Belt"]

DPS_TIER_LABELS = [
    ("campaign", "campaign-tier"),
    ("early_maps", "early-maps-tier"),
    ("mid_maps", "mid-maps-tier"),
    ("endgame", "endgame-ready"),
]


@dataclass
class Finding:
    id: str
    severity: str          # critical | major | minor | info | good
    category: str          # defense | offense | gems | gear
    title: str
    detail: str            # what was measured, with numbers
    recommendation: str    # what to do about it
    metrics: dict = field(default_factory=dict)
    wiki_refs: list[str] = field(default_factory=list)


def _stat(b: Build, name: str, default: float | None = None) -> float | None:
    return b.pob_stats.get(name, default)


def _main_setup(b: Build):
    for s in b.skills:
        if s.skill == b.main_skill:
            return s
    return b.skills[0] if b.skills else None


def _is_endgame(b: Build) -> bool:
    return b.level >= ACFG["endgame_level"]


# ------------------------------------------------------------------ defense

def check_resistances(b: Build) -> list[Finding]:
    out: list[Finding] = []
    cap = ACFG["res_cap"]
    buffer = ACFG["res_overcap_buffer"]
    uncapped_low = []
    for elem, stat, over in (("fire", "FireResist", "FireResistOverCap"),
                             ("cold", "ColdResist", "ColdResistOverCap"),
                             ("lightning", "LightningResist", "LightningResistOverCap")):
        val = _stat(b, stat, b.resistances.get(elem))
        if val is None:
            continue
        overcap = _stat(b, over, 0.0) or 0.0
        if val < cap:
            out.append(Finding(
                id=f"res_uncapped_{elem}",
                severity="critical" if _is_endgame(b) else "major",
                category="defense",
                title=f"{elem.title()} resistance below cap",
                detail=f"{elem.title()} resistance is {val:.0f}%, "
                       f"{cap - val:.0f}% short of the {cap}% cap. Endgame "
                       "enemy damage is balanced around capped resistances, "
                       "and every point missing multiplies damage taken.",
                recommendation=f"Cap {elem} resistance to {cap}% before any "
                               "other defensive investment: fill open "
                               "suffixes on rings/boots/gloves, or use a "
                               "charm/rune as a stopgap.",
                metrics={"value": val, "cap": cap},
                wiki_refs=["Resistance"],
            ))
        elif overcap < buffer:
            uncapped_low.append((elem, overcap))
    if uncapped_low and _is_endgame(b):
        worst = ", ".join(f"{e} +{o:.0f}%" for e, o in uncapped_low)
        out.append(Finding(
            id="res_overcap_thin",
            severity="info",
            category="defense",
            title="Thin resistance overcap",
            detail=f"Capped, but with little headroom ({worst}). Curses and "
                   "exposure (-20% by default) reduce uncapped resistance, "
                   "so a thin buffer means map mods can knock you below cap.",
            recommendation=f"Aim for ~+{ACFG['res_overcap_buffer']}% uncapped "
                           "headroom per element so exposure and curse mods "
                           "can't break your cap.",
            metrics={"overcaps": dict(uncapped_low)},
            wiki_refs=["Resistance"],
        ))
    if not out:
        out.append(Finding(
            id="res_capped", severity="good", category="defense",
            title="Elemental resistances capped",
            detail="All three elemental resistances are at the cap.",
            recommendation="", metrics={},
        ))
    return out


def check_chaos_res(b: Build) -> list[Finding]:
    val = _stat(b, "ChaosResist", b.resistances.get("chaos"))
    if val is None:
        return []
    es = _stat(b, "EnergyShield", b.energy_shield) or 0.0
    life = _stat(b, "Life", b.life) or 0.0
    es_heavy = es > life
    if val < ACFG["chaos_res_severe"]:
        sev = "critical" if es_heavy else "major"
        extra = (" Chaos damage removes twice as much energy shield, so an "
                 "ES-based build is hit doubly hard here." if es_heavy else "")
        return [Finding(
            id="chaos_res_low", severity=sev, category="defense",
            title="Deeply negative chaos resistance",
            detail=f"Chaos resistance is {val:.0f}%.{extra}",
            recommendation="Bring chaos resistance toward 0%+ via suffixes "
                           "or an Amethyst Charm; chaos DoT (poison, "
                           "withering ground) is a common endgame killer.",
            metrics={"value": val, "es_heavy": es_heavy},
            wiki_refs=["Resistance", "Chaos"],
        )]
    if val < ACFG["chaos_res_floor"]:
        return [Finding(
            id="chaos_res_negative", severity="minor", category="defense",
            title="Negative chaos resistance",
            detail=f"Chaos resistance is {val:.0f}%.",
            recommendation="Positive chaos resistance is worth picking up "
                           "on spare suffixes once elemental res is capped.",
            metrics={"value": val},
            wiki_refs=["Resistance"],
        )]
    return [Finding(
        id="chaos_res_ok", severity="good", category="defense",
        title="Chaos resistance under control",
        detail=f"Chaos resistance is {val:.0f}%.",
        recommendation="", metrics={"value": val},
    )]


def check_pool(b: Build) -> list[Finding]:
    life = _stat(b, "Life", b.life) or 0.0
    es = _stat(b, "EnergyShield", b.energy_shield) or 0.0
    pool = life + es
    if pool <= 0:
        return []
    tiers = ACFG["pool_tiers"]
    if not _is_endgame(b):
        return [Finding(
            id="pool_campaign", severity="info", category="defense",
            title="Health pool (campaign)",
            detail=f"Life {life:.0f} + ES {es:.0f} = {pool:.0f} combined pool "
                   f"at level {b.level}.",
            recommendation="Keep life growing every few levels via gear and "
                           "passives; endgame benchmarks kick in at level "
                           f"{ACFG['endgame_level']}.",
            metrics={"life": life, "es": es, "pool": pool},
        )]
    if pool < tiers["low"]:
        sev, verdict = "critical", "dangerously low for endgame maps"
    elif pool < tiers["ok"]:
        sev, verdict = "major", "below the comfortable range for maps"
    elif pool < tiers["good"]:
        sev, verdict = "minor", "workable, with room to grow"
    else:
        sev, verdict = "good", "healthy"
    rec = ""
    if sev != "good":
        rec = ("Raise the combined pool: life/ES prefixes on body armour, "
               "helmet and shield contribute the most, plus +maximum life "
               "notables and Strength (+2 life each) on the tree.")
    return [Finding(
        id="pool_endgame", severity=sev, category="defense",
        title=f"Combined life + ES pool is {verdict}",
        detail=f"Life {life:.0f} + ES {es:.0f} = {pool:.0f} combined pool. "
               f"Heuristic endgame bands: <{tiers['low']} risky, "
               f">{tiers['good']} solid.",
        recommendation=rec,
        metrics={"life": life, "es": es, "pool": pool, "tiers": dict(tiers)},
        wiki_refs=["Energy Shield"] if es > life else [],
    )]


def check_max_hits(b: Build) -> list[Finding]:
    stats = {"physical": "PhysicalMaximumHitTaken", "fire": "FireMaximumHitTaken",
             "cold": "ColdMaximumHitTaken", "lightning": "LightningMaximumHitTaken",
             "chaos": "ChaosMaximumHitTaken"}
    vals = {k: _stat(b, s) for k, s in stats.items()}
    vals = {k: v for k, v in vals.items() if v is not None and v > 0}
    if not vals or not _is_endgame(b):
        return []
    tiers = ACFG["max_hit_tiers"]
    weakest = min(vals, key=vals.get)
    low = vals[weakest]
    if low < tiers["low"]:
        sev = "major"
        verdict = (f"a {low:.0f} {weakest} hit kills you -- big endgame "
                   "slams and boss abilities land in this range")
    elif low < tiers["good"]:
        sev = "minor"
        verdict = f"the weakest link is {weakest} at {low:.0f}"
    else:
        sev = "good"
        verdict = "you can absorb large one-shots in every damage type"
    return [Finding(
        id="max_hit", severity=sev, category="defense",
        title=f"Largest survivable hit: {verdict}" if sev == "good"
              else f"One-shot exposure vs {weakest} damage",
        detail="PoB maximum survivable hit by type: "
               + ", ".join(f"{k} {v:.0f}" for k, v in sorted(vals.items()))
               + f". Heuristic endgame comfort starts around {tiers['low']}.",
        recommendation="" if sev == "good" else
        f"Shore up the {weakest} layer: "
        + ("armour scales poorly against huge hits -- pair it with more "
           "pool or +max res." if weakest == "physical" else
           f"+maximum {weakest} resistance and more pool raise this fastest."),
        metrics={"max_hits": vals, "tiers": dict(tiers)},
        wiki_refs=["Armour"] if weakest == "physical" else ["Resistance"],
    )]


def check_phys_layer(b: Build) -> list[Finding]:
    if not _is_endgame(b):
        return []
    dr = _stat(b, "PhysicalDamageReduction", 0.0) or 0.0
    evade = _stat(b, "EvadeChance", 0.0) or 0.0
    block = _stat(b, "EffectiveBlockChance", 0.0) or 0.0
    if dr >= 20 or evade >= 30 or block >= 20:
        return []
    return [Finding(
        id="no_phys_layer", severity="major", category="defense",
        title="No meaningful physical mitigation layer",
        detail=f"Physical damage reduction {dr:.0f}%, evade chance "
               f"{evade:.0f}%, block {block:.0f}%. Everything physical hits "
               "your raw pool.",
        recommendation="Add at least one layer: armour bases/flat armour, "
                       "an evasion hybrid, or a shield with block (passive "
                       "block caps at 50%).",
        metrics={"phys_dr": dr, "evade": evade, "block": block},
        wiki_refs=["Armour", "Evasion", "Block"],
    )]


def check_spirit(b: Build) -> list[Finding]:
    spirit = _stat(b, "Spirit")
    free = _stat(b, "SpiritUnreserved")
    if spirit is None or free is None:
        return []
    if free >= ACFG["spirit_waste_major"]:
        sev = "major"
    elif free >= ACFG["spirit_waste_minor"]:
        sev = "minor"
    else:
        return [Finding(
            id="spirit_used", severity="good", category="defense",
            title="Spirit fully put to work",
            detail=f"{spirit - free:.0f}/{spirit:.0f} spirit reserved.",
            recommendation="", metrics={"spirit": spirit, "free": free},
        )]
    return [Finding(
        id="spirit_unused", severity=sev, category="defense",
        title=f"{free:.0f} spirit sitting unused",
        detail=f"Only {spirit - free:.0f} of {spirit:.0f} spirit is "
               "reserved. Spirit is free power: persistent buffs, heralds "
               "and permanent minions cost nothing but reservation.",
        recommendation="Socket another spirit gem (herald, aura, or a "
                       "trigger meta gem) or level an existing one to use "
                       "the headroom.",
        metrics={"spirit": spirit, "free": free},
        wiki_refs=["Spirit"],
    )]


def check_es_bypass(b: Build) -> list[Finding]:
    es = _stat(b, "EnergyShield", b.energy_shield) or 0.0
    life = _stat(b, "Life", b.life) or 0.0
    if es <= life or es <= 0:
        return []
    return [Finding(
        id="es_bypass_note", severity="info", category="defense",
        title="ES-primary build: mind the bypass mechanics",
        detail=f"Energy shield ({es:.0f}) is your main pool over life "
               f"({life:.0f}). Bleed and poison bypass ES entirely, and "
               "chaos damage removes ES at double rate.",
        recommendation="Carry bleed/poison-cleansing charms or flask mods, "
                       "keep chaos res positive, and consider 'Stun "
                       "Threshold is based on Energy Shield' nodes so big "
                       "hits don't stun-lock you through a tiny life pool.",
        metrics={"es": es, "life": life},
        wiki_refs=["Energy Shield", "Chaos"],
    )]


def check_recovery(b: Build) -> list[Finding]:
    if not _is_endgame(b):
        return []
    regen = _stat(b, "NetLifeRegen", _stat(b, "LifeRegenRecovery"))
    leech = _stat(b, "LifeLeechGainRate", 0.0) or 0.0
    es_regen = _stat(b, "NetEnergyShieldRegen", 0.0) or 0.0
    if regen is None:
        return []
    if regen > 0 or leech > 0 or es_regen > 0:
        return []
    return [Finding(
        id="no_recovery", severity="minor", category="defense",
        title="No passive recovery outside flasks",
        detail="No life regeneration, leech, or ES regen detected -- "
               "between flask charges every scratch sticks.",
        recommendation="Pick up a regen or leech source: tree notables, "
                       "'gain life on kill' gear, or ES recharge "
                       "acceleration for ES builds.",
        metrics={"net_regen": regen, "leech_rate": leech},
    )]


# ------------------------------------------------------------------ offense

def _dps_value(b: Build, ctx: dict) -> tuple[float | None, str]:
    order = ("CombinedDPS", "FullDPS", "WithDotDPS", "TotalDPS")
    if ctx.get("basis") == "minion":
        order = ("FullDPS", "CombinedDPS", "WithDotDPS", "TotalDPS")
    for stat in order:
        v = _stat(b, stat)
        if v and v > 1:
            return v, stat
    return None, ""


def _dps_recommendation(ctx: dict) -> str:
    if ctx.get("basis") == "minion":
        return ("Minion damage scales with the minion gem's level above "
                "almost everything: prioritize +minion skill level gear, "
                "higher-level uncut gems, and spare spirit for more minions.")
    if ctx.get("basis") == "dot":
        return ("This build's damage is over time, so scale the DoT itself: "
                "skill gem level and increased damage-over-time/magnitude "
                "modifiers multiply it; raw attack/cast speed only speeds up "
                "application.")
    return ("The cheapest DPS multipliers, in order: fill every support "
            "socket on the main skill, upgrade the skill gem level "
            "(uncut gems), then weapon damage -- a weapon upgrade "
            "usually beats any single passive point.")


def check_dps(b: Build, ctx: dict) -> list[Finding]:
    dps, source = _dps_value(b, ctx)
    if dps is None:
        return []
    tiers = ACFG["dps_tiers"]
    label = "pinnacle-ready"
    for key, name in DPS_TIER_LABELS:
        if dps < tiers[key]:
            label = name
            break
    if ctx.get("role") == "support":
        return [Finding(
            id="dps_tier", severity="info", category="offense",
            title=f"Personal DPS: {dps:,.0f} (secondary for a support)",
            detail=f"PoB {source} is {dps:,.0f}. For a group-support build "
                   "this mostly needs to be enough to clear trash between "
                   "packs -- party contribution is what counts.",
            recommendation="",
            metrics={"dps": dps, "source_stat": source, "tier": label},
        )]
    if label in ("campaign-tier", "early-maps-tier") and _is_endgame(b):
        sev = "major" if label == "campaign-tier" else "minor"
        rec = _dps_recommendation(ctx)
    else:
        sev = "good" if _is_endgame(b) else "info"
        rec = ""
    scaling = ""
    if ctx.get("basis") == "dot":
        kinds = ", ".join(ctx.get("dot_kinds") or []) or "damage over time"
        scaling = f" Damage is {kinds}-based."
    elif ctx.get("basis") == "minion":
        scaling = " Damage comes from minions (FullDPS counts them all)."
    return [Finding(
        id="dps_tier", severity=sev, category="offense",
        title=f"Main skill DPS: {dps:,.0f} ({label})",
        detail=f"PoB {source} for {b.main_skill or 'the main skill'} is "
               f"{dps:,.0f}.{scaling} Heuristic bands: <{tiers['campaign']:,} "
               f"campaign, <{tiers['early_maps']:,} early maps, "
               f"<{tiers['mid_maps']:,} mid maps, <{tiers['endgame']:,} "
               "endgame, above that pinnacle-ready.",
        recommendation=rec,
        metrics={"dps": dps, "source_stat": source, "tier": label,
                 "tiers": dict(tiers)},
    )]


def check_support_sockets(b: Build) -> list[Finding]:
    setup = _main_setup(b)
    if setup is None or not setup.gems:
        return []
    n = len(setup.supports)
    out: list[Finding] = []
    if n >= 5:
        return [Finding(
            id="supports_full", severity="good", category="gems",
            title="Main skill fully supported (5/5)",
            detail=f"{setup.skill} runs {n} support gems.",
            recommendation="", metrics={"supports": n},
        )]
    orb = {2: "Lesser Jeweller's Orb", 3: "Greater Jeweller's Orb",
           4: "Perfect Jeweller's Orb"}.get(n)
    sev = "major" if n <= 2 else ("minor" if b.level >= 60 else "info")
    if n >= 4 and b.level < 80:
        sev = "info"
    from app.archetype import suggest_supports
    candidates = suggest_supports(setup.skill, setup.supports, limit=6)
    cand_txt = (f" Tag-matched candidates from the wiki: "
                f"{', '.join(candidates)}." if candidates else "")
    out.append(Finding(
        id="supports_missing", severity=sev, category="gems",
        title=f"Main skill has {n}/5 support sockets used",
        detail=f"{setup.skill} has {n} supports: "
               f"{', '.join(setup.supports) or 'none'}. Skills start with 2 "
               "support sockets; Lesser/Greater/Perfect Jeweller's Orbs "
               "unlock the 3rd/4th/5th.",
        recommendation=((f"Use a {orb} on {setup.skill} and slot a damage "
                         "support -- each socket is a ~20-40% multiplier, "
                         "the biggest single upgrade available."
                         if orb else
                         f"Fill the empty support socket on {setup.skill}.")
                        + cand_txt),
        metrics={"supports": n, "main_skill": setup.skill,
                 "candidates": candidates},
        wiki_refs=["Gem"],
    ))
    return out


def check_duplicate_supports(b: Build) -> list[Finding]:
    out: list[Finding] = []
    for s in b.skills:
        seen = [g for g in s.supports]
        dupes = {g for g in seen if seen.count(g) > 1}
        if dupes:
            out.append(Finding(
                id=f"dupe_support_{s.skill}", severity="critical",
                category="gems",
                title=f"Duplicate support on {s.skill}",
                detail=f"{s.skill} sockets {', '.join(sorted(dupes))} more "
                       "than once. Support gems of the same category cannot "
                       "be socketed into the same skill -- one of these does "
                       "nothing.",
                recommendation="Swap the duplicate for a different support.",
                metrics={"skill": s.skill, "duplicates": sorted(dupes)},
                wiki_refs=["Gem"],
            ))
    return out


def check_gem_levels(b: Build) -> list[Finding]:
    setup = _main_setup(b)
    if setup is None or not setup.gems:
        return []
    lag = ACFG["gem_level_lag"]
    main = next((g for g in setup.gems if not g.is_support), None)
    if main is None:
        return []
    out: list[Finding] = []
    if b.level >= lag["char_level"] and 0 < main.level < lag["min_gem_level"]:
        out.append(Finding(
            id="gem_level_lag", severity="major", category="gems",
            title=f"Main skill gem is level {main.level} at character "
                  f"level {b.level}",
            detail=f"{main.name} is level {main.level}; uncut skill gems up "
                   "to level 20 drop in endgame areas, and skill gem level "
                   "is one of the strongest damage multipliers.",
            recommendation=f"Engrave a higher-level Uncut Skill Gem for "
                           f"{main.name} (level 20 is the non-corrupted cap).",
            metrics={"gem_level": main.level, "char_level": b.level},
            wiki_refs=["Gem"],
        ))
    if b.level >= ACFG["gem_quality_char_level"] and main.quality == 0:
        out.append(Finding(
            id="gem_quality_zero", severity="minor", category="gems",
            title=f"{main.name} has 0% quality",
            detail="Gemcutter's Prisms add 5% quality each (20% cap) and "
                   "are cheap relative to the benefit at this stage.",
            recommendation=f"Apply Gemcutter's Prisms to {main.name}.",
            metrics={"quality": main.quality},
            wiki_refs=["Gem"],
        ))
    return out


def check_hit_chance(b: Build, ctx: dict) -> list[Finding]:
    if ctx.get("basis") == "minion":
        return []  # minions bring their own accuracy
    hc = _stat(b, "HitChance")
    if hc is None or hc <= 0 or hc >= ACFG["hit_chance_floor"]:
        return []
    return [Finding(
        id="hit_chance_low", severity="major", category="offense",
        title=f"Only {hc:.0f}% chance to hit",
        detail=f"Accuracy gives {hc:.0f}% hit chance -- almost "
               f"{100 - hc:.0f}% of attacks (and their DPS) whiff.",
        recommendation="Add accuracy on gloves/rings/amulet or take "
                       "accuracy nodes; attack builds want 95%+.",
        metrics={"hit_chance": hc},
        wiki_refs=["Evasion"],
    )]


# ------------------------------------------------------------ group support

def check_support_coverage(b: Build, ctx: dict) -> list[Finding]:
    if ctx.get("role") != "support":
        return []
    buffs = ctx.get("buff_gems", [])
    curses = ctx.get("curse_gems", [])
    out: list[Finding] = []
    if not curses:
        out.append(Finding(
            id="support_no_curse", severity="major", category="offense",
            title="No enemy debuff in the support kit",
            detail=f"The build runs {len(buffs)} buff/aura gems "
                   f"({', '.join(buffs) or 'none'}) but no curse. Lowering "
                   "enemy resistances or defences multiplies the whole "
                   "party's damage -- it's the highest-leverage thing a "
                   "support can add.",
            recommendation="Add a resistance-lowering curse matching the "
                           "carry's damage type (e.g. Flammability for a "
                           "fire carry), or an exposure source.",
            metrics={"buffs": buffs, "curses": curses},
            wiki_refs=["Curse", "Resistance"],
        ))
    if len(buffs) < 2:
        out.append(Finding(
            id="support_few_buffs", severity="major", category="offense",
            title="Thin party buff coverage",
            detail=f"Only {len(buffs)} persistent buff/aura gem(s) active. "
                   "A support's spirit should be translating into party-wide "
                   "power.",
            recommendation="Reserve remaining spirit on party-relevant "
                           "persistent buffs; prioritize effects the carry "
                           "cannot easily get themselves.",
            metrics={"buffs": buffs},
            wiki_refs=["Spirit", "Buff"],
        ))
    if not out:
        out.append(Finding(
            id="support_kit", severity="good", category="offense",
            title=f"Party kit: {len(buffs)} buffs/auras + "
                  f"{len(curses)} curse(s)",
            detail=f"Buffs: {', '.join(buffs)}. Curses: {', '.join(curses)}.",
            recommendation="", metrics={"buffs": buffs, "curses": curses},
        ))
    return out


def check_curse_limit(b: Build, ctx: dict) -> list[Finding]:
    curses = ctx.get("curse_gems", [])
    if len(curses) < 2:
        return []
    return [Finding(
        id="curse_limit", severity="info", category="offense",
        title=f"Running {len(curses)} curses -- check your curse limit",
        detail=f"{', '.join(curses)} are socketed, but by default only one "
               "curse can be applied to an enemy; extra applications "
               "overwrite the existing curse.",
        recommendation="Pick up +1 curse limit (passives, gear) or drop to "
                       "the single most valuable curse for your party.",
        metrics={"curses": curses},
        wiki_refs=["Curse"],
    )]


# ------------------------------------------------------------ efficiency

def check_move_speed(b: Build) -> list[Finding]:
    ms = _stat(b, "EffectiveMovementSpeedMod")
    if ms is None or not _is_endgame(b):
        return []
    floor = SETTINGS["efficiency"]["move_speed_low"]
    if ms >= floor:
        return [Finding(
            id="move_speed_ok", severity="good", category="efficiency",
            title=f"Movement speed +{(ms - 1) * 100:.0f}%",
            detail="Fast feet mean more maps per hour.",
            recommendation="", metrics={"move_mod": ms},
        )]
    return [Finding(
        id="move_speed_low", severity="minor", category="efficiency",
        title=f"Low movement speed ({(ms - 1) * 100:+.0f}%)",
        detail=f"Effective movement speed modifier is {ms:.2f}. Time spent "
               "walking is the biggest hidden tax on maps (and divines) per "
               "hour.",
        recommendation="Get 30%+ movement speed boots; check for speed "
                       "penalties from body armour or shield, and consider "
                       "travel-skill or onslaught sources.",
        metrics={"move_mod": ms, "floor": floor},
    )]


# ------------------------------------------------------------------ gear

def check_empty_slots(b: Build) -> list[Finding]:
    filled = {e.slot for e in b.equipment if e.name or e.mods}
    missing = [s for s in CORE_SLOTS if s not in filled]
    if not b.equipment or not missing:
        return []
    return [Finding(
        id="empty_slots", severity="major", category="gear",
        title=f"Empty gear slots: {', '.join(missing)}",
        detail="Every empty slot is free life, resistances and damage left "
               "on the table.",
        recommendation="Fill them -- even a 1-alch rare beats an empty slot.",
        metrics={"missing": missing},
    )]


def check_attr_requirements(b: Build) -> list[Finding]:
    out: list[Finding] = []
    for attr, have_stat, req_stat in (("Strength", "Str", "ReqStr"),
                                      ("Dexterity", "Dex", "ReqDex"),
                                      ("Intelligence", "Int", "ReqInt")):
        have = _stat(b, have_stat)
        need = _stat(b, req_stat)
        if have is None or need is None:
            continue
        if need > have:
            out.append(Finding(
                id=f"attr_short_{attr.lower()}", severity="critical",
                category="gear",
                title=f"{attr} requirement not met",
                detail=f"Gear/gems require {need:.0f} {attr} but the build "
                       f"has {have:.0f} -- something is currently inactive.",
                recommendation=f"Add +{need - have:.0f} {attr} from gear or "
                               "travel nodes, or swap the offending item/gem.",
                metrics={"have": have, "need": need},
            ))
    return out


# ------------------------------------------------------------------ driver

SIMPLE_CHECKS = [
    check_resistances, check_chaos_res, check_pool, check_max_hits,
    check_phys_layer, check_spirit, check_es_bypass, check_recovery,
    check_support_sockets, check_duplicate_supports, check_gem_levels,
    check_empty_slots, check_attr_requirements, check_move_speed,
]

# Roadmap staging: survive first, then damage, then farming efficiency.
PHASE_BY_CATEGORY = {"defense": "survive", "gear": "survive",
                     "offense": "damage", "gems": "damage",
                     "efficiency": "efficiency"}
CONTEXT_CHECKS = [
    check_dps, check_hit_chance, check_support_coverage, check_curse_limit,
]


def _grade(findings: list[Finding], category_filter: set[str]) -> str:
    score = 100
    for f in findings:
        if f.category in category_filter:
            score -= SEVERITY_WEIGHT[f.severity]
    for cutoff, letter in ((95, "A"), (85, "B"), (70, "C"), (50, "D")):
        if score >= cutoff:
            return letter
    return "F"


def analyze_build(build: dict | Build, role: str = "auto") -> dict:
    """Run every check; return findings + grades, JSON-serializable.

    role: "auto" (detect), "dps", or "support" -- support builds are graded
    on party contribution instead of personal DPS.
    """
    b = build if isinstance(build, Build) else parse_build(build)
    ctx = detect_archetype(b)
    if role in ("dps", "support"):
        ctx["role"] = role
        ctx["role_forced"] = True
        if role == "support" and not ctx["summary"].startswith("group-support"):
            ctx["summary"] = f"group-support archetype ({ctx['summary']})"

    findings: list[Finding] = []
    for check in SIMPLE_CHECKS:
        findings.extend(check(b))
    for check in CONTEXT_CHECKS:
        findings.extend(check(b, ctx))
    findings.sort(key=lambda f: SEVERITY_ORDER[f.severity])
    finding_dicts = [
        dict(asdict(f), phase=PHASE_BY_CATEGORY.get(f.category, "damage"))
        for f in findings
    ]

    issues = [f for f in findings if f.severity in ("critical", "major", "minor")]
    return {
        "class": b.char_class,
        "ascendancy": b.ascendancy,
        "level": b.level,
        "main_skill": b.main_skill,
        "main_supports": (_main_setup(b).supports if _main_setup(b) else []),
        "endgame": _is_endgame(b),
        "archetype": ctx,
        "role": ctx["role"],
        "offense_label": ("Party support" if ctx["role"] == "support"
                          else "Offense"),
        "grades": {
            "survivability": _grade(findings, {"defense", "gear"})
            if b.pob_stats else "?",
            "offense": _grade(findings, {"offense", "gems"})
            if b.pob_stats else "?",
        },
        "findings": finding_dicts,
        "issue_count": {
            sev: sum(1 for f in issues if f.severity == sev)
            for sev in ("critical", "major", "minor")
        },
        "stats_available": bool(b.pob_stats),
        "assumptions": [
            "Tier thresholds (pool, max-hit, DPS bands) are community "
            "heuristics -- tune them in config/settings.yaml under "
            "'analysis:'.",
            "PoB-computed stats are trusted as-is; re-export after gear "
            "changes to refresh them.",
            f"Game-rule values checked against wiki snapshot for patch "
            f"{SETTINGS['game']['current_version']}.",
        ],
    }
