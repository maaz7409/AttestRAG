"""Text normalisation helpers shared by the BM25 index and the offline embedder."""

import re

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-_.][a-z0-9]+)*")

# A compact English stop-word list. Removing these keeps BM25 focused on the
# terms that actually discriminate between chunks.
_STOPWORD_TEXT = """
    a about above after again against all am an and any are as at be because been before
    being below between both but by can could did do does doing down during each few for
    from further had has have having he her here hers herself him himself his how i if
    in into is it its itself just me more most my myself no nor not now of off on once
    only or other our ours ourselves out over own same she should so some such than that
    the their theirs them themselves then there these they this those through to too
    under until up very was we were what when where which while who whom why will with
    would you your yours yourself yourselves
"""
STOPWORDS = frozenset(_STOPWORD_TEXT.split())


def tokenize(text: str, *, keep_stopwords: bool = False) -> list[str]:
    tokens = _TOKEN_RE.findall(text.lower())
    if keep_stopwords:
        return tokens
    return [t for t in tokens if t not in STOPWORDS]


def normalize_whitespace(text: str) -> str:
    text = text.replace("\x00", "")
    # Re-join words hyphenated across line breaks: "retriev-\nal" -> "retrieval".
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
