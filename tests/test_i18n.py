"""Parity checks across the shipped UI languages.

With ten dictionaries in src/i18n.ts, the realistic failure is not a crash -
it is a key that quietly falls back to English on someone else's Deck, or a
{placeholder} that got translated along with the sentence and now renders
literally as "{n}". Neither is visible to us, so it is checked here.

The file is parsed as text rather than executed: there is no TypeScript
runtime in CI, and the dictionaries are plain literals by convention.
"""

import os
import re
import unittest

I18N = os.path.join(os.path.dirname(__file__), os.pardir, "src", "i18n.ts")

# `const de: Dict = { ... };` - non-greedy up to the first line that closes
# the literal at column 0.
DICT_RE = re.compile(r"^const (\w+): Dict = \{\n(.*?)^\};$", re.S | re.M)

# One entry: `key: "value"` or `key:\n    "value"`. Values are single
# double-quoted strings throughout, escapes included.
ENTRY_RE = re.compile(r"^  (\w+):\s*\n?\s*\"((?:[^\"\\]|\\.)*)\",$", re.M)

PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def read_source() -> str:
    with open(I18N, encoding="utf-8") as fh:
        return fh.read()


def parse_dicts(src: str) -> dict:
    """name -> {key: value}, preserving nothing else about the file."""
    out = {}
    for name, body in DICT_RE.findall(src):
        out[name] = dict(ENTRY_RE.findall(body))
    return out


def parse_entry_order(src: str, name: str) -> list:
    """Keys of one dictionary in file order, duplicates included."""
    for found, body in DICT_RE.findall(src):
        if found == name:
            return [k for k, _ in ENTRY_RE.findall(body)]
    raise AssertionError("no dictionary named %r" % name)


class ParseSanity(unittest.TestCase):
    """If the parser silently matched nothing, every other test would pass."""

    def setUp(self):
        self.src = read_source()
        self.dicts = parse_dicts(self.src)

    def test_finds_every_expected_language(self):
        expected = {
            "en", "ko", "de", "fr", "ru",
            "ptBr", "pl", "tr", "zhCn", "zhTw",
        }
        self.assertEqual(expected, set(self.dicts))

    def test_english_has_a_plausible_number_of_keys(self):
        # Guards against the entry regex matching only a handful of lines.
        self.assertGreater(len(self.dicts["en"]), 100)

    def test_every_dict_is_registered_in_langs(self):
        block = self.src.split("const LANGS", 1)[1].split("};", 1)[0]
        for name in self.dicts:
            self.assertRegex(
                block, r"\b%s\b" % re.escape(name),
                "%s is never reachable from LANGS" % name,
            )


class KeyParity(unittest.TestCase):
    def setUp(self):
        self.src = read_source()
        self.dicts = parse_dicts(self.src)
        self.en = self.dicts["en"]

    def test_no_dict_is_missing_a_key(self):
        for name, table in self.dicts.items():
            missing = sorted(set(self.en) - set(table))
            self.assertEqual([], missing, "%s is missing %s" % (name, missing))

    def test_no_dict_has_a_key_english_lacks(self):
        # A stray key is dead weight, and usually a typo of a real one.
        for name, table in self.dicts.items():
            extra = sorted(set(table) - set(self.en))
            self.assertEqual([], extra, "%s has unknown %s" % (name, extra))

    def test_no_duplicate_keys_within_a_dict(self):
        # A later duplicate silently wins in JS, so the first translation
        # would just vanish.
        for name in self.dicts:
            order = parse_entry_order(self.src, name)
            dupes = sorted({k for k in order if order.count(k) > 1})
            self.assertEqual([], dupes, "%s repeats %s" % (name, dupes))


class PlaceholderParity(unittest.TestCase):
    def setUp(self):
        self.dicts = parse_dicts(read_source())
        self.en = self.dicts["en"]

    def test_placeholders_match_english(self):
        for name, table in self.dicts.items():
            for key, want in self.en.items():
                expected = set(PLACEHOLDER_RE.findall(want))
                got = set(PLACEHOLDER_RE.findall(table.get(key, "")))
                self.assertEqual(
                    expected, got,
                    "%s[%r] has placeholders %s, expected %s"
                    % (name, key, sorted(got), sorted(expected)),
                )

    def test_no_stray_brace(self):
        # "{n items}" or a half-typed "{n" renders as literal text.
        for name, table in self.dicts.items():
            for key, value in table.items():
                stripped = PLACEHOLDER_RE.sub("", value)
                self.assertNotIn(
                    "{", stripped, "%s[%r] has an unclosed brace" % (name, key)
                )
                self.assertNotIn(
                    "}", stripped, "%s[%r] has a stray brace" % (name, key)
                )


class Untranslated(unittest.TestCase):
    """Catches a dictionary that was copied but never actually translated."""

    def setUp(self):
        self.dicts = parse_dicts(read_source())
        self.en = self.dicts["en"]

    def test_long_strings_are_not_verbatim_english(self):
        # Short labels legitimately match ("Status", "Version", "Discord"),
        # so only sentences are checked.
        for name, table in self.dicts.items():
            if name == "en":
                continue
            same = [
                k for k, v in table.items()
                if len(v) > 40 and v == self.en.get(k)
            ]
            self.assertEqual([], same, "%s left %s in English" % (name, same))


if __name__ == "__main__":
    unittest.main()
