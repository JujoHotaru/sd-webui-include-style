"""includefile 構文の一時ディレクトリを使った回帰テスト。"""

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_includestyle as core


class IncludeFileTests(unittest.TestCase):
    def setUp(self):
        # 既存テストのホストスタブとプロンプト生成処理だけを再利用する
        self.core = core.IncludeStyleTests()
        self.core.setUp()
        self.module = self.core.module
        self.shared = self.core.shared
        self.script = self.core.script
        self.tempdir = tempfile.TemporaryDirectory()
        self.prompts = Path(self.tempdir.name)
        self.directory_patch = mock.patch.object(self.module, 'PROMPTS_DIRECTORY', self.prompts)
        self.directory_patch.start()

    def tearDown(self):
        self.directory_patch.stop()
        self.core.tearDown()
        self.tempdir.cleanup()

    def prompt(self, *args, **kwargs):
        return self.core.prompt(*args, **kwargs)

    def write_prompt(self, name, content):
        path = self.prompts / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        return path

    def test_markers_paths_extension_and_argument_whitespace(self):
        self.write_prompt('foobar.txt', 'plain')
        self.write_prompt('nested/child.txt', 'child')
        self.write_prompt('slash/child.txt', 'slash')
        p = self.prompt(
            '#includefile< foobar > $includefile < nested/child.txt > %includefile<slash\\child>',
            '#includefile<foobar.txt>',
        )
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'plain child slash')
        self.assertEqual(p.negative_prompt, 'plain')

    def test_utf8_file_edges_are_trimmed_and_internal_whitespace_is_preserved(self):
        for bom in (b'', b'\xef\xbb\xbf'):
            with self.subTest(bom=bom):
                self.write_prompt('spacing.txt', bom + b' \t\r\nbody \t\r\nend  \r\n')
                p = self.prompt(' \t[#includefile<spacing>]\n', '#includefile<spacing>')
                self.script.before_process(p)
                self.assertEqual(p.prompt, ' \t[body \t\r\nend]\n')
                self.assertEqual(p.negative_prompt, 'body \t\r\nend')
                self.script.postprocess(p)

    def test_file_alias_markers_paths_nested_styles_and_adetailer(self):
        self.write_prompt('日本語.txt', ' \t#inc<base> / $include<base>\r\n')
        self.write_prompt('nested/child.txt', '%file<日本語> + #includefile<日本語.txt>')
        self.shared.prompt_styles.styles['bridge'] = core.PromptStyle(
            'bridge', '#file<nested/child>', '$file<nested\\child.txt>',
        )
        for marker in ('#', '$', '%'):
            with self.subTest(marker=marker):
                p = self.prompt(
                    [f'{marker}file < nested/child >', '#inc<bridge>'],
                    f'{marker}file < nested\\child.txt >',
                    extra={'ADetailer prompt': f'{marker}file<日本語>',
                           'ADetailer negative prompt 3rd': [f'{marker}file<日本語.txt>']},
                )
                self.script.before_process(p)
                self.script.process(p)
                self.assertEqual(p.prompt, ['基本 / 基本 + 基本 / 基本'] * 2)
                self.assertEqual(p.negative_prompt, '基本ネガ / 基本ネガ + 基本ネガ / 基本ネガ')
                self.assertEqual(p.extra_generation_params['ADetailer prompt'], '基本 / 基本')
                self.assertEqual(p.extra_generation_params['ADetailer negative prompt 3rd'],
                                 ['基本ネガ / 基本ネガ'])
                self.script.postprocess(p)

    def test_file_alias_rules_and_mixed_name_cycle_stops_generation(self):
        self.write_prompt('rules.txt', '#delete<remove>#replace<red|pink>red remove')
        self.write_prompt('cycle.txt', '#includefile<cycle> kept')
        p = self.prompt('#file<rules>', '%file<cycle>')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, '循環参照'):
                self.script.before_process(p)
        self.assertEqual(p.prompt, '#file<rules>')
        self.assertEqual(p.negative_prompt, '%file<cycle>')
        self.assertIn('Error', output.getvalue())

    def test_file_alias_invalid_paths_and_unknown_command_names(self):
        for marker in ('#', '$', '%'):
            with self.subTest(marker=marker):
                missing = self.prompt(f'{marker}file<missing>')
                missing_output = io.StringIO()
                with contextlib.redirect_stdout(missing_output):
                    with self.assertRaisesRegex(RuntimeError, '見つかりません'):
                        self.script.before_process(missing)
                self.assertIn('Error', missing_output.getvalue())

                p = self.prompt(f'{marker}file<../outside> '
                                f'{marker}FILE<base> {marker}filename<base>')
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(RuntimeError, 'パスが無効'):
                        self.script.before_process(p)
                self.assertEqual(p.prompt, f'{marker}file<../outside> '
                                  f'{marker}FILE<base> {marker}filename<base>')
                self.assertIn('Error', output.getvalue())

                unknown = self.prompt(f'{marker}FILE<base> {marker}filename<base>')
                self.script.before_process(unknown)
                self.assertEqual(unknown.prompt, f'{marker}FILE<base> {marker}filename<base>')
                self.script.postprocess(unknown)

    def test_nested_references_and_whitespace_only_files_are_trimmed(self):
        self.write_prompt('empty.txt', ' \t\r\n\u3000')
        self.write_prompt('inner.txt', ' \t\r\ninside\u3000')
        self.write_prompt('outer.txt', '#includefile<empty> \n#includefile<inner>\t')
        self.shared.prompt_styles.styles['bridge'] = self.module.styles.PromptStyle(
            'bridge', ' \t#includefile<outer>\n', '\n#includefile<outer>\t',
        )
        p = self.prompt(['[#include<bridge>]', '[$includefile<outer>]', '%includefile<empty>'],
                        ['[%include<bridge>]', '[%includefile<outer>]'])
        self.script.before_process(p)
        self.assertEqual(p.prompt, ['[inside]', '[inside]', ''])
        self.assertEqual(p.negative_prompt, ['[inside]', '[inside]'])

    def test_bom_utf16_little_and_big_endian_expand_both_fields(self):
        source = ' \t\r\n日本語 \t\r\n#include<base> \r\n'
        for encoding, expected_positive, expected_negative in (
                ('utf-16-le', '日本語 \t\r\n基本', '日本語 \t\r\n基本ネガ'),
                ('utf-16-be', '日本語 \t\r\n基本', '日本語 \t\r\n基本ネガ')):
            with self.subTest(encoding=encoding):
                payload = (b'\xff\xfe' if encoding == 'utf-16-le' else b'\xfe\xff')
                (self.prompts / 'utf16.txt').write_bytes(payload + source.encode(encoding))
                p = self.prompt('#includefile<utf16>', '#includefile<utf16>')
                self.script.before_process(p)
                self.assertEqual(p.prompt, expected_positive)
                self.assertEqual(p.negative_prompt, expected_negative)
                self.script.postprocess(p)

    def test_utf16_without_bom_is_read_as_utf8(self):
        self.write_prompt('without-bom.txt', 'plain'.encode('utf-16-le'))
        p = self.prompt('#includefile<without-bom>')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'p\x00l\x00a\x00i\x00n\x00')

    def test_incomplete_bom_utf16_reports_error_and_stops_generation(self):
        for bom in (b'\xff\xfe', b'\xfe\xff'):
            with self.subTest(bom=bom):
                self.write_prompt('incomplete.txt', bom + b'\x61')
                p = self.prompt('before #includefile<incomplete> after')
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(RuntimeError, '読み込めません'):
                        self.script.before_process(p)
                self.assertEqual(p.prompt, 'before #includefile<incomplete> after')
                self.assertIn('Error', output.getvalue())

    def test_file_internal_style_include_uses_current_prompt_field(self):
        self.write_prompt('fields.txt', 'P=#include<base>')
        p = self.prompt('#includefile<fields>', '#includefile<fields>')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'P=基本')
        self.assertEqual(p.negative_prompt, 'P=基本ネガ')

    def test_nested_file_and_style_references_and_mixed_cycle_stops_generation(self):
        self.write_prompt('outer.txt', 'A #includefile<inner> Z')
        self.write_prompt('inner.txt', '#include<bridge>')
        self.write_prompt('back.txt', 'D #include<bridge> E')
        self.shared.prompt_styles.styles.update({
            'bridge': self.module.styles.PromptStyle('bridge', 'B #includefile<back> C', ''),
        })
        p = self.prompt('#includefile<outer>')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, '循環参照'):
                self.script.before_process(p)
        self.assertEqual(p.prompt, '#includefile<outer>')
        self.assertIn('Error', output.getvalue())

    def test_file_directives_are_applied_after_expansion_to_prompt_and_styles(self):
        self.write_prompt('rules.txt', '#delete<remove> #replace<black|white>')
        self.shared.prompt_styles.styles['target'] = self.module.styles.PromptStyle('target', 'remove black', '')
        p = self.prompt('remove black #includefile<rules>', selected=['unused'])
        self.script.before_process(p)
        self.assertEqual(p.prompt, ' white  ')
        self.assertEqual(self.shared.prompt_styles.styles['target'].prompt, ' white')

    def test_selected_style_can_include_file_and_file_can_include_style(self):
        self.write_prompt('selected.txt', ' \t\r\nfile #include<base>\n ')
        self.shared.prompt_styles.styles['selected'] = self.module.styles.PromptStyle(
            'selected', '#includefile<selected>', '#includefile<selected>'
        )
        p = self.prompt('', '', selected=['selected'])
        self.script.before_process(p)
        self.assertEqual(self.shared.prompt_styles.styles['selected'].prompt, 'file 基本')
        self.assertEqual(self.shared.prompt_styles.styles['selected'].negative_prompt, 'file 基本ネガ')

    def test_adetailer_numbered_keys_and_lists_expand_files_by_field(self):
        self.write_prompt('fields.txt', ' \t\r\n#include<base>\n ')
        extra = {
            'ADetailer prompt': '#includefile<fields>',
            'ADetailer prompt 2': ['x #includefile<fields>', '#includefile<fields>'],
            'ADetailer negative prompt 3': ['#includefile<fields>'],
        }
        p = self.prompt(extra=extra)
        self.script.process(p)
        self.assertEqual(extra['ADetailer prompt'], '基本')
        self.assertEqual(extra['ADetailer prompt 2'], ['x 基本', '基本'])
        self.assertEqual(extra['ADetailer negative prompt 3'], ['基本ネガ'])

    def test_invalid_encoding_and_unsafe_paths_report_errors(self):
        self.write_prompt('bad.txt', b'\xff')
        invalid_encoding = self.prompt('before #includefile<bad> after')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, '生成を中止'):
                self.script.before_process(invalid_encoding)
        self.assertEqual(invalid_encoding.prompt, 'before #includefile<bad> after')
        self.assertIn('Error', output.getvalue())

        invalid_path = self.prompt('before #includefile<../outside> after')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, 'パスが無効'):
                self.script.before_process(invalid_path)
        self.assertEqual(invalid_path.prompt, 'before #includefile<../outside> after')
        self.assertIn('Error', output.getvalue())

    def test_external_file_symbolic_link_is_read_in_both_prompt_fields(self):
        outside_dir = tempfile.TemporaryDirectory()
        self.addCleanup(outside_dir.cleanup)
        outside = Path(outside_dir.name) / 'outside.txt'
        outside.write_text('outside', encoding='utf-8')
        link = self.prompts / 'escape.txt'
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'この環境ではシンボリックリンクを作成できません: {exc}')
        p = self.prompt('#includefile<escape>', '#includefile<escape>')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'outside')
        self.assertEqual(p.negative_prompt, 'outside')

    def test_external_directory_link_supports_both_path_separators(self):
        outside_dir = tempfile.TemporaryDirectory()
        self.addCleanup(outside_dir.cleanup)
        outside = Path(outside_dir.name)
        (outside / 'child.txt').write_text('child', encoding='utf-8')
        link = self.prompts / 'external'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'この環境ではシンボリックリンクを作成できません: {exc}')
        p = self.prompt('#includefile<external/child>#includefile<external\\child>')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'childchild')

    def test_cycle_through_alias_of_same_external_file_precedes_depth_limit(self):
        outside_dir = tempfile.TemporaryDirectory()
        self.addCleanup(outside_dir.cleanup)
        target = Path(outside_dir.name) / 'cycle.txt'
        target.write_text('before #includefile<alias> after', encoding='utf-8')
        alias = self.prompts / 'alias.txt'
        entry = self.prompts / 'entry.txt'
        try:
            alias.symlink_to(target)
            entry.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'この環境ではシンボリックリンクを作成できません: {exc}')
        depth_patch = mock.patch.object(self.module, 'MAX_INCLUDE_DEPTH', 1)
        depth_patch.start()
        try:
            p = self.prompt('#includefile<entry>')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                with self.assertRaisesRegex(RuntimeError, '循環参照'):
                    self.script.before_process(p)
            self.assertEqual(p.prompt, '#includefile<entry>')
            self.assertIn('Error', output.getvalue())
            self.assertNotIn('depth limit', output.getvalue())
        finally:
            depth_patch.stop()

    def test_aliases_to_same_external_file_share_read_cache(self):
        outside_dir = tempfile.TemporaryDirectory()
        self.addCleanup(outside_dir.cleanup)
        target = Path(outside_dir.name) / 'shared.txt'
        target.write_text('shared', encoding='utf-8')
        first = self.prompts / 'first.txt'
        second = self.prompts / 'second.txt'
        try:
            first.symlink_to(target)
            second.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'この環境ではシンボリックリンクを作成できません: {exc}')
        original_open = Path.open
        reads = []

        def open_file(current, *args, **kwargs):
            if current.resolve() == target.resolve():
                reads.append(current)
            return original_open(current, *args, **kwargs)

        p = self.prompt('#includefile<first>#includefile<second>')
        with mock.patch.object(Path, 'open', open_file):
            self.script.before_process(p)
        self.assertEqual(p.prompt, 'sharedshared')
        self.assertEqual(len(reads), 1)

    def test_broken_symbolic_link_reports_error_and_stops_generation(self):
        outside_dir = tempfile.TemporaryDirectory()
        self.addCleanup(outside_dir.cleanup)
        missing = Path(outside_dir.name) / 'missing.txt'
        link = self.prompts / 'broken.txt'
        try:
            link.symlink_to(missing)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'この環境ではシンボリックリンクを作成できません: {exc}')
        p = self.prompt('before #includefile<broken> after')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, '生成を中止'):
                self.script.before_process(p)
        self.assertEqual(p.prompt, 'before #includefile<broken> after')
        self.assertIn('Error', output.getvalue())

    def test_self_and_mutual_file_cycles_report_error_and_stop_generation(self):
        self.write_prompt('self.txt', 'S #includefile<self> E')
        self.write_prompt('left.txt', 'L #includefile<right> R')
        self.write_prompt('right.txt', 'Q #includefile<left> Z')
        p = self.prompt('#includefile<self>|#includefile<left>')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, '循環参照'):
                self.script.before_process(p)
        self.assertEqual(p.prompt, '#includefile<self>|#includefile<left>')
        self.assertIn('Error', output.getvalue())

    def test_file_expansion_uses_existing_depth_and_length_limits(self):
        self.write_prompt('one.txt', '#includefile<two>')
        self.write_prompt('two.txt', '#includefile<three>')
        self.write_prompt('three.txt', 'deepest')
        self.shared.prompt_styles.styles['from-file'] = self.module.styles.PromptStyle(
            'from-file', '#includefile<one>', ''
        )
        depth_patch = mock.patch.object(self.module, 'MAX_INCLUDE_DEPTH', 2)
        depth_patch.start()
        try:
            p = self.prompt('#include<from-file>')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.script.before_process(p)
            self.assertNotIn('deepest', p.prompt)
            self.assertIn('depth limit', output.getvalue())
            self.script.postprocess(p)
        finally:
            depth_patch.stop()

        self.write_prompt('large.txt', '123456')
        self.shared.prompt_styles.styles['too-large'] = self.module.styles.PromptStyle(
            'too-large', '#includefile<large>', ''
        )
        length_patch = mock.patch.object(self.module, 'MAX_PROMPT_LENGTH', 5)
        length_patch.start()
        try:
            p = self.prompt('#include<too-large>')
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.script.before_process(p)
            self.assertEqual(p.prompt, '')
            self.assertIn('length limit', output.getvalue())
        finally:
            length_patch.stop()

    def test_file_cache_is_scoped_to_one_generation(self):
        path = self.write_prompt('changing.txt', 'first')
        p1 = self.prompt('#includefile<changing>')
        self.script.before_process(p1)
        self.assertEqual(p1.prompt, 'first')
        path.write_text('second', encoding='utf-8')
        p1.extra_generation_params['ADetailer prompt'] = '#includefile<changing>'
        self.script.process(p1)
        self.assertEqual(p1.extra_generation_params['ADetailer prompt'], 'first')
        self.script.postprocess(p1)
        p2 = self.prompt('#includefile<changing>')
        self.script.before_process(p2)
        self.assertEqual(p2.prompt, 'second')

    def test_absolute_empty_and_device_filenames_are_not_opened(self):
        p = self.prompt('#includefile<>#includefile<.>#includefile</absolute>#includefile<C:relative>'
                        '#includefile<NUL>#includefile<CON.txt>')
        with mock.patch.object(Path, 'open') as opened, contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, 'パスが無効'):
                self.script.before_process(p)
        opened.assert_not_called()
        self.assertIn('#includefile<', p.prompt)

    def test_one_resolver_reads_a_file_once_for_both_prompt_fields(self):
        path = self.write_prompt('cached.txt', '#include<base>')
        original_open = Path.open
        reads = []

        def open_file(current, *args, **kwargs):
            if current == path:
                reads.append(current)
            return original_open(current, *args, **kwargs)

        p = self.prompt('#includefile<cached>#includefile<cached.txt>', '#includefile<cached>')
        with mock.patch.object(Path, 'open', open_file):
            self.script.before_process(p)
        self.assertEqual(len(reads), 1)
        self.assertEqual(p.prompt, '基本基本')
        self.assertEqual(p.negative_prompt, '基本ネガ')


if __name__ == '__main__':
    unittest.main()
