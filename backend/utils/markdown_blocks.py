"""Markdown → structured blocks, for the document generator.

The deep-research report is markdown (see `aggregator.py` for the exact subset
the model is told to produce: one H1, H2/H3 sections, paragraphs, "- " bullets,
pipe tables, fenced code, **bold**, and $…$/$$…$$ LaTeX). The DOCX and PDF
writers cannot consume markdown directly, so this module turns it into a flat
list of block dicts with inline `Span`s — one neutral shape every writer in
`generator_agent.py` renders in its own way.

This is deliberately a small, targeted parser rather than a full CommonMark
implementation: it covers exactly the constructs the report generator emits,
and degrades to plain paragraphs for anything else.
"""

import re
from dataclasses import dataclass


@dataclass
class Span:
    """A run of inline text with its formatting. `link` is a URL or None."""
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    link: str | None = None


# ── LaTeX → readable plain text ───────────────────────────────────────────
# Reports contain real LaTeX ($\eta = P_{out}/P_{in}$). KaTeX renders it in the
# browser, but a .docx/.pdf/.txt has no such renderer, so we approximate it with
# Unicode instead of dumping raw backslash commands into the document.

_GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "chi": "χ",
    "psi": "ψ", "omega": "ω", "Gamma": "Γ", "Delta": "Δ", "Theta": "Θ",
    "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ",
    "Psi": "Ψ", "Omega": "Ω",
}

_SYMBOLS = {
    "times": "×", "cdot": "·", "div": "÷", "pm": "±", "mp": "∓",
    "leq": "≤", "le": "≤", "geq": "≥", "ge": "≥", "neq": "≠", "ne": "≠",
    "approx": "≈", "sim": "~", "propto": "∝", "equiv": "≡",
    "infty": "∞", "partial": "∂", "nabla": "∇", "sum": "Σ", "prod": "Π",
    "int": "∫", "sqrt": "√", "in": "∈", "notin": "∉", "subset": "⊂",
    "cup": "∪", "cap": "∩", "forall": "∀", "exists": "∃",
    "rightarrow": "→", "to": "→", "leftarrow": "←", "leftrightarrow": "↔",
    "Rightarrow": "⇒", "Leftarrow": "⇐", "ldots": "…", "dots": "…",
    "degree": "°", "circ": "°", "percent": "%",
}

_SUPERSCRIPT = str.maketrans("0123456789+-=()n i", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ ⁱ")
_SUBSCRIPT = str.maketrans("0123456789+-=()", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎")


def _script(body: str, table, fallback_prefix: str) -> str:
    """Render a super/subscript body with Unicode when every character has a
    mapping, else fall back to the readable ASCII form (x^(out))."""
    converted = body.translate(table)
    if converted != body or all(c in " " for c in body):
        # translate() leaves unmapped characters untouched, so a mixed result
        # would silently read wrong — require a full conversion.
        if all(ord(c) > 127 or c == " " for c in converted):
            return converted
    return f"{fallback_prefix}({body})" if len(body) > 1 else f"{fallback_prefix}{body}"


def latex_to_text(latex: str) -> str:
    """Best-effort LaTeX → Unicode plain text. Never raises; unknown commands
    are stripped of their backslash rather than dropped, so no information is
    lost even when the rendering is imperfect."""
    s = latex.strip()

    # \frac{a}{b} → (a)/(b), innermost first so nesting resolves.
    for _ in range(4):
        new = re.sub(
            r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}",
            lambda m: f"({m.group(1)})/({m.group(2)})",
            s,
        )
        if new == s:
            break
        s = new

    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√(\1)", s)
    s = re.sub(r"\\text(?:rm|bf|it)?\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\mathrm\s*\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"\\left|\\right", "", s)
    s = re.sub(r"\\[,;:!]|\\quad|\\qquad", " ", s)
    s = s.replace("\\\\", "  ")

    for name, char in {**_GREEK, **_SYMBOLS}.items():
        s = re.sub(rf"\\{name}(?![A-Za-z])", char, s)

    s = re.sub(r"\^\s*\{([^{}]*)\}", lambda m: _script(m.group(1), _SUPERSCRIPT, "^"), s)
    s = re.sub(r"_\s*\{([^{}]*)\}", lambda m: _script(m.group(1), _SUBSCRIPT, "_"), s)
    s = re.sub(r"\^(\w)", lambda m: _script(m.group(1), _SUPERSCRIPT, "^"), s)
    s = re.sub(r"_(\w)", lambda m: _script(m.group(1), _SUBSCRIPT, "_"), s)

    # Anything left over: drop the braces and the leading backslash so the
    # reader sees "beta" rather than "\beta{".
    s = re.sub(r"\\([A-Za-z]+)", r"\1", s)
    s = s.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


# ── Inline parsing ────────────────────────────────────────────────────────
# One alternation, scanned left to right, so `**bold**` inside a code span or a
# link label can't be mis-paired across boundaries.
_INLINE_RE = re.compile(
    r"(?P<code>`+)(?P<code_text>.+?)(?P=code)"
    r"|!\[(?P<img_alt>[^\]]*)\]\((?P<img_url>[^)]*)\)"
    r"|\[(?P<link_text>[^\]]*)\]\((?P<link_url>[^)\s]*)(?:\s+\"[^\"]*\")?\)"
    r"|(?P<bi>\*\*\*|___)(?P<bi_text>.+?)(?P=bi)"
    r"|(?P<b>\*\*|__)(?P<b_text>.+?)(?P=b)"
    r"|(?P<i>[*_])(?P<i_text>[^*_]+?)(?P=i)"
    r"|(?P<math>\$)(?P<math_text>[^$\n]+?)\$",
    re.DOTALL,
)


def parse_inline(text: str) -> list[Span]:
    """Split a line of markdown into formatted `Span`s."""
    spans: list[Span] = []
    pos = 0

    def push(chunk: str, **kw):
        if chunk:
            spans.append(Span(chunk, **kw))

    for m in _INLINE_RE.finditer(text):
        push(text[pos:m.start()])
        pos = m.end()

        if m.group("code") is not None:
            push(m.group("code_text"), code=True)
        elif m.group("img_url") is not None:
            push(m.group("img_alt") or "image", italic=True)
        elif m.group("link_url") is not None:
            label = m.group("link_text") or m.group("link_url")
            push(label, link=m.group("link_url") or None)
        elif m.group("bi") is not None:
            push(m.group("bi_text"), bold=True, italic=True)
        elif m.group("b") is not None:
            push(m.group("b_text"), bold=True)
        elif m.group("i") is not None:
            push(m.group("i_text"), italic=True)
        elif m.group("math") is not None:
            push(latex_to_text(m.group("math_text")), italic=True)

    push(text[pos:])
    return spans or [Span("")]


def spans_to_text(spans: list[Span]) -> str:
    """Flatten spans back to plain text (used by the .txt writer)."""
    return "".join(s.text for s in spans)


# ── Block parsing ─────────────────────────────────────────────────────────
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)\s*([\w+-]*)\s*$")
_RULE_RE = re.compile(r"^\s*([-*_])(?:\s*\1){2,}\s*$")
_ULIST_RE = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_OLIST_RE = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?\s*$")


def _split_row(line: str) -> list[str]:
    """Split a pipe-table row, ignoring the optional leading/trailing pipes and
    honouring `\\|` escapes inside cells."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells = re.split(r"(?<!\\)\|", line)
    return [c.replace("\\|", "|").strip() for c in cells]


def parse_markdown(md: str) -> list[dict]:
    """Parse a markdown document into a flat list of block dicts.

    Block shapes:
      {"type": "heading",   "level": 1-6, "spans": [...]}
      {"type": "paragraph", "spans": [...]}
      {"type": "list_item", "ordered": bool, "level": int, "number": int|None,
                            "spans": [...]}
      {"type": "code",      "language": str, "text": str}
      {"type": "table",     "header": [[Span]], "rows": [[[Span]]]}
      {"type": "quote",     "spans": [...]}
      {"type": "math",      "text": str}
      {"type": "rule"}
    """
    lines = (md or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[dict] = []
    para: list[str] = []
    i = 0

    def flush_para():
        if para:
            text = " ".join(l.strip() for l in para).strip()
            if text:
                blocks.append({"type": "paragraph", "spans": parse_inline(text)})
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            flush_para()
            i += 1
            continue

        fence = _FENCE_RE.match(line)
        if fence:
            flush_para()
            marker, lang = fence.group(1), fence.group(2)
            i += 1
            body: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith(marker):
                body.append(lines[i])
                i += 1
            i += 1  # closing fence (or EOF)
            blocks.append({"type": "code", "language": lang, "text": "\n".join(body)})
            continue

        # Display math: $$…$$ on its own line, or opened here and closed later.
        if stripped.startswith("$$"):
            flush_para()
            inner = stripped[2:]
            if inner.endswith("$$") and len(stripped) > 4:
                blocks.append({"type": "math", "text": latex_to_text(inner[:-2])})
                i += 1
                continue
            body = [inner] if inner else []
            i += 1
            while i < len(lines) and "$$" not in lines[i]:
                body.append(lines[i])
                i += 1
            if i < len(lines):
                body.append(lines[i].split("$$")[0])
                i += 1
            blocks.append({"type": "math", "text": latex_to_text(" ".join(body))})
            continue

        if _RULE_RE.match(line):
            flush_para()
            blocks.append({"type": "rule"})
            i += 1
            continue

        heading = _HEADING_RE.match(stripped)
        if heading:
            flush_para()
            blocks.append({
                "type": "heading",
                "level": len(heading.group(1)),
                "spans": parse_inline(heading.group(2).strip().rstrip("#").strip()),
            })
            i += 1
            continue

        # Table: a header row followed by a |---|---| separator.
        if "|" in stripped and i + 1 < len(lines) and _TABLE_SEP_RE.match(lines[i + 1]):
            flush_para()
            header = [parse_inline(c) for c in _split_row(stripped)]
            i += 2
            rows = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                cells = [parse_inline(c) for c in _split_row(lines[i])]
                # Pad/trim to the header width so writers can assume a rectangle.
                cells = (cells + [[Span("")]] * len(header))[:len(header)]
                rows.append(cells)
                i += 1
            blocks.append({"type": "table", "header": header, "rows": rows})
            continue

        quote = _QUOTE_RE.match(line)
        if quote:
            flush_para()
            parts = [quote.group(1)]
            i += 1
            while i < len(lines) and _QUOTE_RE.match(lines[i]):
                parts.append(_QUOTE_RE.match(lines[i]).group(1))
                i += 1
            blocks.append({"type": "quote", "spans": parse_inline(" ".join(parts).strip())})
            continue

        olist = _OLIST_RE.match(line)
        ulist = None if olist else _ULIST_RE.match(line)
        if olist or ulist:
            flush_para()
            indent = len((olist or ulist).group(1).replace("\t", "  "))
            blocks.append({
                "type": "list_item",
                "ordered": bool(olist),
                "level": min(indent // 2, 3),
                "number": int(olist.group(2)) if olist else None,
                "spans": parse_inline((olist.group(3) if olist else ulist.group(2)).strip()),
            })
            i += 1
            continue

        para.append(line)
        i += 1

    flush_para()
    return blocks
