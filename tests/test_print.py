import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import dashboard.print as press

EDITION = {
    'number': 4,
    'dateLabel': 'Thursday, 5 November 2026',
    'storyCount': 2,
    'sourceCount': 2,
    'crossPosted': 1,
    'withheld': 0,
    'standfirst': '2 new since No. 3',
    'lead': {'title': 'Council <b>approves</b> transit plan', 'snippet': 'Two corridors & a spur.',
             'publishers': ['Alpha']},
    'sections': [{'source': 'Beta', 'stories': [
        {'title': '<script>alert(1)</script>Harbour fees rise', 'snippet': 'Port authority confirmed.',
         'publishers': ['Beta']}]}],
    'stories': [{}, {}],
}


class Completed:
    def __init__(self, stdout='', stderr='', returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


class RenderTests(unittest.TestCase):
    def test_escapes_everything_from_the_feeds(self):
        page = press.render_html(EDITION)
        self.assertNotIn('<script>alert(1)</script>', page)
        self.assertNotIn('<b>approves</b>', page)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', page)
        self.assertIn('Two corridors &amp; a spur.', page)

    def test_columns_flow_with_protected_headings(self):
        page = press.render_html(EDITION)
        self.assertIn('.story { break-inside: auto', page)
        self.assertIn('.story h3 { break-inside: avoid', page)
        self.assertIn('orphans: 3', page)
        self.assertIn('column-fill: balance', page)

    def test_sets_a_broadsheet_not_a_link_list(self):
        page = press.render_html(EDITION)
        self.assertIn('class="nameplate"', page)
        self.assertIn('column-count: 3', page)
        self.assertIn('class="lead"', page)
        self.assertIn('Compiled by Hermes', page)
        self.assertIn('page 1 of 1', page)

    def test_never_prints_a_url(self):
        edition = dict(EDITION, sections=[{'source': 'Beta', 'stories': [{
            'title': 'A story', 'publishers': ['Beta'],
            'snippet': 'Article URL: https://example.com/a Comments URL: https://example.com/b',
        }]}])
        page = press.render_html(edition, source_urls=['https://alpha.example/feed'])
        self.assertNotIn('http', page)
        self.assertIn('alpha.example', page)

    def test_a_link_dump_becomes_a_brief(self):
        edition = dict(EDITION, sections=[{'source': 'Beta', 'stories': [{
            'title': 'Short item', 'publishers': ['Beta'],
            'snippet': 'Article URL: https://example.com/a Points: 12 # Comments: 3',
        }]}])
        page = press.render_html(edition)
        self.assertIn('In brief', page)
        self.assertIn('Short item', page)
        self.assertNotIn('Points: 12', page)

    def test_clean_snippet_drops_urls_labels_and_votes(self):
        self.assertEqual(
            press.clean_snippet('Article URL: https://x.example/a Comments URL: https://y.example/b Points: 12 # Comments: 3'),
            '')
        self.assertEqual(
            press.clean_snippet('  The council   approved the plan on Tuesday.  '),
            'The council approved the plan on Tuesday.')
        self.assertIn('…', press.clean_snippet('A ' * 400))

    def test_domain_of_strips_www_and_path(self):
        self.assertEqual(press.domain_of('https://www.example.com/a/b?c=1'), 'example.com')
        self.assertEqual(press.domain_of('not a url'), '')

    def test_has_masthead_date_and_counts(self):
        page = press.render_html(EDITION)
        self.assertIn('Daily Edition', page)
        self.assertIn('No. 4', page)
        self.assertIn('Thursday, 5 November 2026', page)
        self.assertIn('2 stories · 2 sources · 1 cross-posted', page)
        self.assertIn('@page', page)

    def test_an_empty_edition_still_renders_honestly(self):
        page = press.render_html({'number': 1, 'dateLabel': 'Thursday, 5 November 2026'})
        self.assertIn('No stories were printed', page)
        self.assertIn('Daily Edition', page)

    def test_text_rendition_strips_markup(self):
        text = press.to_text(press.render_html(EDITION))
        for tag in ('<div', '<h1', '<section', '<article', '<style'):
            self.assertNotIn(tag, text)
        self.assertIn('Council', text)
        self.assertIn('Harbour fees rise', text)
        # A headline that looked like markup prints as text, not as a tag in the page.
        self.assertNotIn('<b>approves</b>', press.render_html(EDITION))

    def test_page_count_reads_page_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = pathlib.Path(tmp) / 'x.pdf'
            pdf.write_bytes(b'%PDF-1.4 /Type /Pages 1 0 R /Type /Page /Type /Page')
            self.assertEqual(press.page_count(str(pdf)), 2)
            pdf.write_bytes(b'%PDF-1.4 /Type /Pages')
            self.assertEqual(press.page_count(str(pdf)), 0)


class SubmitTests(unittest.TestCase):
    def setUp(self):
        # Tests must not depend on whether the host has CUPS installed.
        patcher = patch.object(press.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name)
        patcher.start()
        self.addCleanup(patcher.stop)
    def test_refuses_a_printer_name_that_could_be_shell_input(self):
        job, error = press.submit('/tmp/x.pdf', 'office; rm -rf /')
        self.assertEqual(job, '')
        self.assertIn('Invalid printer name', error)

    def test_the_browser_is_told_not_to_reach_the_network(self):
        """Both browser invocations must carry the offline flags, not just the print one."""
        captured = []
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)

        def fake_run(argv, **kwargs):
            captured.append(argv)
            if '--dump-dom' in argv:
                return Completed('', '', 0)
            pathlib.Path(argv[[i for i, a in enumerate(argv) if a.startswith('--print-to-pdf=')][0]]
                         .split('=', 1)[1]).write_bytes(b'%PDF-1.4')
            return Completed('', '', 0)

        with patch.object(press, 'chrome_path', return_value='/usr/bin/chrome'), \
             patch.object(press, 'BROWSER_FLAGS', press.BROWSER_FLAGS), \
             patch.object(press.subprocess, 'run', side_effect=fake_run):
            press.render_pdf('<p>x</p>', str(pathlib.Path(tmp) / 'x.pdf'))
            press.measure_layout(str(pathlib.Path(tmp) / 'x.pdf.html'))

        self.assertGreaterEqual(len(captured), 2)
        for argv in captured:
            for flag in ('--disable-background-networking', '--disable-component-update',
                         '--disable-sync', '--no-pings'):
                self.assertIn(flag, argv)

    def test_refuses_when_cups_has_no_destination(self):
        with patch.object(press, 'available_printers', return_value=[]):
            job, error = press.submit('/tmp/x.pdf', '')
        self.assertEqual(job, '')
        self.assertIn('No printer is configured', error)

    def test_without_cups_it_says_so_plainly(self):
        with patch.object(press.shutil, 'which', return_value=None):
            job, error = press.submit('/tmp/x.pdf', '')
        self.assertEqual(job, '')
        self.assertIn('CUPS lp is not installed', error)

    def test_parses_the_job_id(self):
        with patch.object(press, 'available_printers', return_value=['Office']), \
             patch.object(press.subprocess, 'run', return_value=Completed('request id is Office-42 (1 file(s))')):
            job, error = press.submit('/tmp/x.pdf', 'Office')
        self.assertEqual(job, 'Office-42')
        self.assertEqual(error, '')

    def test_lp_receives_an_argument_list_not_a_shell_string(self):
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs))
            return Completed('request id is Office-7 (1 file(s))')

        with patch.object(press, 'available_printers', return_value=['Office']), \
             patch.object(press.subprocess, 'run', side_effect=fake_run):
            press.submit('/tmp/x.pdf', 'Office')
        command, kwargs = calls[0]
        self.assertIsInstance(command, list)
        self.assertEqual(command[1:3], ['-d', 'Office'])
        self.assertNotIn('shell', kwargs)

    def test_parses_printers(self):
        with patch.object(press.subprocess, 'run',
                          return_value=Completed('printer Office is idle.  enabled since Thu\nprinter Lab disabled since Thu')):
            self.assertEqual(press.available_printers(), ['Office', 'Lab'])


class PrintEditionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.dict(os.environ, {'HERMES_HOME': self.tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        # CUPS presence is a property of the host, not of the pipeline's logic.
        which = patch.object(press.shutil, 'which', side_effect=lambda name: '/usr/bin/' + name)
        which.start()
        self.addCleanup(which.stop)

    def fake_pdf(self, pages):
        def render(html_text, out_path, html_path=''):
            target = html_path or (str(out_path) + '.html')
            pathlib.Path(target).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(target).write_text(html_text, encoding='utf-8')
            pathlib.Path(out_path).write_bytes(b'%PDF-1.4 ' + b'/Type /Page ' * pages)
            return str(out_path), ''
        return render

    def test_dry_run_writes_artifacts_and_never_calls_lp(self):
        with patch.object(press, 'render_pdf', side_effect=self.fake_pdf(1)), \
             patch.object(press, 'measure_layout', return_value={'fill': 0.95, 'heights': {}}), \
             patch.object(press, 'submit') as submit_mock:
            result = press.print_edition(EDITION, dry_run=True)
        submit_mock.assert_not_called()
        self.assertTrue(result['ok'])
        self.assertEqual(result['pages'], 1)
        self.assertTrue(pathlib.Path(result['html']).exists())
        self.assertTrue(pathlib.Path(result['text']).exists())

    def test_fit_drops_tail_stories_until_one_page(self):
        edition = dict(EDITION, stories=[{'t': 1}, {'t': 2}, {'t': 3}], storyCount=3)
        seen = {'n': 0}

        def pages(path):
            seen['n'] += 1
            return 2 if seen['n'] == 1 else 1

        with patch.object(press, 'render_pdf', side_effect=self.fake_pdf(1)), \
             patch.object(press, 'measure_layout', return_value={'fill': 0.95, 'heights': {}}), \
             patch.object(press, 'page_count', side_effect=pages):
            result = press.print_edition(edition, dry_run=True)
        self.assertEqual(result['pages'], 1)
        self.assertEqual(result['stories'], 2)
        self.assertEqual(len(result['attempts']), 2)

    def test_an_underfilled_sheet_gets_larger_type(self):
        fills = iter([0.45, 0.95])

        def fill(path):
            return {'fill': next(fills), 'heights': {}}

        with patch.object(press, 'render_pdf', side_effect=self.fake_pdf(1)), \
             patch.object(press, 'measure_layout', side_effect=fill):
            result = press.print_edition(EDITION, dry_run=True)
        self.assertEqual(len(result['attempts']), 2)
        self.assertGreater(result['attempts'][-1]['scale'], 1.0)
        page = pathlib.Path(result['html']).read_text()
        self.assertIn('zoom: 1.15', page)

    def test_an_overflowing_sheet_keeps_the_largest_fitting_type(self):
        pages = iter([1, 2, 1, 1])
        fills = iter([0.50, 0.95])

        with patch.object(press, 'render_pdf', side_effect=self.fake_pdf(1)), \
             patch.object(press, 'page_count', side_effect=lambda p: next(pages)), \
             patch.object(press, 'measure_layout', side_effect=lambda p: {'fill': next(fills), 'heights': {}}):
            result = press.print_edition(dict(EDITION, stories=[1, 2, 3], storyCount=3), dry_run=True)
        # Grew to fill the sheet, overflowed, and went back to the last attempt that fitted:
        # no story dropped, and the submitted PDF is the one that was measured at 1 page.
        self.assertEqual(result['stories'], 3)
        self.assertEqual(result['pages'], 1)
        self.assertEqual(len(result['attempts']), 3)
        self.assertGreater(result['attempts'][1]['scale'], 1.0)
        # The third attempt bisects between "fitted" and "overflowed" instead of oscillating.
        self.assertLess(result['attempts'][2]['scale'], result['attempts'][1]['scale'])
        self.assertGreater(result['attempts'][2]['scale'], result['attempts'][0]['scale'])

    def test_printer_problem_does_not_raise(self):
        with patch.object(press, 'render_pdf', side_effect=self.fake_pdf(1)), \
             patch.object(press, 'measure_layout', return_value={'fill': 0.95, 'heights': {}}), \
             patch.object(press, 'available_printers', return_value=[]):
            result = press.print_edition(EDITION, dry_run=False)
        self.assertFalse(result['ok'])
        self.assertIn('No printer is configured', result['error'])
        self.assertTrue(pathlib.Path(result['pdf']).exists())


@unittest.skipUnless(press.chrome_path(), 'no headless browser available')
class RealPdfTests(unittest.TestCase):
    def test_chrome_renders_a_real_one_page_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / 'edition.pdf'
            path, error = press.render_pdf(press.render_html(EDITION), str(out))
            self.assertEqual(error, '')
            self.assertTrue(pathlib.Path(path).exists())
            self.assertGreaterEqual(press.page_count(path), 1)


class RouteTests(unittest.TestCase):
    def test_route_wires_saved_state_to_the_press(self):
        import dashboard.plugin_api as api
        composed = ({'number': 1, 'storyCount': 0, 'sections': [], 'lead': None}, {'line': 'first'}, [])
        with patch.object(api.engine, 'compose', return_value=composed), \
             patch.object(api.press, 'print_edition', return_value={'ok': True, 'pages': 1}) as called:
            result = api.print_paper(api.PrintBody(dry_run=True))
        called.assert_called_once()
        self.assertTrue(result['ok'])
        edition = called.call_args[0][0]
        self.assertEqual(edition['standfirst'], 'first')


if __name__ == '__main__':
    unittest.main()
