# SPDX-License-Identifier: GPL-3.0-or-later
"""The email tool is offered only when the person asks for an email to be written (D88; hands-on round 2)."""

import unittest

from cin_minai.daemon.intent import narrow, wants_email

ASKS_FOR_AN_EMAIL = [
    "Can you pull up my email and write a letter to Anthropic thanking them for Claude and OpenAI for ChatGPT?",
    "¿Puedes abrir mi correo y escribir una carta a Anthropic agradeciéndoles por Claude?",
    "Kannst du mein E-Mail-Programm öffnen und einen Brief an Anthropic schreiben?",
    "Write an email to my landlord telling him the kitchen sink is leaking.",
    "Escreva um e-mail para meu chefe dizendo como foi a reunião.",
    "Écris un courriel à mon propriétaire.",
    "大家さんにメールを書いて",
    "Send an email to my sister saying happy birthday",
]
DOES_NOT = [
    "Help me write a polite letter to my landlord: the heater has been broken for two weeks.",
    "How do I write an email with an attachment?",
    "Como escrevo um e-mail com anexo?",
    "¿Cómo escribo un correo con un archivo adjunto?",
    "Wie schreibe ich eine E-Mail?",
    "My email won't send",
    "Open my email",
    "メールの書き方を教えて",
]


def schema(*tools):
    return {"anyOf": [{"properties": {"tool": {"const": t}}} for t in tools]}


class EmailIntent(unittest.TestCase):
    def test_requests_for_an_email(self):
        for text in ASKS_FOR_AN_EMAIL:
            self.assertTrue(wants_email(text), text)

    def test_everything_else(self):
        for text in DOES_NOT:
            self.assertFalse(wants_email(text), text)

    def test_the_schema_offers_only_what_fits(self):
        s = schema("lookup_help", "open_app", "answer", "decline", "compose_email")
        tools = lambda sch: [o["properties"]["tool"]["const"] for o in sch["anyOf"]]
        self.assertEqual(tools(narrow(s, ASKS_FOR_AN_EMAIL[0])), ["decline", "compose_email"])
        self.assertNotIn("compose_email", tools(narrow(s, DOES_NOT[0])))
        self.assertIn("answer", tools(narrow(s, DOES_NOT[0])))
        plain = schema("lookup_help", "answer")
        self.assertIs(narrow(plain, ASKS_FOR_AN_EMAIL[0]), plain)  # prompts without the email tool: untouched


if __name__ == "__main__":
    unittest.main()
