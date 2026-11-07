import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'dashboard'))

import model_client


class ModelClientTests(unittest.TestCase):
    def test_no_endpoint_ships_as_the_default(self):
        """A public default must not name a vendor: styling is off until one is configured."""
        self.assertEqual(model_client.DEFAULT_BASE, '')
        state = model_client.settings({'DAILY_EDITION_API_KEY': 'k'})
        self.assertFalse(state['configured'])
        self.assertIn('DAILY_EDITION_BASE_URL', state['error'])
        with self.assertRaises(ValueError):
            model_client.endpoint('')

    def test_a_configured_endpoint_sends_a_bearer(self):
        req = model_client.build_request(
            [{'role': 'user', 'content': 'hi'}],
            base_url='https://tokenharbor.ai/v1', model='claude-haiku-5.5', api_key='thk_test')
        self.assertEqual(req['url'], 'https://tokenharbor.ai/v1/chat/completions')
        self.assertEqual(req['headers']['Authorization'], 'Bearer thk_test')
        self.assertEqual(req['body']['model'], 'claude-haiku-5.5')
        self.assertEqual(req['body']['messages'], [{'role': 'user', 'content': 'hi'}])
        self.assertLessEqual(req['body']['max_tokens'], 128)

    def test_endpoint_normalisation_accepts_trailing_slash_and_bare_host(self):
        self.assertEqual(model_client.endpoint('https://tokenharbor.ai/v1/'), 'https://tokenharbor.ai/v1/chat/completions')
        self.assertEqual(model_client.endpoint('https://tokenharbor.ai'), 'https://tokenharbor.ai/v1/chat/completions')

    def test_plain_http_is_only_allowed_for_loopback(self):
        self.assertEqual(model_client.endpoint('http://127.0.0.1:11434/v1'), 'http://127.0.0.1:11434/v1/chat/completions')
        with self.assertRaises(ValueError):
            model_client.endpoint('http://example.com/v1')

    def test_missing_key_is_reported_not_guessed(self):
        settings = model_client.settings({'DAILY_EDITION_BASE_URL': 'https://tokenharbor.ai/v1', 'DAILY_EDITION_MODEL': 'x'})
        self.assertFalse(settings['configured'])
        self.assertIn('DAILY_EDITION_API_KEY', settings['error'])

    def test_key_can_come_from_a_named_variable(self):
        env = {'DAILY_EDITION_API_KEY': 'thk_supersecret_value', 'DAILY_EDITION_MODEL': 'm',
               'DAILY_EDITION_BASE_URL': 'https://example.invalid/v1'}
        settings = model_client.settings(env)
        self.assertTrue(settings['configured'])
        self.assertNotIn('thk_supersecret_value', str(settings))

    def test_errors_never_echo_the_key(self):
        with self.assertRaises(RuntimeError) as ctx:
            model_client.fail('401 Unauthorized', key='thk_secret')
        self.assertNotIn('thk_secret', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
