import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from image_background_removal_claim_audit import phrases
from image_background_removal_claim_audit.audit import audit, claims, evidence, main

BACKGROUNDREMOVAL = ['background removal', 'background-removal', 'backgroundremoval', 'background removal model', 'background removal models', 'background removal system', 'background removal systems', 'background removal feature', 'background removal capability', 'background removal support', 'supports background removal', 'background removal tool', 'background removal api', 'background removal pipeline', 'background removal algorithm', 'background removal library', 'background removal framework', 'background removal service', 'background removal function', 'background removal engine', 'background removal engines', 'background remover', 'background removers', 'removes backgrounds', 'remove backgrounds', 'removes background', 'remove background', 'removes image background', 'remove image background', 'removes photo background', 'remove photo background', 'removes the background', 'remove the background', 'image background removal', 'photo background removal', 'removes backgrounds from images', 'remove backgrounds from images', 'automatic background removal', 'automated background removal', 'background removal software', 'background removal app', 'background removal program', 'removes your background', 'background cutout', 'image cutout', 'photo cutout', 'cuts out backgrounds', 'cut out backgrounds', 'makes backgrounds transparent', 'background eraser']
NOBACKGROUNDREMOVAL = ['does not support background removal', 'do not support background removal', "doesn't support background removal", "don't support background removal", 'no background removal', 'without background removal', 'never performs background removal', 'does not perform background removal', 'background removal not supported', 'background removal unsupported', 'no background removal support', 'lacks background removal', 'missing background removal', 'background removal disabled', 'no background removal capability', 'without background removal support', 'does not provide background removal', 'no background removal model', 'background removal not available', 'does not use background removal', 'no background remover', 'without background remover', 'does not support background remover', 'no photo background remover']
GENERIC_NAMES = ['remove_background', 'remove_image_background', 'background_removal', 'remove_bg', 'strip_background', 'cut_out_background', 'extract_foreground', 'remove_background_from_image', 'image_background_removal', 'photo_background_removal', 'background_remover', 'remove_photo_background', 'transparent_background', 'make_background_transparent', 'remove_background_image', 'bg_removal', 'remove_backgrounds', 'background_removal_model', 'predict_transparent_image', 'remove_image_bg', 'cutout_image', 'image_cutout', 'remove_background_from_photo', 'background_removal_tool']
REMOVE_NAMES = ['remove']
REMOVE_SOURCES = ['rembg', 'backgroundremover.bg']
GRABCUT_NAMES = ['grabCut']
REMOVER_CLASSES = ['Remover']
WITHOUTBG_CLASSES = ['WithoutBG']


class OracleTests(unittest.TestCase):
    def test_phrases(self):
        self.assertEqual(phrases.BACKGROUNDREMOVAL, BACKGROUNDREMOVAL)
        self.assertEqual(phrases.NOBACKGROUNDREMOVAL, NOBACKGROUNDREMOVAL)

    def test_generic_names(self):
        self.assertEqual(phrases.GENERIC_NAMES, GENERIC_NAMES)

    def test_remove_route(self):
        self.assertEqual(phrases.REMOVE_NAMES, ['remove'])
        self.assertEqual(phrases.REMOVE_SOURCES, ['rembg', 'backgroundremover.bg'])

    def test_grabcut_names(self):
        self.assertEqual(phrases.GRABCUT_NAMES, ['grabCut'])

    def test_remover_classes(self):
        self.assertEqual(phrases.REMOVER_CLASSES, ['Remover'])

    def test_withoutbg_classes(self):
        self.assertEqual(phrases.WITHOUTBG_CLASSES, ['WithoutBG'])


class MatchingTests(unittest.TestCase):
    def test_all_positive(self):
        for phrase in BACKGROUNDREMOVAL:
            with self.subTest(phrase=phrase):
                self.assertEqual(claims(phrase), ([phrase], []))

    def test_all_negative(self):
        for phrase in NOBACKGROUNDREMOVAL:
            with self.subTest(phrase=phrase):
                self.assertEqual(claims(phrase), ([], [phrase]))

    def test_models_longest(self):
        self.assertEqual(claims('background removal models')[0], ['background removal models'])

    def test_model_longest(self):
        self.assertEqual(claims('background removal model')[0], ['background removal model'])

    def test_case(self):
        self.assertEqual(claims('BACKGROUND REMOVAL')[0], ['background removal'])

    def test_audio_collision(self):
        self.assertEqual(claims('remove background noise from audio')[0], ['remove background'])

    def test_fence(self):
        self.assertEqual(claims('```text\nbackground removal\n```'), ([], []))

    def test_inline(self):
        self.assertEqual(claims('`background removal`')[0], ['background removal'])

    def test_no_hyphen_normalization(self):
        self.assertEqual(claims('remove-background'), ([], []))


class EvidenceTests(unittest.TestCase):
    def test_remove_import_sources(self):
        for source in REMOVE_SOURCES:
            for code in [
                'from {s} import remove; remove(img)',
                'from {s} import remove as cut; cut(img)',
                'import {s}; {s}.remove(img)',
                'import {s} as r; r.remove(img)',
            ]:
                with self.subTest(code=code, source=source):
                    self.assertTrue(evidence(code.format(s=source)))
        self.assertTrue(evidence('from backgroundremover import bg; bg.remove(img)'))

    def test_remover_pairs(self):
        for constructor in ['Remover()', 'tb.Remover()', 'R()']:
            for mode in ['', ", type='rgba'", ", type='green'", ", type='picture.jpg'"]:
                for call in ['r = {c}; r.process(img{m})', '{c}.process(img{m})']:
                    with self.subTest(constructor=constructor, mode=mode, call=call):
                        self.assertTrue(evidence('import transparent_background as tb; from transparent_background import Remover as R; ' + call.format(c=constructor,m=mode)))

    def test_withoutbg_pairs(self):
        for constructor in ['WithoutBG()', 'WithoutBG.open_weights()', 'WithoutBG.api(key)', 'w.WithoutBG.api(key)', 'W.open_weights()']:
            for call in ['r = {c}; r.remove_background(img)', '{c}.remove_background(img)']:
                with self.subTest(constructor=constructor, call=call):
                    self.assertTrue(evidence('import withoutbg as w; from withoutbg import WithoutBG as W; '+call.format(c=constructor)))

    def test_all_direct_generic_forms(self):
        for name in GRABCUT_NAMES + GENERIC_NAMES:
            for code in ['x.{n}(img)', 'from lib import {n}; {n}(img)', 'from lib import {n} as f; f(img)']:
                with self.subTest(name=name, code=code):
                    self.assertTrue(evidence(code.format(n=name)))

    def test_not_evidence(self):
        cases = [
            'import rembg, transparent_background, backgroundremover, withoutbg, cv2',
            'from rembg import remove; remove',
            'from rembg import new_session; new_session()',
            'Remover()', 'WithoutBG()', 'WithoutBG.open_weights()', 'WithoutBG.api(key)',
            'rembg.remove(img)', 'backgroundremover.bg.remove(img)',
            'remove(img)', 'os.remove(file)', 'x.remove(img)', 'lst.remove(item)',
            'import os; os.remove(file)', 'from os import remove; remove(file)',
            'from other import remove as r; r(img)',
            'import rembg; x.remove(img)',
            'mask = cv2.threshold(img, 0, 255, 0)',
            'mask = sam.predict(img)', 'boxes = detector.detect(img)',
            'img = cv2.GaussianBlur(img, (3,3), 0)',
            'mask = np.all(pixels == [0,255,0], axis=-1); pixels[mask] = 0',
            "img.crop(box).resize((10,10)).convert('RGBA')",
            "# rembg.remove(img)\ns = 'background removal; background remover'",
            '\"\"\"background removal\"\"\"',
            'from lib import grabCut; grabCut',
            'from lib import remove_background; remove_background',
            "subprocess.run(['rembg', 'i', 'input.png', 'output.png'])",
            'this is not valid source!'
        ]
        for code in cases:
            with self.subTest(code=code):
                self.assertFalse(evidence(code))

    def test_rejected_modes(self):
        for mode in ['blur', 'map', 'overlay']:
            for code in ['r = Remover(); r.process(img, type={m!r})', 'Remover().process(img, type={m!r})']:
                with self.subTest(mode=mode, code=code):
                    self.assertFalse(evidence(code.format(m=mode)))

    def test_shadowing(self):
        for name, prefix, call in [
            ('remove', 'from rembg import remove', 'remove(img)'),
            ('grabCut', 'from cv2 import grabCut', 'grabCut(img)'),
            ('remove_background', 'from lib import remove_background', 'remove_background(img)'),
            ('Remover', 'from transparent_background import Remover', 'Remover().process(img)'),
            ('WithoutBG', 'from withoutbg import WithoutBG', 'WithoutBG.open_weights().remove_background(img)'),
        ]:
            for definition in ['def {n}(*a): pass', 'class {n}: pass']:
                with self.subTest(name=name, definition=definition):
                    self.assertFalse(evidence(prefix+'\n'+definition.format(n=name)+'\n'+call))
        self.assertFalse(evidence('import rembg as r\ndef r(): pass\nr.remove(img)'))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def cli(self, *options):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(list(options))
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue(), err.getvalue()

    def test_good(self):
        self.write('README.md', 'background removal')
        self.write('app.py', 'import rembg; rembg.remove(img)')
        self.assertEqual(self.cli('audit', str(self.root))[0], 0)
        self.assertEqual(audit(self.root), [])

    def test_bad_json(self):
        self.write('README.md', 'BACKGROUND REMOVAL background removal models')
        code, out, _ = self.cli('audit', str(self.root), '--json')
        self.assertEqual(code, 2)
        data = json.loads(out)
        self.assertEqual(data['verdict'], 'FAIL')
        self.assertEqual(len(data['findings']), 1)
        f = data['findings'][0]
        self.assertEqual(f['rule'], 'documented-image-background-removal-claim-false')
        self.assertEqual(f['severity'], 'HIGH')
        self.assertEqual(f['verdict'], 'FAIL')
        self.assertTrue(f['message'])

    def test_denial(self):
        self.write('README.md', 'does not support background removal')
        self.assertEqual(audit(self.root), [])
        self.write('app.py', 'x.grabCut(img)')
        code, out, _ = self.cli('audit', str(self.root), '--json')
        self.assertEqual(code, 2)
        f = json.loads(out)['findings'][0]
        self.assertEqual(f['rule'], 'documented-no-image-background-removal-claim-false')
        self.assertEqual(f['severity'], 'HIGH')

    def test_test_only(self):
        self.write('tests/fixture.py', "s = 'background removal'")
        self.assertEqual(self.cli('audit', str(self.root))[0], 0)
        self.assertEqual(self.cli('audit', str(self.root), '--fail-on', 'medium')[0], 2)
        self.assertEqual(audit(self.root)[0]['severity'], 'MEDIUM')

    def test_no_claim(self):
        self.write('README.md', 'A still picture tool.')
        self.assertEqual(self.cli('audit', str(self.root))[0], 0)
        self.write('app.py', 'x.grabCut(img)')
        self.assertEqual(audit(self.root), [])

    def test_ignore_before_repo(self):
        self.write('docs/skip.md', 'background removal')
        self.assertEqual(self.cli('audit', '--ignore', 'docs/', str(self.root))[0], 0)
        self.assertEqual(self.cli('audit', str(self.root), '--ignore', 'docs/')[0], 0)

    def test_repeat_ignore(self):
        self.write('docs/a.md', 'background removal')
        self.write('docs/b.md', 'background removal')
        self.assertEqual(self.cli('audit', '--ignore', 'docs/a', '--ignore', 'docs/b', str(self.root))[0], 0)

    def test_version(self):
        self.assertEqual(self.cli('--version')[:2], (0, '0.1.0\n'))

    def test_verbose(self):
        self.write('app.py', 'x.grabCut(img)')
        code, _, err = self.cli('audit', str(self.root), '--verbose')
        self.assertEqual(code, 0)
        self.assertIn('Scope:', err)
        self.assertIn('app.py:', err)

    def test_usage_io(self):
        for args in [[], ['audit', '--unknown'], ['audit', '--fail-on', 'low'], ['audit', str(self.root / 'absent')]]:
            self.assertEqual(self.cli(*args)[0], 1)

    def test_default_repo(self):
        import os
        old = os.getcwd()
        try:
            os.chdir(self.root)
            self.assertEqual(self.cli('audit')[0], 0)
        finally:
            os.chdir(old)

    def test_split_module(self):
        self.write('README.md', 'background removal')
        self.write('a.py', 'from rembg import remove')
        self.write('b.py', 'remove(img)')
        self.write('c.py', 'r = Remover()')
        self.write('d.py', 'r.process(img)')
        self.assertEqual(audit(self.root)[0]['severity'], 'HIGH')

    def test_scope_and_exclusions(self):
        self.write('other.md', 'background removal')
        self.write('docs/nested/a.md', 'background removal')
        for directory in ['.git', '__pycache__', '.venv', 'venv']:
            self.write(directory+'/e.py', 'x.grabCut(img)')
        self.assertEqual(audit(self.root)[0]['severity'], 'HIGH')

    def test_readme_self_audit_only(self):
        readme = Path(__file__).resolve().parents[1] / 'README.md'
        self.write('README.md', readme.read_text())
        self.assertEqual(audit(self.root), [])
        self.assertEqual(self.cli('audit', str(self.root))[0], 0)


if __name__ == '__main__':
    unittest.main()
