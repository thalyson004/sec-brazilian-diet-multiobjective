"""Fixed-width positions for POF 2017-2018 CONSUMO_ALIMENTAR records.

Positions are zero-based. They were checked against the IBGE variable
dictionary distributed in Documentacao_20230713.zip. Keep this mapping
versioned with the source archive; do not infer positions from the text file.
"""

FIELDS = {
    "UF": (0, 2),
    "COD_UPA": (7, 9),
    "NUM_DOM": (16, 2),
    "NUM_UC": (18, 1),
    "COD_INFORMANTE": (19, 2),
    "QUADRO": (21, 2),
    "V9001": (31, 7),
    "V9015": (38, 3),
    "V9017": (43, 1),
    "COD_PREPARACAO_FINAL": (59, 2),
    "QTD": (68, 9),
    "COD_TBCA": (77, 6),
    "DIA_ATIPICO": (543, 1),
}

MIN_RECORD_LENGTH = max(start + length for start, length in FIELDS.values())
VALID_DAYS = {"72": "1", "73": "2"}

# Official dictionary positions 84--489 (one-based), 14 characters per field.
# These are absolute nutrient quantities for the recorded consumption line.
NUTRIENT_FIELDS = (
    "ENERGIA_KCAL", "ENERGIA_KJ", "PTN", "CHOTOT", "FIBRA", "LIP",
    "COLEST", "AGSAT", "AGMONO", "AGPOLI", "AGTRANS", "CALCIO",
    "FERRO", "SODIO", "MAGNESIO", "FOSFORO", "POTASSIO", "COBRE",
    "ZINCO", "VITA_RAE", "TIAMINA", "RIBOFLAVINA", "NIACINA",
    "PIRIDOXAMINA", "COBALAMINA", "VITD", "VITE", "VITC", "FOLATO",
)
NUTRIENT_START = 83
NUTRIENT_WIDTH = 14


def field(record: str, name: str) -> str:
    start, length = FIELDS[name]
    return record[start : start + length].strip()


def code(value: object) -> str | None:
    """Normalize a numeric code for joins without inventing missing values."""
    raw = str(value).strip() if value is not None else ""
    if not raw:
        return None
    if not raw.isdigit():
        return None
    return str(int(raw))
