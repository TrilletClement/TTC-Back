def unique_name(base_name: str, existing_names: set[str]) -> str:
    candidate = base_name
    n = 2
    while candidate in existing_names:
        candidate = f"{base_name} {n}"
        n += 1
    return candidate
