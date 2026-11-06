import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))

from personas import PERSONAS, build_prompt, sanitize_headline, check_rewrite, compose_persona


class PersonaTests(unittest.TestCase):
    def test_house_personas_exist_and_are_described(self):
        self.assertIn('librosmarcus', PERSONAS)
        self.assertIn('juno', PERSONAS)
        self.assertIn('quell', PERSONAS)
        for key, persona in PERSONAS.items():
            self.assertTrue(persona['name'], key)
            self.assertTrue(persona['voice'], key)

    def test_prompt_carries_the_source_and_the_no_invention_rules(self):
        messages = build_prompt('juno', {'title': 'Bridge reopens ahead of schedule', 'snippet': 'The crossing closed in March.'})
        system = messages[0]['content'].lower()
        self.assertIn('rewrite', system)
        self.assertIn('do not add', system)
        self.assertIn('numbers', system)
        user = messages[1]['content']
        self.assertIn('Bridge reopens ahead of schedule', user)
        self.assertIn('The crossing closed in March.', user)

    def test_unknown_persona_is_refused(self):
        with self.assertRaises(ValueError):
            build_prompt('nobody', {'title': 'x'})

    def test_sanitize_strips_wrapping_quotes_and_models_preamble(self):
        self.assertEqual(sanitize_headline('"Bridge reopens ahead of schedule"'), 'Bridge reopens ahead of schedule')
        self.assertEqual(sanitize_headline('Headline: Bridge reopens ahead of schedule\n'), 'Bridge reopens ahead of schedule')
        self.assertEqual(sanitize_headline('  —  Bridge   reopens  '), 'Bridge reopens')
        self.assertEqual(sanitize_headline(''), '')

    def test_rewrite_is_rejected_when_it_invents_a_number(self):
        original = {'title': 'Bridge reopens ahead of schedule'}
        ok, reason = check_rewrite(original, 'Bridge reopens 3 months early')
        self.assertFalse(ok)
        self.assertIn('number', reason)

    def test_rewrite_is_accepted_when_it_reuses_only_source_facts(self):
        original = {'title': 'Bridge reopens ahead of schedule', 'snippet': 'The crossing closed in March.'}
        ok, reason = check_rewrite(original, 'The bridge is open again, ahead of plan')
        self.assertTrue(ok, reason)

    def test_rewrite_is_rejected_when_it_is_far_too_long_or_empty(self):
        original = {'title': 'Bridge reopens'}
        self.assertFalse(check_rewrite(original, '')[0])
        long_text = 'Bridge reopens and ' + ('many words ' * 40)
        self.assertFalse(check_rewrite(original, long_text)[0])

    def test_compose_keeps_the_publishers_headline_on_failure(self):
        stories = [
            {'title': 'Bridge reopens ahead of schedule', 'snippet': 'Closed in March.'},
            {'title': 'Markets steady', 'snippet': ''},
        ]
        calls = []

        def fake_model(messages):
            calls.append(messages)
            if 'Markets' in messages[1]['content']:
                return 'Markets surge 12 percent'  # invents a number
            return 'The crossing opens again'

        result = compose_persona('quell', stories, fake_model)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result[0]['styled'], 'The crossing opens again')
        self.assertTrue(result[0]['ok'])
        self.assertEqual(result[1]['styled'], 'Markets steady')
        self.assertFalse(result[1]['ok'])
        self.assertEqual(result[1]['reason'], 'number')

    def test_compose_survives_a_model_that_raises(self):
        stories = [{'title': 'Bridge reopens', 'snippet': ''}]

        def boom(messages):
            raise RuntimeError('upstream 429')

        result = compose_persona('juno', stories, boom)
        self.assertEqual(result[0]['styled'], 'Bridge reopens')
        self.assertFalse(result[0]['ok'])
        self.assertIn('429', result[0]['reason'])

    def test_compose_is_bounded(self):
        stories = [{'title': 'Story %d' % i, 'snippet': ''} for i in range(30)]
        result = compose_persona('librosmarcus', stories, lambda m: 'Styled story', limit=5)
        self.assertEqual(len(result), 5)


if __name__ == '__main__':
    unittest.main()
