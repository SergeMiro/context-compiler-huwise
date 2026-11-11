"""Per-question card compression (measured offline, not enabled in configuration C): keep the card header,
key fields, fields whose name or label shares a word stem with the question, date fields when a year is asked,
and the notes/limits. The check is retention: every field the reference query needs must survive."""
import re

from ctx.compile import tokens

from .values import norm

STOP = set("combien de des du la le les un une en dans quel quelle est sont avec pour par au aux a y t il qui que "
           "the of in how many what which is are".split())


def stems(text):
    return {w[:5] for w in re.findall(r"[a-z0-9]+", norm(text).replace("_", " ")) if w not in STOP and len(w) > 2}


def compress(full_card, question):
    q = stems(question)
    year = bool(re.search(r"\b(19|20)\d\d\b", question))
    out, section = [], "head"
    for line in full_card.splitlines():
        if line.startswith("### "):
            section = line[4:].lower()
            out.append(line)
            continue
        if section != "fields" or not line.startswith("- "):
            out.append(line)
            continue
        name = line[2:].split(" · ")[0]
        if " · key" in line or (year and (" · date" in line or "year(" in line)) or stems(line) & q:
            out.append(line)
    text = "\n".join(out)
    return text, tokens(text)


def kept_fields(card):
    return {line[2:].split(" · ")[0] for line in card.splitlines() if line.startswith("- ") and " · " in line}
