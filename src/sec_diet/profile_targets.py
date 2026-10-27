"""Reference anthropometry and sourced nutrient goals for the four profiles."""

from __future__ import annotations

from .layout import NUTRIENT_FIELDS


def maintenance_energy(profile: dict) -> float:
    """2023 adult low-active EER, height in cm and weight in kg (Table S-3)."""
    if profile["physical_activity"] != "low_active":
        raise ValueError("The registered profiles require the low-active category")
    age, height, weight = profile["age_years"], 100 * profile["height_m"], profile["weight_kg"]
    if profile["sex_code"] == "2":
        return 575.77 - 7.01 * age + 6.60 * height + 12.14 * weight
    if profile["sex_code"] == "1":
        return 581.47 - 10.83 * age + 8.30 * height + 14.94 * weight
    raise ValueError("Unknown POF sex code")


def targets(profile: dict) -> list[dict]:
    female, older = profile["sex_code"] == "2", profile["age_years"] >= 51
    rows = []

    def add(name, unit, lower=None, upper=None, kind="RDA", source="healthcanada2025elements", **extra):
        if name not in NUTRIENT_FIELDS:
            raise ValueError(f"Unknown POF nutrient {name}")
        rows.append(dict(nutrient=name, unit=unit, lower=lower, upper=upper,
                         recommendation_type=kind, citation_key=source, **extra))

    add("PTN", "g", .8 * profile["weight_kg"], kind="RDA and AMDR", source="healthcanada2025macronutrients",
        lower_energy_fraction=.10, upper_energy_fraction=.35, kcal_per_g=4)
    add("CHOTOT", "g", kind="AMDR", source="healthcanada2025macronutrients",
        lower_energy_fraction=.45, upper_energy_fraction=.65, kcal_per_g=4,
        field_note="POF reported total carbohydrate is the operational measure; no digestible-carbohydrate RDA is imposed.")
    add("LIP", "g", kind="AMDR intersected with WHO maximum", source="healthcanada2025macronutrients,who2023fatsupdate",
        lower_energy_fraction=.20, upper_energy_fraction=.30, kcal_per_g=9)
    add("FIBRA", "g", max(25, (21 if older else 25) if female else (30 if older else 38)),
        kind="AI intersected with WHO minimum", source="healthcanada2025macronutrients,who2023fatsupdate")
    add("AGSAT", "g", kind="WHO recommended maximum", source="who2023fatsupdate",
        upper_energy_fraction=.10, kcal_per_g=9)
    add("AGTRANS", "g", kind="WHO recommended maximum", source="who2023fatsupdate",
        upper_energy_fraction=.01, kcal_per_g=9)
    add("SODIO", "mg", upper=2000, kind="WHO recommended maximum", source="who2012sodium")
    add("CALCIO", "mg", 1200 if female and older else 1000, 2000 if older else 2500, kind="RDA and UL")
    add("FERRO", "mg", 18 if female and not older else 8, 45, kind="RDA and UL")
    add("MAGNESIO", "mg", (320 if older else 310) if female else (420 if older else 400))
    add("FOSFORO", "mg", 700, 4000, kind="RDA and UL")
    add("POTASSIO", "mg", 2600 if female else 3400, kind="AI")
    add("COBRE", "mg", .9, 10, kind="RDA and UL")
    add("ZINCO", "mg", 8 if female else 11, 40, kind="RDA and UL")
    vitamin_source = "healthcanada2025vitamins"
    add("VITA_RAE", "ug RAE", 700 if female else 900, source=vitamin_source)
    add("TIAMINA", "mg", 1.1 if female else 1.2, source=vitamin_source)
    add("RIBOFLAVINA", "mg", 1.1 if female else 1.3, source=vitamin_source)
    add("NIACINA", "mg NE", 14 if female else 16, source=vitamin_source)
    add("PIRIDOXAMINA", "mg", (1.5 if female else 1.7) if older else 1.3, 100,
        kind="RDA and UL", source=vitamin_source)
    add("COBALAMINA", "ug", 2.4, source=vitamin_source)
    add("VITD", "ug", 15, 100, kind="RDA and UL", source=vitamin_source)
    add("VITE", "mg alpha-tocopherol", 15, source=vitamin_source)
    add("VITC", "mg", 75 if female else 90, 2000, kind="RDA and UL", source=vitamin_source)
    return rows


def bounds(row: dict, energy: float) -> tuple[float | None, float | None]:
    lower, upper = row["lower"], row["upper"]
    if "lower_energy_fraction" in row:
        value = row["lower_energy_fraction"] * energy / row["kcal_per_g"]
        lower = max(lower or 0, value)
    if "upper_energy_fraction" in row:
        value = row["upper_energy_fraction"] * energy / row["kcal_per_g"]
        upper = min(upper, value) if upper is not None else value
    return lower, upper
