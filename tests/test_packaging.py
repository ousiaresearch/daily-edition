"""Packaging contract: the manifest, the changelog and the entry points agree.

A release is only as good as its metadata. These checks are cheap and catch the mistakes that make a
plugin look careless from the outside: a version that disagrees between two manifests, a changelog
that stops a release behind, a declared tool nobody registers, a licence that is not a licence.
"""

import importlib.util
import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def load_manifest():
    return yaml.safe_load((ROOT / 'plugin.yaml').read_text('utf-8'))


def load_entry():
    spec = importlib.util.spec_from_file_location('daily_edition_packaging_entry', ROOT / '__init__.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.manifest = load_manifest()
        self.package = json.loads((ROOT / 'dashboard' / 'manifest.json').read_text('utf-8'))

    def test_name_is_a_plugin_slug(self):
        self.assertRegex(self.manifest['name'], r'^[a-z0-9][a-z0-9_-]{0,63}$')

    def test_name_matches_the_repository_it_ships_from(self):
        # The plugin name is the catalog key and the install directory, so it must match the repo it
        # is published from — but a reviewer who clones into /tmp/whatever must still get a green
        # suite, so this reads the remote rather than the checkout's directory name.
        import subprocess
        try:
            remote = subprocess.run(['git', 'remote', 'get-url', 'origin'], cwd=ROOT,
                                    capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            self.skipTest('not a git checkout')
        url = (remote.stdout or '').strip()
        if remote.returncode != 0 or not url:
            self.skipTest('no origin remote')
        base = url.rstrip('/').rsplit('/', 1)[-1].rsplit(':', 1)[-1]
        if base.endswith('.git'):
            base = base[:-4]
        self.assertEqual(self.manifest['name'], base)

    def test_versions_agree_between_the_two_manifests(self):
        self.assertEqual(str(self.manifest['version']), str(self.package['version']))

    def test_the_changelog_documents_this_version(self):
        text = (ROOT / 'CHANGELOG.md').read_text('utf-8')
        self.assertRegex(text, r'(?m)^## %s\b' % re.escape(str(self.manifest['version'])),
                         'add a CHANGELOG entry for the version being released')

    def test_entry_points_exist(self):
        for relative in ('__init__.py', 'dashboard/plugin_api.py', 'desktop/plugin.js'):
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_declared_tools_are_the_tools_registered(self):
        module = load_entry()
        declared = set(self.manifest.get('provides_tools') or [])
        self.assertEqual(declared, {module.SCHEMA['name']})

    def test_the_tool_schema_is_well_formed(self):
        module = load_entry()
        schema = module.SCHEMA
        self.assertEqual(schema['parameters']['type'], 'object')
        self.assertIn('description', schema)
        for name in schema['parameters']['properties']['action']['enum']:
            self.assertIsInstance(name, str)

    def test_host_requirements_are_declared(self):
        self.assertRegex(str(self.manifest.get('requires_hermes') or ''), r'^>=')

    def test_licence_is_present_and_is_mit(self):
        text = (ROOT / 'LICENSE').read_text('utf-8')
        self.assertIn('MIT License', text)
        self.assertIn('Permission is hereby granted', text)

    def test_readme_names_the_plugin_and_the_install_path(self):
        text = (ROOT / 'README.md').read_text('utf-8')
        self.assertIn('Daily Edition', text)
        self.assertIn('hermes plugins adopt', text)

    def test_no_python_bytecode_is_tracked_into_the_release(self):
        import subprocess
        try:
            listed = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True,
                                    text=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            self.skipTest('not a git checkout')
        if listed.returncode != 0:
            self.skipTest('not a git checkout')
        tracked = [line for line in listed.stdout.splitlines() if '__pycache__' in line]
        self.assertEqual(tracked, [], 'remove bytecode from the release commit')

    def test_the_print_spec_ships_with_the_plugin(self):
        self.assertTrue((ROOT / 'PRINT-PIPELINE.md').is_file())


if __name__ == '__main__':
    unittest.main()
