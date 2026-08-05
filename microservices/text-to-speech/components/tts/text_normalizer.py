"""Text normalisation for character-vocabulary TTS models (SpeechT5).

SpeechT5 ships an 81-token character vocabulary that contains **no digits** and
almost no symbols::

    !"'(),-./:;?ABCDEFGHIJKLMNOPQRSTUVWXYZ[]abcdefghijklmnopqrstuvwxyz{}æéêœ̄—▁

Anything outside that set is mapped to ``<unk>`` and is silently *dropped* by
the decoder rather than spoken. So ``"We are open 8 AM to 11 PM."`` is
synthesised as ``"We are open  AM to  PM."`` — the listener hears "we are open
am to pm". The same applies to menu prices (``"Paneer Tikka Burger (159)"`` →
``"Paneer Tikka Burger ()"``) and to the ``₹`` sign.

This module expands numbers and unsupported symbols into words *before*
tokenisation, so the model receives only characters it can pronounce.

The integer-to-words conversion is implemented locally rather than pulling in
``num2words`` (LGPL) or ``inflect``: the required range is small, the output
needs to be deterministic for a voice kiosk, and the service should not grow a
dependency for ~60 lines of logic.

Only :func:`normalize_for_speech` is public.
"""

from __future__ import annotations

import re

__all__ = ["normalize_for_speech", "SPEECHT5_SUPPORTED_CHARS"]


# The single-character portion of the SpeechT5 tokenizer vocabulary. Kept here
# so the final scrub stage can drop anything the model cannot voice.
SPEECHT5_SUPPORTED_CHARS = frozenset(
    "!\"'(),-./:;?"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "[]{}"
    "æéêœ\u0304—"
    " "
)

_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
_TENS = (
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
)
_SCALES = ((1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand"))

_ORDINAL_ONES = {
    "one": "first", "two": "second", "three": "third", "five": "fifth",
    "eight": "eighth", "nine": "ninth", "twelve": "twelfth",
}

# Symbols outside the vocabulary that carry meaning and must be spoken.
_SYMBOLS = {
    "&": " and ",
    "+": " plus ",
    "=": " equals ",
    "@": " at ",
    "%": " percent ",
    "#": " number ",
    "*": " ",
    "_": " ",
    "|": " ",
    "~": " ",
    "^": " ",
    "\\": " ",
    "<": " less than ",
    ">": " greater than ",
    "°": " degrees ",
    "©": " copyright ",
    "®": " registered ",
    "™": " trademark ",
}

# Currency symbol → (major unit, minor unit).
_CURRENCIES = {
    "₹": ("rupees", "paise"),
    "$": ("dollars", "cents"),
    "€": ("euros", "cents"),
    "£": ("pounds", "pence"),
    "¥": ("yen", "sen"),
}


def _int_to_words(number: int) -> str:
    """Convert a non-negative integer to its spoken English form.

    Args:
        number: Integer to convert. Values above 999 billion are returned
            digit-by-digit as a safe fallback.

    Returns:
        The number written out in words, e.g. ``119`` → ``"one hundred
        nineteen"``.
    """
    if number < 0:
        return "minus " + _int_to_words(-number)
    if number < 20:
        return _ONES[number]
    if number < 100:
        tens, ones = divmod(number, 10)
        return _TENS[tens] + ("-" + _ONES[ones] if ones else "")
    if number < 1000:
        hundreds, rest = divmod(number, 100)
        out = _ONES[hundreds] + " hundred"
        return out + (" " + _int_to_words(rest) if rest else "")
    for scale_value, scale_name in _SCALES:
        if number >= scale_value:
            count, rest = divmod(number, scale_value)
            out = _int_to_words(count) + " " + scale_name
            return out + (" " + _int_to_words(rest) if rest else "")
    # Out of supported range — spell the digits so nothing is lost.
    return " ".join(_ONES[int(d)] for d in str(number))


def _int_to_ordinal_words(number: int) -> str:
    """Convert a non-negative integer to its spoken ordinal form (``1`` → ``first``)."""
    words = _int_to_words(number)
    head, _, tail = words.rpartition(" ")
    stem, sep, last = tail.rpartition("-")
    if last in _ORDINAL_ONES:
        last = _ORDINAL_ONES[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last = last + "th"
    tail = stem + sep + last
    return (head + " " + tail) if head else tail


def _spell_digits(digits: str) -> str:
    return " ".join(_ONES[int(d)] for d in digits)


def _money(match: re.Match) -> str:
    """Expand a currency amount, e.g. ``₹159.50`` → ``one hundred fifty-nine rupees fifty paise``."""
    groups = match.groupdict()
    symbol = groups.get("sym")
    if symbol is None:
        # Word-form prefix (Rs. / INR / USD) rather than a symbol.
        prefix = match.group(0).lstrip().upper()
        symbol = "$" if prefix.startswith("USD") else "₹"
    major_unit, minor_unit = _CURRENCIES.get(symbol, ("rupees", "paise"))
    whole = int(match.group("whole").replace(",", ""))
    fraction = groups.get("frac")

    out = f"{_int_to_words(whole)} {major_unit}"
    if fraction:
        minor = int(fraction.ljust(2, "0")[:2])
        if minor:
            out += f" {_int_to_words(minor)} {minor_unit}"
    return " " + out + " "


def _clock(match: re.Match) -> str:
    """Expand a clock time, e.g. ``8:30`` → ``eight thirty``, ``10:00`` → ``ten o'clock``."""
    hour = int(match.group("h"))
    minute = int(match.group("m"))
    if minute == 0:
        return f" {_int_to_words(hour)} o'clock "
    if minute < 10:
        return f" {_int_to_words(hour)} oh {_int_to_words(minute)} "
    return f" {_int_to_words(hour)} {_int_to_words(minute)} "


def _decimal(match: re.Match) -> str:
    whole = int(match.group("whole").replace(",", ""))
    return f" {_int_to_words(whole)} point {_spell_digits(match.group('frac'))} "


def _ordinal(match: re.Match) -> str:
    return " " + _int_to_ordinal_words(int(match.group("n"))) + " "


def _integer(match: re.Match) -> str:
    return " " + _int_to_words(int(match.group("n").replace(",", ""))) + " "


# Order matters: the most specific pattern must win. Currency before decimal,
# decimal before plain integer, otherwise "159.50" is read as two integers.
_CURRENCY_RE = re.compile(
    r"(?P<sym>[₹$€£¥])\s*(?P<whole>\d{1,3}(?:,\d{2,3})*|\d+)(?:\.(?P<frac>\d{1,2}))?"
)
_RUPEE_WORD_RE = re.compile(
    r"\b(?:Rs\.?|INR|USD)\s*(?P<whole>\d{1,3}(?:,\d{2,3})*|\d+)(?:\.(?P<frac>\d{1,2}))?",
    re.IGNORECASE,
)
_CLOCK_RE = re.compile(r"\b(?P<h>\d{1,2}):(?P<m>\d{2})\b")
_RANGE_RE = re.compile(r"(?<=\d)\s*[–—-]\s*(?=\d)")
_ORDINAL_RE = re.compile(r"\b(?P<n>\d+)(?:st|nd|rd|th)\b", re.IGNORECASE)
_DECIMAL_RE = re.compile(r"\b(?P<whole>\d{1,3}(?:,\d{3})*|\d+)\.(?P<frac>\d+)\b")
_INTEGER_RE = re.compile(r"\b(?P<n>\d{1,3}(?:,\d{3})*|\d+)\b")
_WHITESPACE_RE = re.compile(r"\s+")
# Expansions insert padding spaces to avoid gluing words together; these tidy
# the spacing back up around punctuation afterwards.
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?;:)\]}])")
_SPACE_AFTER_OPEN_RE = re.compile(r"([(\[{])\s+")


def normalize_for_speech(text: str, *, restrict_to_vocab: bool = True) -> str:
    """Expand digits and unsupported symbols so a character-vocabulary TTS can speak them.

    SpeechT5 drops every character outside its 81-token vocabulary, so numbers
    vanish from the audio entirely. This rewrites them as words.

    Args:
        text: Raw text to be synthesised.
        restrict_to_vocab: When True, characters still outside
            :data:`SPEECHT5_SUPPORTED_CHARS` are removed after expansion so
            nothing is silently swallowed by the tokenizer.

    Returns:
        Text containing only pronounceable characters.

    Example:
        >>> normalize_for_speech("We are open 8 AM to 11 PM.")
        'We are open eight AM to eleven PM.'
        >>> normalize_for_speech("Paneer Tikka Burger (₹159)")
        'Paneer Tikka Burger (one hundred fifty-nine rupees)'
    """
    if not text:
        return ""

    out = text
    # A numeric range ("8-11 PM") would otherwise be read as "eight minus
    # eleven"; say "to" instead.
    out = _RANGE_RE.sub(" to ", out)
    out = _CURRENCY_RE.sub(_money, out)
    out = _RUPEE_WORD_RE.sub(_money, out)
    out = _CLOCK_RE.sub(_clock, out)
    out = _ORDINAL_RE.sub(_ordinal, out)
    out = _DECIMAL_RE.sub(_decimal, out)
    out = _INTEGER_RE.sub(_integer, out)

    for symbol, replacement in _SYMBOLS.items():
        if symbol in out:
            out = out.replace(symbol, replacement)

    if restrict_to_vocab:
        out = "".join(ch if ch in SPEECHT5_SUPPORTED_CHARS else " " for ch in out)

    out = _WHITESPACE_RE.sub(" ", out)
    out = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", out)
    out = _SPACE_AFTER_OPEN_RE.sub(r"\1", out)
    return out.strip()
