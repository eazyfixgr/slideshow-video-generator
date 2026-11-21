"""Rich caption markup parsing and wrapping."""

import unittest

from slideshow.rich_text import (markup_ranges, parse_markup, size_factor,
                                 wrap_spans)
from slideshow.slide_design import _font


class RichTextTests(unittest.TestCase):
    def test_bold_accent_and_relative_size_spans(self):
        spans = parse_markup("Α **Β** ##Γ## %+2%Δ%%")
        rendered = [(span.text.strip(), span.bold, span.accent, span.size_steps)
                    for span in spans if span.text.strip()]
        self.assertEqual(rendered, [("Α", False, False, 0),
                                    ("Β", True, False, 0),
                                    ("Γ", False, True, 0),
                                    ("Δ", False, False, 2)])

    def test_nested_formatting_keeps_all_styles(self):
        spans = parse_markup("**##%+1%κείμενο%%##**")
        content = next(span for span in spans if span.text.strip())
        self.assertTrue(content.bold)
        self.assertTrue(content.accent)
        self.assertEqual(content.size_steps, 1)

    def test_markers_are_not_part_of_rendered_lines(self):
        def factory(family, size, bold):
            return _font(family, size, bold)

        lines = wrap_spans("Κανονικό **έντονο** ##χρυσό## %+1%μεγάλο%%",
                           _font("Calibri", 20), "Calibri", 500, factory)
        text = "".join(segment[0] for line in lines for segment in line)
        for marker in ("**", "##", "%%", "%+1%"):
            self.assertNotIn(marker, text)
        self.assertTrue(any(segment[2] for line in lines for segment in line))
        self.assertTrue(any(segment[1].size > 20 for line in lines
                            for segment in line))

    def test_size_factor_steps(self):
        self.assertAlmostEqual(size_factor(1), 1.1)
        self.assertAlmostEqual(size_factor(-2), 0.8)
        self.assertAlmostEqual(size_factor(99), 3.0)

    def test_marker_ranges_cover_all_markup_tokens(self):
        ranges = markup_ranges("**A** ##B## %+1%C%%")
        self.assertEqual(len(ranges), 6)


if __name__ == "__main__":
    unittest.main()
