"""Rich caption markup: **bold**, ##accent## and %+1%relative size%%."""

import re
from dataclasses import dataclass

_SIZE_OPEN = re.compile(r"%([+-]\d+)%")
_SIZE_CLOSE = re.compile(r"%%")
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
    """Return source-offset spans with nested formatting applied.

    Markers are scanned as a stream instead of recursively closing at the
    first delimiter. This keeps nested size changes valid:
    ``%+3%outside %+1%inside%% outside%%``.
    """
    text = str(text or "")
    spans = []
    bold_state, accent_state = bool(bold), bool(accent)
    size_stack = [int(size_steps)]
    index = 0
    for match in _MARKERS.finditer(text):
        position = match.start()
        if position > index:
            spans.append(RichSpan(text[index:position], bold_state, accent_state,
                                  size_stack[-1], base + index, base + position))
        token = match.group(0)
        if token == "**":
            bold_state = not bold_state
        elif token == "##":
            accent_state = not accent_state
        elif token == "%%":
            if len(size_stack) > 1:
                size_stack.pop()
        else:
            try:
                size_stack.append(size_stack[-1] + int(token[1:-1]))
            except ValueError:
                pass
        index = match.end()
    if index < len(text):
        spans.append(RichSpan(text[index:], bold_state, accent_state,
                              size_stack[-1], base + index, base + len(text)))
    return _merge(spans)


def trim_markup_selection(text, start, end):
    """Move selection edges out of hidden formatting tokens.

    A visual line selection often ends after an outer ``%%`` (or includes a
    newline after it). Wrapping that range would put a new closing marker
    outside the existing one and corrupt the markup.
    """
    text = str(text or "")
    start = max(0, min(len(text), int(start)))
    end = max(start, min(len(text), int(end)))
    if start == end:
        return start, end

    def selected():
        return text[start:end]

    while start < end:
        chunk = selected()
        token = next((candidate for candidate in ("%[+-]\\d+%", "\\*\\*", "##")
                      if re.match(candidate, chunk)), None)
        if token is None:
            break
        marker = re.match(token, chunk).group(0)
        if token == "##":
            balanced = chunk.count("##") % 2 == 0
        elif token == "\\*\\*":
            balanced = chunk.count("**") % 2 == 0
        else:
            balanced = len(_SIZE_CLOSE.findall(chunk)) >= len(
                _SIZE_OPEN.findall(chunk))
        if balanced:
            break
        start += len(marker)

    while start < end:
        chunk = selected()
        trailing = chunk.rstrip()
        end -= len(chunk) - len(trailing)
        if end <= start:
            break
        chunk = selected()
        opens = len(_SIZE_OPEN.findall(chunk))
        closes = len(_SIZE_CLOSE.findall(chunk))
        if chunk.endswith("%%") and closes > opens:
            end -= 2
        elif chunk.endswith("**") and chunk.count("**") % 2:
            end -= 2
        elif chunk.endswith("##") and chunk.count("##") % 2:
            end -= 2
        else:
            break
    return start, end


def markup_ranges(text):
    return [(match.start(), match.end()) for match in _MARKERS.finditer(str(text or ""))]


def strip_markup(text):
    """Remove formatting tokens while keeping their text."""
    return _MARKERS.sub("", str(text or ""))


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
