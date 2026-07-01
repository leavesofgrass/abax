"""Map an amateur-radio callsign to its DXCC entity (country).

Pure stdlib, pure data + string logic. A curated (not exhaustive) prefix->entity
table drives a longest-prefix match. This is a bundled offline lookup -- no
network -- so it covers the common DXCC entities and their well-known prefix
blocks rather than the full 340-odd ITU allocation.

The matcher normalises the call, strips a leading ``PREFIX/`` re-location prefix
(e.g. ``DL/W1AW`` -> Germany) and trailing operational suffixes (``/P``, ``/M``,
``/MM``, ``/QRP``, ``/A``, ``/0``..``/9`` ...), then does a longest-prefix match
on the leading letters+digits of the base call.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Prefix -> entity table.
#
# Longest-prefix wins, so more specific blocks (KH6, KL7, KP4) can sit alongside
# the generic ones (K, W, N) that would otherwise swallow them. Prefixes are the
# leading letters+digits of a callsign; keep them uppercase.
# --------------------------------------------------------------------------- #
PREFIXES: dict[str, str] = {
    # --- United States (and specific island/territory blocks) --------------- #
    "K": "United States",
    "W": "United States",
    "N": "United States",
    "AA": "United States",
    "AB": "United States",
    "AC": "United States",
    "AD": "United States",
    "AE": "United States",
    "AF": "United States",
    "AG": "United States",
    "AI": "United States",
    "AJ": "United States",
    "AK": "United States",
    "KH6": "Hawaii",
    "KH7": "Hawaii",
    "NH6": "Hawaii",
    "WH6": "Hawaii",
    "AH6": "Hawaii",
    "KL": "Alaska",
    "KL7": "Alaska",
    "NL7": "Alaska",
    "WL7": "Alaska",
    "AL7": "Alaska",
    "KP4": "Puerto Rico",
    "NP4": "Puerto Rico",
    "WP4": "Puerto Rico",
    "KP2": "US Virgin Islands",
    "NP2": "US Virgin Islands",
    "WP2": "US Virgin Islands",
    # --- Canada ------------------------------------------------------------- #
    "VE": "Canada",
    "VA": "Canada",
    "VO": "Canada",
    "VY": "Canada",
    "CY": "Canada",
    # --- British Isles ------------------------------------------------------ #
    "G": "England",
    "M": "England",
    "2E": "England",
    "GM": "Scotland",
    "MM": "Scotland",
    "2M": "Scotland",
    "GW": "Wales",
    "MW": "Wales",
    "2W": "Wales",
    "GI": "Northern Ireland",
    "MI": "Northern Ireland",
    "2I": "Northern Ireland",
    "GD": "Isle of Man",
    "GJ": "Jersey",
    "GU": "Guernsey",
    "EI": "Ireland",
    "EJ": "Ireland",
    # --- Western / Central Europe ------------------------------------------- #
    "DA": "Germany",
    "DB": "Germany",
    "DC": "Germany",
    "DD": "Germany",
    "DF": "Germany",
    "DG": "Germany",
    "DH": "Germany",
    "DJ": "Germany",
    "DK": "Germany",
    "DL": "Germany",
    "DM": "Germany",
    "DO": "Germany",
    "F": "France",
    "TM": "France",
    "I": "Italy",
    "IK": "Italy",
    "IZ": "Italy",
    "IW": "Italy",
    "EA": "Spain",
    "EB": "Spain",
    "EC": "Spain",
    "ED": "Spain",
    "EE": "Spain",
    "EF": "Spain",
    "EG": "Spain",
    "EH": "Spain",
    "CT": "Portugal",
    "CQ": "Portugal",
    "CR": "Portugal",
    "PA": "Netherlands",
    "PB": "Netherlands",
    "PC": "Netherlands",
    "PD": "Netherlands",
    "PE": "Netherlands",
    "PF": "Netherlands",
    "PG": "Netherlands",
    "PH": "Netherlands",
    "PI": "Netherlands",
    "ON": "Belgium",
    "OO": "Belgium",
    "OP": "Belgium",
    "OQ": "Belgium",
    "OR": "Belgium",
    "OS": "Belgium",
    "OT": "Belgium",
    "HB": "Switzerland",
    "HB0": "Liechtenstein",
    "OE": "Austria",
    "LX": "Luxembourg",
    # --- Nordics ------------------------------------------------------------ #
    "SM": "Sweden",
    "SA": "Sweden",
    "SB": "Sweden",
    "SC": "Sweden",
    "SD": "Sweden",
    "SE": "Sweden",
    "SF": "Sweden",
    "SG": "Sweden",
    "SH": "Sweden",
    "SI": "Sweden",
    "SJ": "Sweden",
    "SK": "Sweden",
    "SL": "Sweden",
    "LA": "Norway",
    "LB": "Norway",
    "LC": "Norway",
    "LD": "Norway",
    "LE": "Norway",
    "LF": "Norway",
    "LG": "Norway",
    "LH": "Norway",
    "LI": "Norway",
    "LJ": "Norway",
    "LK": "Norway",
    "LL": "Norway",
    "LM": "Norway",
    "LN": "Norway",
    "OH": "Finland",
    "OF": "Finland",
    "OG": "Finland",
    "OH0": "Aland Islands",
    "OZ": "Denmark",
    "OU": "Denmark",
    "OV": "Denmark",
    "OW": "Denmark",
    "OX": "Greenland",
    "OY": "Faroe Islands",
    "TF": "Iceland",
    # --- Eastern / Southern Europe ------------------------------------------ #
    "SP": "Poland",
    "SN": "Poland",
    "SO": "Poland",
    "SQ": "Poland",
    "SR": "Poland",
    "SV": "Greece",
    "SW": "Greece",
    "SX": "Greece",
    "SY": "Greece",
    "SZ": "Greece",
    "OK": "Czech Republic",
    "OL": "Czech Republic",
    "OM": "Slovakia",
    "HA": "Hungary",
    "HG": "Hungary",
    "YO": "Romania",
    "YP": "Romania",
    "LZ": "Bulgaria",
    "S5": "Slovenia",
    "9A": "Croatia",
    "YU": "Serbia",
    "YT": "Serbia",
    "Z3": "North Macedonia",
    "E7": "Bosnia and Herzegovina",
    "ZA": "Albania",
    "SP0": "Poland",
    "YL": "Latvia",
    "LY": "Lithuania",
    "ES": "Estonia",
    "UR": "Ukraine",
    "US": "Ukraine",
    "UT": "Ukraine",
    "UU": "Ukraine",
    "UX": "Ukraine",
    "UY": "Ukraine",
    "EW": "Belarus",
    "EU": "Belarus",
    "ER": "Moldova",
    "EA6": "Balearic Islands",
    "EA8": "Canary Islands",
    "EA9": "Ceuta and Melilla",
    "9H": "Malta",
    "5B": "Cyprus",
    "TA": "Turkey",
    "TC": "Turkey",
    # --- Russia and CIS ----------------------------------------------------- #
    "R": "Russia",
    "UA": "Russia",
    "UB": "Russia",
    "UC": "Russia",
    "UD": "Russia",
    "UE": "Russia",
    "UF": "Russia",
    "UG": "Russia",
    "UH": "Russia",
    "UI": "Russia",
    "UN": "Kazakhstan",
    "EX": "Kyrgyzstan",
    "EY": "Tajikistan",
    "EZ": "Turkmenistan",
    "UK": "Uzbekistan",
    "4L": "Georgia",
    "4J": "Azerbaijan",
    "4K": "Azerbaijan",
    "EK": "Armenia",
    # --- Asia --------------------------------------------------------------- #
    "JA": "Japan",
    "JB": "Japan",
    "JC": "Japan",
    "JD": "Japan",
    "JE": "Japan",
    "JF": "Japan",
    "JG": "Japan",
    "JH": "Japan",
    "JI": "Japan",
    "JJ": "Japan",
    "JK": "Japan",
    "JL": "Japan",
    "JM": "Japan",
    "JN": "Japan",
    "JO": "Japan",
    "JP": "Japan",
    "JQ": "Japan",
    "JR": "Japan",
    "JS": "Japan",
    "7J": "Japan",
    "7K": "Japan",
    "7L": "Japan",
    "7M": "Japan",
    "7N": "Japan",
    "8J": "Japan",
    "8N": "Japan",
    "B": "China",
    "BA": "China",
    "BD": "China",
    "BG": "China",
    "BH": "China",
    "BI": "China",
    "BV": "Taiwan",
    "BY": "China",
    "VR": "Hong Kong",
    "XX9": "Macao",
    "HL": "South Korea",
    "DS": "South Korea",
    "6K": "South Korea",
    "6L": "South Korea",
    "P5": "North Korea",
    "VU": "India",
    "AT": "India",
    "4S": "Sri Lanka",
    "S2": "Bangladesh",
    "AP": "Pakistan",
    "9N": "Nepal",
    "XZ": "Myanmar",
    "HS": "Thailand",
    "E2": "Thailand",
    "XU": "Cambodia",
    "XW": "Laos",
    "3W": "Vietnam",
    "XV": "Vietnam",
    "9M": "Malaysia",
    "9V": "Singapore",
    "YB": "Indonesia",
    "YC": "Indonesia",
    "YD": "Indonesia",
    "DU": "Philippines",
    "DV": "Philippines",
    "DW": "Philippines",
    "DX": "Philippines",
    "DY": "Philippines",
    "DZ": "Philippines",
    "A4": "Oman",
    "A6": "United Arab Emirates",
    "A7": "Qatar",
    "A9": "Bahrain",
    "HZ": "Saudi Arabia",
    "9K": "Kuwait",
    "YK": "Syria",
    "YI": "Iraq",
    "JY": "Jordan",
    "OD": "Lebanon",
    "4X": "Israel",
    "4Z": "Israel",
    "EP": "Iran",
    "YA": "Afghanistan",
    # --- Oceania ------------------------------------------------------------ #
    "VK": "Australia",
    "AX": "Australia",
    "ZL": "New Zealand",
    "ZM": "New Zealand",
    "P2": "Papua New Guinea",
    "KH2": "Guam",
    "3D2": "Fiji",
    "FO": "French Polynesia",
    "FK": "New Caledonia",
    # --- Africa ------------------------------------------------------------- #
    "ZS": "South Africa",
    "ZR": "South Africa",
    "ZU": "South Africa",
    "SU": "Egypt",
    "CN": "Morocco",
    "7X": "Algeria",
    "3V": "Tunisia",
    "5A": "Libya",
    "ST": "Sudan",
    "5Z": "Kenya",
    "5H": "Tanzania",
    "5X": "Uganda",
    "9J": "Zambia",
    "Z2": "Zimbabwe",
    "5N": "Nigeria",
    "9G": "Ghana",
    "TR": "Gabon",
    "TT": "Chad",
    "3B8": "Mauritius",
    "5R": "Madagascar",
    "3C": "Equatorial Guinea",
    "TY": "Benin",
    # --- Americas (non-US/Canada) ------------------------------------------ #
    "PY": "Brazil",
    "PP": "Brazil",
    "PQ": "Brazil",
    "PR": "Brazil",
    "PS": "Brazil",
    "PT": "Brazil",
    "PU": "Brazil",
    "ZV": "Brazil",
    "ZW": "Brazil",
    "ZX": "Brazil",
    "ZY": "Brazil",
    "ZZ": "Brazil",
    "LU": "Argentina",
    "AY": "Argentina",
    "AZ": "Argentina",
    "L2": "Argentina",
    "L3": "Argentina",
    "L4": "Argentina",
    "L5": "Argentina",
    "L6": "Argentina",
    "L7": "Argentina",
    "L8": "Argentina",
    "L9": "Argentina",
    "LW": "Argentina",
    "XE": "Mexico",
    "XF": "Mexico",
    "4A": "Mexico",
    "6D": "Mexico",
    "CE": "Chile",
    "CA": "Chile",
    "CB": "Chile",
    "CC": "Chile",
    "CD": "Chile",
    "HK": "Colombia",
    "HJ": "Colombia",
    "OA": "Peru",
    "YV": "Venezuela",
    "YY": "Venezuela",
    "HC": "Ecuador",
    "CP": "Bolivia",
    "CX": "Uruguay",
    "ZP": "Paraguay",
    "PZ": "Suriname",
    "8R": "Guyana",
    "TG": "Guatemala",
    "TI": "Costa Rica",
    "HP": "Panama",
    "YS": "El Salvador",
    "HR": "Honduras",
    "YN": "Nicaragua",
    "V3": "Belize",
    "CM": "Cuba",
    "CO": "Cuba",
    "HH": "Haiti",
    "HI": "Dominican Republic",
    "J6": "Saint Lucia",
    "J3": "Grenada",
    "8P": "Barbados",
    "9Y": "Trinidad and Tobago",
    "FM": "Martinique",
    "FG": "Guadeloupe",
    "PJ": "Curacao",
    "6Y": "Jamaica",
    "C6": "Bahamas",
    "VP9": "Bermuda",
    "ZF": "Cayman Islands",
}

# Operational suffixes that carry no country information and should be dropped
# from the end of a callsign before matching (e.g. ``W1AW/QRP`` -> ``W1AW``).
_IGNORED_SUFFIXES: frozenset[str] = frozenset(
    {"P", "M", "MM", "AM", "QRP", "A"}
)


def _strip_suffix(call: str) -> str:
    """Drop trailing operational suffixes after the last ``/`` if ignorable.

    Recognised suffixes: the ones in :data:`_IGNORED_SUFFIXES` plus a bare
    single digit (a re-location call-area indicator such as ``W1AW/7``).
    """
    while "/" in call:
        head, _, tail = call.rpartition("/")
        if tail in _IGNORED_SUFFIXES or (len(tail) == 1 and tail.isdigit()):
            call = head
        else:
            break
    return call


def _leading_token(call: str) -> str:
    """Leading run of letters+digits of a base call (stops at first ``/``)."""
    base = call.split("/", 1)[0]
    out: list[str] = []
    for ch in base:
        if ch.isalnum():
            out.append(ch)
        else:
            break
    return "".join(out)


def _longest_prefix_match(token: str) -> str | None:
    """Longest-prefix match of ``token`` against :data:`PREFIXES`."""
    for length in range(len(token), 0, -1):
        entity = PREFIXES.get(token[:length])
        if entity is not None:
            return entity
    return None


def entity_for_call(callsign: str) -> str | None:
    """Return the DXCC entity name for ``callsign``, or ``None`` if unmatched.

    Normalises to uppercase and strips surrounding whitespace. If the substring
    before the first ``/`` is itself a known prefix (e.g. ``DL/W1AW``), that
    re-location prefix wins and determines the entity. Otherwise trailing
    operational suffixes (``/P``, ``/QRP``, ``/7`` ...) are dropped and the base
    call is matched by longest prefix.
    """
    if not callsign:
        return None
    call = callsign.strip().upper()
    if not call:
        return None

    # Leading PREFIX/CALL re-location: the part before the first slash wins if it
    # is itself a known prefix.
    if "/" in call:
        head = call.split("/", 1)[0]
        head_token = _leading_token(head)
        head_entity = _longest_prefix_match(head_token) if head_token else None
        if head_entity is not None and head_token == head:
            return head_entity

    call = _strip_suffix(call)
    token = _leading_token(call)
    if not token:
        return None
    return _longest_prefix_match(token)
