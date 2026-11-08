import os
import unittest
from unittest.mock import patch
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

    def test_multiplexed_request_uses_only_profile_endpoint_and_model(self):
        import json, types
        values = {'DAILY_EDITION_API_KEY': 'profile_key',
                  'DAILY_EDITION_BASE_URL': 'https://profile.invalid/v1',
                  'DAILY_EDITION_MODEL': 'profile-model'}
        fake = types.ModuleType('agent.secret_scope')
        fake.get_secret = lambda name: values.get(name)
        fake.is_multiplex_active = lambda: True
        fake.serves_routed_profile = lambda: True
        pkg = types.ModuleType('agent')
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"choices":[{"message":{"content":"ok"}}]}'
        with patch.dict(sys.modules, {'agent': pkg, 'agent.secret_scope': fake}), \
             patch.dict(os.environ, {'DAILY_EDITION_API_KEY': 'other_key',
                                     'DAILY_EDITION_BASE_URL': 'https://other.invalid',
                                     'DAILY_EDITION_MODEL': 'other-model'}), \
             patch.object(model_client.urllib.request, 'urlopen', return_value=response) as send:
            self.assertEqual(model_client.chat([]), 'ok')
            request = send.call_args.args[0]
            self.assertEqual(request.full_url, 'https://profile.invalid/v1/chat/completions')
            self.assertEqual(request.get_header('Authorization'), 'Bearer profile_key')
            self.assertEqual(json.loads(request.data)['model'], 'profile-model')
            del values['DAILY_EDITION_BASE_URL']
            with self.assertRaises(RuntimeError):
                model_client.chat([])
            self.assertEqual(send.call_count, 1)

    def test_stale_config_cannot_send_scoped_key_to_another_endpoint(self):
        import types
        fake = types.ModuleType('agent.secret_scope')
        fake.get_secret = lambda name: {'DAILY_EDITION_API_KEY': 'profile_key',
                                        'DAILY_EDITION_BASE_URL': 'https://profile.invalid',
                                        'DAILY_EDITION_MODEL': 'profile-model'}.get(name)
        fake.serves_routed_profile = lambda: True
        with patch.dict(sys.modules, {'agent': types.ModuleType('agent'), 'agent.secret_scope': fake}), \
             patch.object(model_client.urllib.request, 'urlopen') as send:
            with self.assertRaises(RuntimeError):
                model_client.chat([], {'configured': True, 'url': 'https://other.invalid/v1/chat/completions', 'model': 'profile-model'})
            send.assert_not_called()

    def test_real_hermes_scope_isolation_when_available(self):
        try:
            from agent import secret_scope as scope
        except ImportError:
            self.skipTest('Hermes source not on Python path')
        values = {'DAILY_EDITION_API_KEY': 'profile_key',
                  'DAILY_EDITION_BASE_URL': 'https://profile.invalid',
                  'DAILY_EDITION_MODEL': 'profile-model'}
        with patch.dict(os.environ, {'DAILY_EDITION_API_KEY': 'other_key',
                                     'DAILY_EDITION_BASE_URL': 'https://other.invalid',
                                     'DAILY_EDITION_MODEL': 'other-model'}):
            multiplex = scope.set_multiplex_context(True)
            token = scope.set_secret_scope(values)
            try:
                state = model_client.settings()
                self.assertEqual(state['url'], 'https://profile.invalid/v1/chat/completions')
                self.assertEqual(state['model'], 'profile-model')
                del values['DAILY_EDITION_BASE_URL']
                self.assertFalse(model_client.settings()['configured'])
                del values['DAILY_EDITION_MODEL']
                self.assertEqual(model_client.settings()['model'], model_client.DEFAULT_MODEL)
            finally:
                scope.reset_secret_scope(token)
            try:
                self.assertFalse(model_client.settings()['configured'])
            finally:
                scope.reset_multiplex_context(multiplex)
            token = scope.set_secret_scope({'DAILY_EDITION_API_KEY': 'profile_key'},
                                           profile_home='/foreign-profile-for-scope-test')
            try:
                self.assertTrue(scope.serves_routed_profile())
                self.assertFalse(model_client.settings()['configured'])
                self.assertEqual(model_client.settings()['model'], model_client.DEFAULT_MODEL)
            finally:
                scope.reset_secret_scope(token)

    def test_a_scoped_secret_wins_over_the_environment(self):
        """Catalog rule 11: the profile secret scope is the route, not a bare env read."""
        import sys, types
        fake = types.ModuleType('agent.secret_scope')
        fake.get_secret = lambda name, default=None: {'DAILY_EDITION_API_KEY': 'scoped_key', 'DAILY_EDITION_BASE_URL': 'https://example.invalid/v1'}.get(name, default)
        fake.serves_routed_profile = lambda: True
        pkg = types.ModuleType('agent')
        pkg.secret_scope = fake
        with patch.dict(sys.modules, {'agent': pkg, 'agent.secret_scope': fake}):
            state = model_client.settings({'DAILY_EDITION_API_KEY': 'env_key',
                                           'DAILY_EDITION_BASE_URL': 'https://example.invalid/v1'})
        self.assertTrue(state['configured'])
        self.assertNotIn('env_key', str(state))

    def test_chat_sends_scoped_key_not_process_key_and_fails_closed(self):
        import sys, types
        fake = types.ModuleType('agent.secret_scope')
        fake.get_secret = lambda name: {'DAILY_EDITION_API_KEY': 'profile_scoped_secret', 'DAILY_EDITION_BASE_URL': 'https://example.invalid'}.get(name)
        fake.serves_routed_profile = lambda: True
        pkg = types.ModuleType('agent')
        pkg.secret_scope = fake
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"choices":[{"message":{"content":"ok"}}]}'
        with patch.dict(sys.modules, {'agent': pkg, 'agent.secret_scope': fake}), \
             patch.dict(os.environ, {'DAILY_EDITION_API_KEY': 'other_profile_secret', 'DAILY_EDITION_BASE_URL': 'https://example.invalid'}), \
             patch.object(model_client.urllib.request, 'urlopen', return_value=response) as send:
            self.assertEqual(model_client.chat([]), 'ok')
            self.assertEqual(send.call_args.args[0].get_header('Authorization'), 'Bearer profile_scoped_secret')
            fake.get_secret = lambda name: None
            with self.assertRaises(RuntimeError):
                model_client.chat([], {'configured': True, 'url': 'https://example.invalid/v1/chat/completions', 'model': 'm'})
            self.assertEqual(send.call_count, 1)

    def test_multiplexed_without_a_scoped_secret_fails_closed(self):
        """An env value must never be used for another profile's secret under multiplexing."""
        import sys, types
        fake = types.ModuleType('agent.secret_scope')
        fake.get_secret = lambda name, default=None: 'https://example.invalid/v1' if name == 'DAILY_EDITION_BASE_URL' else default
        fake.serves_routed_profile = lambda: True
        pkg = types.ModuleType('agent')
        pkg.secret_scope = fake
        with patch.dict(sys.modules, {'agent': pkg, 'agent.secret_scope': fake}):
            state = model_client.settings({'DAILY_EDITION_API_KEY': 'another_profiles_key',
                                           'DAILY_EDITION_BASE_URL': 'https://example.invalid/v1'})
        self.assertFalse(state['configured'])
        self.assertIn('DAILY_EDITION_API_KEY', state['error'])

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
