"""Rich caption markup: **bold**, ##accent## and %+1%relative size%%."""

import re
from dataclasses import dataclass

_SIZE_OPEN = re.compile(r"%([+-]\d+)%")
_MARKERS = re.compile(r"\*\*|##|%%|%[+-]\d+%")


@dataclass
class RichSpan:
    text: str
    bold: bool = False
    accent: bool = False
    size_steps: int = 0
    start: int = 0
    end: int = 0


def _merge(spans):
    out = []
    for span in spans:
        if not span.text:
            continue
        if (out and out[-1].bold == span.bold and out[-1].accent == span.accent and
                out[-1].size_steps == span.size_steps and
                out[-1].end == span.start):
            out[-1].text += span.text
            out[-1].end = span.end
        else:
            out.append(span)
    return out


def parse_markup(text, bold=False, accent=False, size_steps=0, base=0):
    """Return source-offset spans with nested formatting applied."""
    text = str(text or "")
    spans = []
    index = 0
    while index < len(text):
        bold_at = text.find("**", index)
        accent_at = text.find("##", index)
        size_match = _SIZE_OPEN.search(text, index)
        starts = []
        if bold_at >= 0:
            starts.append((bold_at, "bold"))
        if accent_at >= 0:
            starts.append((accent_at, "accent"))
        if size_match is not None:
            starts.append((size_match.start(), "size"))
        if not starts:
            spans.append(RichSpan(text[index:], bold, accent, size_steps,
                                  base + index, base + len(text)))
            break
        pos, kind = min(starts, key=lambda item: item[0])
        if pos > index:
            spans.append(RichSpan(text[index:pos], bold, accent, size_steps,
                                  base + index, base + pos))
        if kind == "bold":
            close = text.find("**", pos + 2)
            if close < 0:
                spans.append(RichSpan("**", bold, accent, size_steps,
                                      base + pos, base + pos + 2))
                index = pos + 2
                continue
            spans.extend(parse_markup(text[pos + 2:close], True, accent,
                                      size_steps, base + pos + 2))
            index = close + 2
        elif kind == "accent":
            close = text.find("##", pos + 2)
            if close < 0:
                spans.append(RichSpan("##", bold, accent, size_steps,
                                      base + pos, base + pos + 2))
                index = pos + 2
                continue
            spans.extend(parse_markup(text[pos + 2:close], bold, True,
                                      size_steps, base + pos + 2))
            index = close + 2
        else:
            close = text.find("%%", size_match.end())
            if close < 0:
                spans.append(RichSpan(size_match.group(0), bold, accent,
                                      size_steps, base + pos, base + size_match.end()))
                index = size_match.end()
                continue
            try:
                steps = int(size_match.group(1))
            except ValueError:
                steps = 0
            spans.extend(parse_markup(text[size_match.end():close], bold, accent,
                                      size_steps + steps, base + size_match.end()))
            index = close + 2
    return _merge(spans)


def markup_ranges(text):
    return [(match.start(), match.end()) for match in _MARKERS.finditer(str(text or ""))]


def size_factor(steps):
    try:
        steps = int(steps)
    except (TypeError, ValueError):
        steps = 0
    return max(0.3, min(3.0, 1.0 + steps * 0.1))


def font_for_span(span, base_font, family, font_factory):
    size = max(6, round(getattr(base_font, "size", 12) * size_factor(span.size_steps)))
    return font_factory(family, size, span.bold)


def wrap_spans(text, base_font, family, max_width, font_factory):
    """Return wrapped lines as [(text, font, accent), ...]."""
    lines, line, line_width = [], [], 0.0

    def flush(force_empty=False):
        nonlocal line, line_width
        if line or force_empty:
            lines.append(line)
        line, line_width = [], 0.0

    spans = parse_markup(text)
    if not spans:
        spans = [RichSpan("", start=0, end=0)]
    for span in spans:
        chosen_font = font_for_span(span, base_font, family, font_factory)
        paragraphs = span.text.split("\n")
        for paragraph_index, paragraph in enumerate(paragraphs):
            if paragraph_index:
                flush(force_empty=True)
            for word in paragraph.split():
                pieces = _split_word(word, chosen_font, max_width)
                for piece_index, piece in enumerate(pieces):
                    token = piece + (" " if piece_index == len(pieces) - 1 else "")
                    piece_width = _width(chosen_font, token)
                    if line and line_width + piece_width > max_width:
                        flush()
                    line.append((token, chosen_font, span.accent))
                    line_width += piece_width
    flush()
    return lines


def _split_word(word, font, max_width):
    """Break one long word into chunks that fit max_width."""
    if _width(font, word) <= max_width:
        return [word]
    pieces, piece, piece_width = [], "", 0.0
    for char in word:
        char_width = _width(font, char)
        if piece and piece_width + char_width > max_width:
            pieces.append(piece)
            piece, piece_width = char, char_width
        else:
            piece += char
            piece_width += char_width
    if piece:
        pieces.append(piece)
    return pieces or [word]


def _width(font, text):
    try:
        return font.getlength(text)
    except Exception:
        try:
            return font.getbbox(text)[2]
        except Exception:
            return len(text) * max(1, getattr(font, "size", 12) // 2)


def line_width(line, fallback_font=None):
    if isinstance(line, str):
        return _width(fallback_font, line) if fallback_font is not None else 0
    total = 0.0
    for segment in line:
        if len(segment) == 2:
            text, font = segment
        else:
            text, font, _accent = segment
        total += _width(font, text)
    return total


def line_height(line, fallback):
    if isinstance(line, str) or not line:
        return fallback
    sizes = [getattr(segment[1], "size", 0) for segment in line]
    return max(int(fallback), int(max(sizes or [0]) * 1.2))
