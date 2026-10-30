"""No screen shows a word from the old vocabulary.

Everyone using the app is assumed to read like a twelve-year-old, so the
words on the left of ``glossary.PLAIN_WORDS`` ("waiver", "evidence",
"publication", "commit"...) never reach a page. This reads the text a
template actually puts in front of someone -- its words, and the
placeholder, label, title and button values it fills in -- leaving out
comments, tags and template code, and checks every flash message the
blueprints can show. A failure names the file, the line and the plain word
to use instead.
"""

import os
import re
import unittest
from pathlib import Path

os.environ["TESTING"] = "true"

from app.services.glossary import PLAIN_WORDS

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "app" / "templates"
BLUEPRINTS = ROOT / "app" / "blueprints"

_BANNED = re.compile(r"\b(" + "|".join(sorted((re.escape(word) for word in PLAIN_WORDS), key=len, reverse=True)) + r")(?:s|es)?\b", re.I)
_ATTRIBUTES = re.compile(r'(?:placeholder|aria-label|title|alt|value|data-confirm-submit)="([^"]*)"')


def visible_text(source):
    """The words a template can put on screen, one fragment per line."""
    source = re.sub(r"\{#.*?#\}", " ", source, flags=re.S)
    source = re.sub(r"\{%-?\s*block auth_stage_class\s*-?%\}.*?\{%-?\s*endblock\s*-?%\}", " ", source, flags=re.S)
    source = re.sub(r"<(script|style)\b.*?</\1>", " ", source, flags=re.S)
    source = re.sub(r"<!--.*?-->", " ", source, flags=re.S)
    attributes = [re.sub(r"\{\{.*?\}\}", " ", value) for value in _ATTRIBUTES.findall(source)]
    source = re.sub(r"\{%.*?%\}", " ", source, flags=re.S)
    source = re.sub(r"\{\{.*?\}\}", " ", source, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", source)
    return [line.strip() for line in text.splitlines() + attributes if line.strip()]


def flash_messages(source):
    return [match.group(2) for match in re.finditer(r"flash\(\s*f?(['\"])(.*?)\1", source)]


class PlainLanguageTestCase(unittest.TestCase):
    def _check(self, where, fragments):
        found = []
        for fragment in fragments:
            for match in _BANNED.finditer(fragment):
                word = match.group(1).lower()
                found.append(f"{where}: “{fragment[:90]}” — say “{PLAIN_WORDS[word]}” instead of “{word}”")
        return found

    def test_no_template_shows_an_old_word(self):
        found = []
        for path in sorted(TEMPLATES.rglob("*.html")):
            found += self._check(path.relative_to(ROOT), visible_text(path.read_text(encoding="utf-8")))
        self.assertEqual(found, [], "\n" + "\n".join(found))

    def test_no_flash_message_uses_an_old_word(self):
        found = []
        for path in sorted(BLUEPRINTS.glob("*.py")):
            found += self._check(path.relative_to(ROOT), flash_messages(path.read_text(encoding="utf-8")))
        self.assertEqual(found, [], "\n" + "\n".join(found))

    def test_every_recorded_action_has_plain_words(self):
        # "Who changed what" reads each action as a sentence; one with no
        # entry would show its raw identifier ("checklist instantiate").
        from app.services.glossary import AUDIT_ACTIONS

        source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "app").rglob("*.py"))
        actions = set(re.findall(r'record_audit\(\s*"([a-z_]+\.[a-z_.]+)"', source))
        self.assertTrue(actions)
        self.assertEqual(sorted(actions - set(AUDIT_ACTIONS)), [])

    def test_the_checker_sees_words_but_not_code(self):
        fragments = visible_text('{# evidence #}<p class="stage">Add the <b>evidence</b></p>{{ waiver }}<input placeholder="Commit it">')
        self.assertEqual(self._check("x", ["Add the"]), [])
        self.assertEqual(len(self._check("x", fragments)), 2)


if __name__ == "__main__":
    unittest.main()
