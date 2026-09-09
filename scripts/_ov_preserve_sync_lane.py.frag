def preserve_sync_lane(existing: str, new_text: str, heading: str) -> str:
    """Union lane bullets across mechanical digest rewrites.

    OVERSEER_PRESERVE_SYNC_UNION_2026_09_04 — keep prior bullets when the new
    cycle adds different ones (do not drop Hub registry honesty etc.).
    """
    new_body = extract_heading_body(new_text, heading)
    old_body = extract_heading_body(existing, heading)
    new_bullets = [ln for ln in new_body.splitlines() if ln.startswith("- ")]
    old_bullets = [ln for ln in old_body.splitlines() if ln.startswith("- ")]
    if not old_bullets:
        return new_text
    if not new_bullets:
        body_lines = old_bullets
    else:
        none_mark = "(none this cycle)"
        seen: set[str] = set()
        body_lines: list[str] = []
        for ln in old_bullets + new_bullets:
            key = ln.strip()
            if none_mark in key and any(none_mark not in x for x in old_bullets + new_bullets):
                continue
            if key in seen:
                continue
            seen.add(key)
            body_lines.append(ln)
    marker = f"## {heading}"
    idx = new_text.find(marker)
    if idx < 0:
        return new_text
    after = new_text[idx + len(marker) :]
    nxt = after.find("\n## ")
    replacement = marker + "\n\n" + "\n".join(body_lines).rstrip() + "\n"
    if nxt < 0:
        return new_text[:idx] + replacement
    end = idx + len(marker) + nxt
    return new_text[:idx] + replacement + new_text[end:]
