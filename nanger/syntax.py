"""Very small regex based syntax highlighter."""
import re

from .term import A

KEYWORDS = re.compile(
    r"\b(?:if|elif|else|for|while|do|done|then|fi|case|esac|in|return|def|class|"
    r"import|from|as|with|try|except|finally|raise|lambda|yield|pass|break|continue|"
    r"and|or|not|is|None|True|False|function|const|let|var|new|this|null|true|false|"
    r"undefined|switch|default|catch|throw|async|await|public|private|protected|"
    r"static|void|int|char|float|double|long|bool|struct|enum|typedef|include|define|"
    r"export|local|echo|fn|pub|use|mut|impl|match|package|func|go|defer|type|self)\b")
STRINGS = re.compile(r'"(?:\\.|[^"\\])*"?|\'(?:\\.|[^\'\\])*\'?')
NUMBERS = re.compile(r"\b(?:0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b")
COMMENTS = {
    ".py": "#", ".sh": "#", ".bash": "#", ".zsh": "#", ".rb": "#", ".pl": "#",
    ".yml": "#", ".yaml": "#", ".toml": "#", ".conf": "#", ".cfg": "#", ".r": "#",
    ".ini": ";", ".c": "//", ".h": "//", ".cpp": "//", ".hpp": "//", ".cc": "//",
    ".java": "//", ".js": "//", ".ts": "//", ".jsx": "//", ".tsx": "//", ".go": "//",
    ".rs": "//", ".php": "//", ".cs": "//", ".kt": "//", ".swift": "//", ".css": None,
    ".json": None, ".lua": "--", ".sql": "--", ".hs": "--", ".vim": '"', ".tex": "%",
}
PLAIN = {".txt", ".md", ".log", ".csv", ".tsv", ".rst"}


def highlight(line, ctok):
    """Per-character attribute list for one line."""
    attrs = [0] * len(line)
    if len(line) > 3000:
        return attrs

    def paint(s, e, a):
        for i in range(s, e):
            attrs[i] = a

    for m in NUMBERS.finditer(line):
        paint(m.start(), m.end(), A["num"])
    for m in KEYWORDS.finditer(line):
        paint(m.start(), m.end(), A["kw"])
    spans = []
    for m in STRINGS.finditer(line):
        paint(m.start(), m.end(), A["str"])
        spans.append((m.start(), m.end()))
    if ctok:
        i = line.find(ctok)
        while i != -1 and any(s <= i < e for s, e in spans):
            i = line.find(ctok, i + 1)
        if i != -1:
            paint(i, len(line), A["com"])
    return attrs
