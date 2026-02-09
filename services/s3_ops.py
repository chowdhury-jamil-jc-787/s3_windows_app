def is_prefix(key: str) -> bool:
    return key.endswith("/")


def join_prefix(prefix: str, name: str) -> str:
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return f"{prefix}{name}"


def parent_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    p = prefix.rstrip("/")
    if "/" not in p:
        return ""
    return p.rsplit("/", 1)[0] + "/"
