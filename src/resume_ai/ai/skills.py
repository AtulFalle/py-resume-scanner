"""Deterministic, alias-aware skill matching.

The generated patterns are valid both as Python `re` patterns and as
PostgreSQL regular expressions (used with the case-insensitive `~*`
operator), so the same matching rules apply in SQL filters and in code.
"""

import re

# Each group lists spellings that should be treated as the same skill.
# Keep entries lower-case. Add to this as you see misses.
ALIAS_GROUPS: list[set[str]] = [
    {"angular", "angularjs", "angular.js", "angular js"},
    {"react", "reactjs", "react.js", "react js"},
    {"react native", "react-native"},
    {"vue", "vuejs", "vue.js"},
    {"node.js", "nodejs", "node js", "node"},
    {"next.js", "nextjs"},
    {"express", "express.js", "expressjs"},
    {"javascript", "java script", "ecmascript"},
    {"typescript", "type script"},
    {"c#", "c sharp", "csharp"},
    {".net", "dotnet", "dot net", "asp.net", ".net core", "asp.net core"},
    {"c++", "cpp"},
    {"golang", "go lang"},
    {"postgresql", "postgres", "postgre sql", "postgre"},
    {"mysql", "my sql"},
    {"mongodb", "mongo db", "mongo"},
    {"sql server", "mssql", "ms sql", "microsoft sql server"},
    {"kubernetes", "k8s"},
    {"aws", "amazon web services"},
    {"gcp", "google cloud", "google cloud platform"},
    {"azure", "microsoft azure"},
    {"machine learning", "ml"},
    {"artificial intelligence", "ai"},
    {"natural language processing", "nlp"},
    {"ci/cd", "cicd", "ci cd", "continuous integration"},
    {"microsoft excel", "ms excel", "advanced excel"},
    {"power bi", "powerbi"},
    {"sap fico", "sap fi/co", "sap fi co"},
    {"gst", "goods and services tax"},
    {"human resources", "hr"},
    {"ui/ux", "ui ux", "ux/ui", "user experience"},
    {"html", "html5", "xhtml"},
    {"css", "css3"},
]

_ALIAS_LOOKUP: dict[str, set[str]] = {}
for _group in ALIAS_GROUPS:
    for _name in _group:
        _ALIAS_LOOKUP[_name] = _group

_FRONTEND_FRAMEWORKS = {
    "angular", "angularjs", "react", "reactjs", "react.js", "vue", "vuejs", "vue.js",
    "svelte", "next.js", "nextjs", "nuxt", "ember",
}

# One-way implications for resume filtering: a resume that lists any skill on
# the right demonstrably has the skill on the left (SCSS → CSS, Angular → HTML),
# even if the generic name is never written. Not used for query parsing.
IMPLIED_BY: dict[str, set[str]] = {
    "css": {"scss", "sass", "less", "tailwind", "tailwind css", "tailwindcss", "bootstrap",
            *_FRONTEND_FRAMEWORKS},
    "html": {*_FRONTEND_FRAMEWORKS, "jsx", "tsx"},
    "javascript": {"typescript", "node.js", "nodejs", *_FRONTEND_FRAMEWORKS},
    "devops": {"docker", "kubernetes", "k8s", "ci/cd", "cicd", "jenkins", "terraform",
               "github actions", "gitlab ci", "ansible"},
}

# Characters that can be part of a skill token; a match must not be
# surrounded by them (so "java" doesn't match "javascript").
_TOKEN_CHARS = "a-z0-9+#"
_PREFIX = f"(^|[^{_TOKEN_CHARS}])"
_SUFFIX = f"($|[^{_TOKEN_CHARS}])"

_REGEX_SPECIAL = set(".^$*+?()[]{}|\\")


def normalize_skill(name: str) -> str:
    return " ".join(name.lower().split())


def skill_variants(name: str) -> set[str]:
    skill = normalize_skill(name)
    if not skill:
        return set()

    variants = {skill}
    variants |= _ALIAS_LOOKUP.get(skill, set())

    # Generic "foo" ↔ "foojs" ↔ "foo.js" handling for unlisted JS libraries.
    for variant in list(variants):
        if variant.endswith(".js"):
            base = variant[:-3].rstrip(" .")
        elif variant.endswith("js") and len(variant) > 4:
            base = variant[:-2].rstrip(" .")
        else:
            continue
        if base:
            variants.update({base, base + "js", base + ".js"})

    return {variant for variant in variants if variant}


def _escape(text: str) -> str:
    parts: list[str] = []
    for char in text:
        if char == " ":
            parts.append(r"\s+")
        elif char in _REGEX_SPECIAL:
            parts.append("\\" + char)
        else:
            parts.append(char)
    return "".join(parts)


def skill_pattern(name: str) -> str | None:
    """Regex matching any spelling of a skill as a whole token."""
    variants = sorted(skill_variants(name), key=len, reverse=True)
    if not variants:
        return None
    alternatives = "|".join(_escape(variant) for variant in variants)
    return f"{_PREFIX}({alternatives}){_SUFFIX}"


def resume_skill_pattern(name: str) -> str | None:
    """Like skill_pattern, but also accepts skills that imply this one.

    Use this for filtering resumes: "CSS" matches a resume that says "SCSS".
    """
    variants = skill_variants(name)
    for variant in list(variants):
        variants |= IMPLIED_BY.get(variant, set())
    if not variants:
        return None
    ordered = sorted(variants, key=len, reverse=True)
    alternatives = "|".join(_escape(variant) for variant in ordered)
    return f"{_PREFIX}({alternatives}){_SUFFIX}"


def text_has_skill(text: str, skill: str) -> bool:
    pattern = skill_pattern(skill)
    if pattern is None or not text:
        return False
    return re.search(pattern, text.lower()) is not None
