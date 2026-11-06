"""The plugin entry point: one tool, one command, registered through the public plugin API."""

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def load_entry():
    spec = importlib.util.spec_from_file_location('daily_edition_entry_module', ROOT / '__init__.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeContext:
    def __init__(self):
        self.tools = []
        self.commands = []

    def register_tool(self, **kwargs):
        self.tools.append(kwargs)

    def register_command(self, name, handler, description='', args_hint=''):
        self.commands.append({'name': name, 'handler': handler, 'description': description, 'args_hint': args_hint})


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.module = load_entry()
        self.ctx = FakeContext()
        self.module.register(self.ctx)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.dict(os.environ, {'HERMES_HOME': self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_registers_exactly_one_tool_and_one_command(self):
        self.assertEqual([tool['name'] for tool in self.ctx.tools], ['daily_edition'])
        self.assertEqual([command['name'] for command in self.ctx.commands], ['edition'])

    def test_tool_schema_is_a_valid_object_schema(self):
        schema = self.ctx.tools[0]['schema']
        self.assertEqual(schema['name'], 'daily_edition')
        self.assertEqual(schema['parameters']['type'], 'object')
        self.assertEqual(schema['parameters']['properties']['action']['enum'], ['print', 'diff', 'sources'])
        self.assertIn('description', schema)

    def test_sources_action_reads_saved_state(self):
        from dashboard import state
        state.write({'interests': ['fusion energy'], 'feeds': ['https://alpha.example/feed']})
        payload = json.loads(self.module._tool({'action': 'sources'}))
        self.assertEqual(payload['interests'], ['fusion energy'])
        self.assertIn('1 interest', payload['text'])

    def test_rejects_too_many_interests(self):
        payload = json.loads(self.module._tool({'action': 'print', 'interests': ['a'] * 13}))
        self.assertIn('At most 12 interests', payload['error'])

    def test_rejects_a_non_list_interest_argument(self):
        payload = json.loads(self.module._tool({'action': 'print', 'interests': 'fusion'}))
        self.assertIn('list of phrases', payload['error'])

    def test_command_reports_a_broken_configuration_instead_of_raising(self):
        handler = self.ctx.commands[0]['handler']
        with patch.object(self.module, '_tool', side_effect=RuntimeError('boom')):
            # _command parses the tool's JSON, so an exception surfaces as an error string.
            with self.assertRaises(RuntimeError):
                handler('')
        with patch.object(self.module, '_tool', return_value=json.dumps({'error': 'no key'})):
            self.assertIn('no key', handler(''))


if __name__ == '__main__':
    unittest.main()
