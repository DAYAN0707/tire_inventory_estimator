import re


def parse_tire_spec(spec_str):
    
    if not spec_str:
        return {"inch": None}

    match = re.search(r"R(\d+)", spec_str.upper())
    if not match:
        return {"inch": None}

    return {
        "inch": int(match.group(1))
    }

# 例: 195/65R15 → inch=15 を取り出す