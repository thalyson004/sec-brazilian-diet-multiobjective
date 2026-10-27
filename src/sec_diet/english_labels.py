"""Reviewed English publication labels; original POF codes remain the identifiers."""
from functools import lru_cache
import json
from pathlib import Path

GROUPS = {
    "aves e ovos": "Poultry and eggs",
    "cereais e leguminosas": "Cereals and pulses",
    "frutas": "Fruit",
    "laticínios": "Dairy products",
    "pescados e frutos do mar": "Fish and seafood",
    "hortaliças tuberosas": "Roots and tubers",
    "bebidas não alcoólicas e infusões": "Nonalcoholic beverages and infusions",
    "panificados": "Bread and baked goods",
    "sais e condimentos": "Salt and condiments",
    "farinhas, féculas e massas": "Flours, starches and pasta",
    "açúcares e produtos de confeitaria": "Sugar and confectionery",
    "bebidas alcoólicas": "Alcoholic beverages",
    "hortaliças folhosas, frutosas e outras": "Leafy and other vegetables",
    "carnes e vísceras": "Meat and offal",
    "óleos e gorduras": "Oils and fats",
    "cocos, castanhas e nozes": "Coconut, nuts and seeds",
    "carnes industrializadas": "Processed meat",
    "miscelâneas": "Mixed dishes and other foods",
    "Tap water": "Tap water",
}


def english_group(name):
    if name in GROUPS:
        return GROUPS[name]
    if name == "Invented group":
        return name
    raise ValueError(f"Food group lacks a reviewed English label: {name}")


@lru_cache(maxsize=1)
def food_labels():
    path = Path(__file__).resolve().parents[2] / "docs/profiles/food-labels-en.json"
    return json.loads(path.read_text(encoding="utf-8"))["labels"]


def english_food(code):
    value = food_labels().get(str(code))
    if value is None:
        raise ValueError(f"Food code lacks a reviewed English label: {code}")
    return value["english"]
