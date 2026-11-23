import html


def chip(text: str, tone: str = "neutral", href: str | None = None, extra: str = "") -> str:
    tone_class = "" if tone == "neutral" else f" rs-{tone}"
    label = html.escape(str(text))
    cls = f"rs-chip{tone_class} {extra}".strip()
    if href:
        safe = html.escape(href, quote=True)
        attrs = f'href="{safe}" target="_blank" rel="noopener noreferrer"'
        return f'<a class="{cls}" {attrs}>{label}</a>'
    return f'<span class="{cls}">{label}</span>'


def chips(items: list[str]) -> str:
    return f'<div class="rs-chips">{"".join(items)}</div>' if items else ""


def score_tone(score: float) -> str:
    if score >= 80:
        return "green"
    if score >= 60:
        return "amber"
    return "red"


def score_bar(score: float) -> str:
    width = max(0, min(100, round(score)))
    tone = score_tone(score)
    return f'<div class="rs-bar rs-bar-{tone}"><span style="width:{width}%"></span></div>'


STATUS_TONES = {
    "embedded": "green",
    "completed": "green",
    "failed": "red",
    "queue_failed": "red",
    "embedding_failed": "red",
    "uploaded": "blue",
    "queued": "blue",
    "extracting": "amber",
    "embedding_queued": "amber",
    "embedding": "amber",
    "ok": "green",
    "success": "green",
    "skipped": "neutral",
}


def status_chip(status: str | None) -> str:
    value = (status or "unknown").lower()
    label = "completed" if value == "embedded" else value.replace("_", " ")
    return chip(label, STATUS_TONES.get(value, "neutral"))


def experience_text(years: float | None, source: str | None) -> str:
    if years is None:
        return "experience not stated"
    text = f"{years:g} yrs"
    return f"{text}, {source}" if source else text
