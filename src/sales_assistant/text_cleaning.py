"""Clean text read from PDFs, keeping each printed line (and so each table row) on its own line."""

import re

# PDFium writes this where a hyphen fell at a line break: "air-to\x02pulp" is "air-to-pulp".
LINE_BREAK_HYPHEN = "\x02"
# Every other control character except tab and line feed; icon glyphs come out as these.
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_text(text: str) -> str:
    r"""Return `text` with plain line breaks, no control characters, single spaces, no empty lines.

    Example: "Chambers   8\t10\r\n\x1a\r\nair-to\x02pulp" -> "Chambers 8 10\nair-to-pulp".
    """
    text = text.replace("\r\n", "\n").replace(LINE_BREAK_HYPHEN, "-")
    text = CONTROL_CHARACTERS.sub("", text)
    lines = (" ".join(line.split()) for line in text.split("\n"))
    return "\n".join(line for line in lines if line)
