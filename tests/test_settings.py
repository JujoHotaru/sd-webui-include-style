"""生成画面のチェック状態と、参照先がない場合の停止・警告動作の回帰テスト。"""

import contextlib
import copy
import io
import unittest
from unittest import mock

import test_includefile as files
import test_includestyle as core


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.files = files.IncludeFileTests()
        self.files.setUp()
        self.addCleanup(self.files.tearDown)
        self.core = self.files.core
        self.module = self.core.module
        self.shared = self.core.shared
        self.script = self.core.script
        self.prompt = self.core.prompt
        self.write_prompt = self.files.write_prompt
        self.error_on_missing = True

    def test_template_loading_checkbox_defaults_and_syncs_in_both_directions(self):
        for is_img2img in (False, True):
            self.assertEqual(len(self.script.ui(is_img2img)), 1)
        controls = self.module._TEMPLATE_PROMPT_CHECKBOXES
        for tab, checkbox in controls.items():
            self.assertIs(checkbox.value, True)
            self.assertEqual(checkbox.label, '画像情報の読み込み時にテンプレートプロンプトを読み込む')
            self.assertEqual(checkbox.elem_id, f'include_style_{tab}_load_template_prompts')
            self.assertIs(checkbox.do_not_save_to_config, True)
        for tab, enabled in (('txt2img', False), ('img2img', True)):
            checkbox = controls[tab]
            checkbox.value = enabled
            for call in checkbox.input.call_args_list:
                binding = call.kwargs
                self.assertEqual(binding['inputs'], [checkbox])
                self.assertIs(binding['queue'], False)
                result = binding['fn'](enabled)
                for target in binding.get('outputs', []):
                    target.value = result
            self.assertIs(self.module._load_template_prompts_enabled(), enabled)
            self.assertTrue(all(control.value is enabled for control in controls.values()))

    def test_ui_rebuild_discards_old_controls_and_keeps_current_setting(self):
        self.script.ui(False)
        self.module._set_load_template_prompts(False)
        self.assertEqual(self.core.before_ui_callbacks, [self.module._reset_template_prompt_checkboxes])
        self.core.before_ui_callbacks[0]()
        self.assertEqual(self.module._TEMPLATE_PROMPT_CHECKBOXES, {})
        self.script.ui(False)
        checkbox = self.module._TEMPLATE_PROMPT_CHECKBOXES['txt2img']
        self.assertIs(checkbox.value, False)
        self.assertEqual(checkbox.input.call_count, 1)

    def allow_missing(self):
        self.error_on_missing = False

    def test_default_argument_stops_generation_and_aborts_host_init(self):
        p = self.prompt('#include<missing>')
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, '見つかりません'):
                self.script.before_process(p)
        with self.assertRaisesRegex(RuntimeError, '生成を中止'):
            p.init()
        self.assertIs(self.shared.prompt_styles.styles, self.core.styles)

    def test_warning_mode_handles_all_markers_aliases_lists_and_preserves_init(self):
        self.allow_missing()
        for marker in ('#', '$', '%'):
            for command in ('include', 'inc', 'includefile', 'file'):
                with self.subTest(marker=marker, command=command):
                    p = self.prompt([f'left {marker}{command} < 不明 > right'] * 2,
                                    f'bad {marker}{command}<不明>')
                    p.init = mock.Mock()
                    original_init = p.init
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        self.script.before_process(p, self.error_on_missing)
                    self.assertEqual(p.prompt, ['left  right'] * 2)
                    self.assertEqual(p.negative_prompt, 'bad ')
                    self.assertIs(p.init, original_init)
                    self.assertEqual(output.getvalue().count('Warning:'), 1)
                    self.assertIn('不明', output.getvalue())
                    self.assertNotIn('Error:', output.getvalue())
                    p.close()
                    self.assertIs(self.shared.prompt_styles.styles, self.core.styles)

    def test_warning_mode_resolves_selected_nested_styles_and_rules(self):
        self.allow_missing()
        self.shared.prompt_styles.styles.update({
            'inner': core.PromptStyle('inner', 'red #inc<missing>', '#delete<bad>'),
            'outer': core.PromptStyle('outer', '#include<inner>#file<missing>', '#include<inner>kept'),
        })
        p = self.prompt('red #include<outer>#replace<red|pink>', 'bad remain', selected=['outer'])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.script.before_process(p, self.error_on_missing)
        self.assertEqual(p.prompt, 'pink pink')
        self.assertEqual(p.negative_prompt, ' remain')
        self.assertEqual(self.shared.prompt_styles.styles['outer'].prompt, 'pink')
        self.assertEqual(self.shared.prompt_styles.styles['outer'].negative_prompt, 'kept')
        self.assertEqual(output.getvalue().count('Warning:'), 2)

    def test_direct_style_with_missing_file_still_applies_opposite_rules(self):
        self.allow_missing()
        self.shared.prompt_styles.styles['direct'] = core.PromptStyle(
            'direct', 'good #file<missing>', '#delete<bad>',
        )
        p = self.prompt('#inc<direct>', 'bad kept')
        with contextlib.redirect_stdout(io.StringIO()):
            self.script.before_process(p, self.error_on_missing)
        self.assertEqual(p.prompt, 'good')
        self.assertEqual(p.negative_prompt, ' kept')
        self.assertEqual(self.shared.prompt_styles.styles['direct'].prompt, 'good ')

    def test_unused_missing_references_stay_silent_in_warning_mode(self):
        self.allow_missing()
        self.shared.prompt_styles.styles['unused'] = core.PromptStyle(
            'unused', '#include<missing>', '#file<missing>',
        )
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.script.before_process(self.prompt('plain'))
        self.assertEqual(output.getvalue(), '')

    def test_missing_in_file_preserves_routing_and_other_content(self):
        self.allow_missing()
        self.write_prompt('child.txt', '##negative##\nbad #file<missing> end')
        self.write_prompt('parent.txt', 'good #inc<missing> #file<child> tail')
        p = self.prompt('#file<parent>', 'original')
        with contextlib.redirect_stdout(io.StringIO()):
            self.script.before_process(p, self.error_on_missing)
        self.assertEqual(p.prompt, 'good')
        self.assertEqual(p.negative_prompt, 'original, bad  end tail')

    def test_adetailer_warns_and_continues_with_and_without_before_process(self):
        self.allow_missing()
        self.shared.prompt_styles.styles['bridge'] = core.PromptStyle(
            'bridge', 'kept #include<missing>', '#file<missing>',
        )
        for prepare in (False, True):
            with self.subTest(prepare=prepare):
                p = self.prompt(extra={
                    'ADetailer prompt 2nd': ['a #include<bridge>', '#file<missing> b'],
                    'ADetailer negative prompt 2nd': '#inc<missing> c',
                })
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    if prepare:
                        self.script.before_process(p, self.error_on_missing)
                    self.script.process(p, self.error_on_missing)
                self.assertEqual(p.extra_generation_params['ADetailer prompt 2nd'], ['a kept', ' b'])
                self.assertEqual(p.extra_generation_params['ADetailer negative prompt 2nd'], ' c')
                self.assertIn('Warning:', output.getvalue())
                self.assertFalse(hasattr(p, 'init'))
                p.close()

    def test_each_generation_uses_its_own_checkbox_argument(self):
        self.allow_missing()
        with contextlib.redirect_stdout(io.StringIO()):
            p = self.prompt('#include<missing>')
            self.script.before_process(p, self.error_on_missing)
            p.close()
            self.error_on_missing = True
            with self.assertRaisesRegex(RuntimeError, '生成を中止'):
                self.script.before_process(self.prompt('#include<missing>'), self.error_on_missing)

    def test_process_reuses_before_process_setting_and_child_keeps_its_argument(self):
        parent = self.prompt('plain', extra={'ADetailer prompt': '#inc<missing> kept'})
        with contextlib.redirect_stdout(io.StringIO()):
            self.script.before_process(parent, False)
            self.script.process(parent)
            self.assertEqual(parent.extra_generation_params['ADetailer prompt'], ' kept')
            child = copy.copy(parent)
            self.core.processing_objects.append(child)
            child.prompt = '#include<missing> child'
            self.script.before_process(child, False)
            self.assertEqual(child.prompt, ' child')
            child.close()
            parent.close()
            with self.assertRaisesRegex(RuntimeError, '生成を中止'):
                self.script.before_process(self.prompt('#include<missing>'))

    def test_warning_mode_keeps_invalid_path_encoding_and_cycle_errors(self):
        self.allow_missing()
        self.write_prompt('invalid.txt', b'\xff')
        self.write_prompt('cycle.txt', '#file<cycle>')
        self.shared.prompt_styles.styles['cycle'] = core.PromptStyle('cycle', '#inc<cycle>', '')
        for command, message in (
            ('#file<../outside>', 'パスが無効'),
            ('#file<invalid>', '読み込めません'),
            ('#file<cycle>', '循環参照'),
            ('#inc<cycle>', '循環参照'),
        ):
            with self.subTest(command=command), contextlib.redirect_stdout(io.StringIO()):
                p = self.prompt(command)
                with self.assertRaisesRegex(RuntimeError, message):
                    self.script.before_process(p, self.error_on_missing)
                with self.assertRaisesRegex(RuntimeError, '生成を中止'):
                    p.init()
                self.assertIs(self.shared.prompt_styles.styles, self.core.styles)


if __name__ == '__main__':
    unittest.main()
