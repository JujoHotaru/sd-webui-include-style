"""展開上限とホストの終了・再入処理に関する回帰テスト。"""

import contextlib
import copy
import io
import threading
import unittest
from unittest import mock

import test_includestyle as core


class LimitsAndStateTests(unittest.TestCase):
    setUp = core.IncludeStyleTests.setUp
    tearDown = core.IncludeStyleTests.tearDown
    prompt = core.IncludeStyleTests.prompt

    def test_empty_original_dictionary_restores_its_identity(self):
        original = {}
        self.shared.prompt_styles.styles = original
        p = self.prompt('plain')
        self.script.before_process(p)
        self.script.postprocess(p)
        self.assertIs(self.shared.prompt_styles.styles, original)

    def test_forward_reference_to_none_style_fields_is_safe(self):
        self.shared.prompt_styles.styles = {
            'first': core.PromptStyle('first', '#include<empty>', '#include<empty>'),
            'empty': core.PromptStyle('empty', None, None),
        }
        p = self.prompt('#include<first>', '#include<first>')
        self.script.before_process(p)
        self.assertEqual((p.prompt, p.negative_prompt), ('', ''))

    def test_shallow_copy_close_is_bound_to_child(self):
        original = self.shared.prompt_styles.styles
        parent = self.prompt('#include<base>')
        self.script.before_process(parent)
        parent_styles = self.shared.prompt_styles.styles
        child = copy.copy(parent)
        child.prompt = '#include<base>'
        self.processing_objects.append(child)
        self.script.before_process(child)
        child.close()
        self.assertTrue(child.closed)
        self.assertFalse(parent.closed)
        self.assertIs(self.shared.prompt_styles.styles, parent_styles)
        parent.close()
        self.assertTrue(parent.closed)
        self.assertIs(self.shared.prompt_styles.styles, original)

    def test_close_failure_still_restores_styles(self):
        original = self.shared.prompt_styles.styles
        p = self.prompt('#include<base>')
        p.close = mock.Mock(side_effect=RuntimeError('ホストの終了失敗'))
        self.script.before_process(p)
        with self.assertRaisesRegex(RuntimeError, 'ホストの終了失敗'):
            p.close()
        self.assertIs(self.shared.prompt_styles.styles, original)

    def test_parent_finishing_before_child_defers_restoration(self):
        original = self.shared.prompt_styles.styles
        parent, child = self.prompt(), self.prompt()
        self.script.before_process(parent)
        self.script.before_process(child)
        child_styles = self.shared.prompt_styles.styles
        self.script.postprocess(parent)
        self.assertIs(self.shared.prompt_styles.styles, child_styles)
        self.script.postprocess(child)
        self.assertIs(self.shared.prompt_styles.styles, original)

    def test_repeated_processing_object_does_not_leave_backup(self):
        original = self.shared.prompt_styles.styles
        p = self.prompt('#include<base>')
        self.script.before_process(p)
        self.script.before_process(p)
        p.close()
        self.assertIs(self.shared.prompt_styles.styles, original)

    def test_adetailer_resume_copy_without_close_is_restored_by_parent(self):
        original = self.shared.prompt_styles.styles
        parent = self.prompt('#include<base>')
        self.script.before_process(parent)
        self.script.postprocess(copy.copy(parent))
        child = copy.copy(parent)
        self.processing_objects.append(child)
        self.script.before_process(child)
        self.assertIsNot(self.shared.prompt_styles.styles, original)
        self.script.postprocess(parent)
        self.assertIs(self.shared.prompt_styles.styles, original)
        self.assertEqual(self.module._STYLE_STATES, [])
        child.close()
        parent.close()
        self.assertIs(self.shared.prompt_styles.styles, original)

    def test_parent_close_recovers_unclosed_copy_after_exception(self):
        original = self.shared.prompt_styles.styles
        parent = self.prompt()
        self.script.before_process(parent)
        child = copy.copy(parent)
        self.processing_objects.append(child)
        self.script.before_process(child)
        grandchild = copy.copy(child)
        self.processing_objects.append(grandchild)
        self.script.before_process(grandchild)
        parent.close()
        self.assertIs(self.shared.prompt_styles.styles, original)
        self.assertEqual(self.module._STYLE_STATES, [])

    def test_depth_limit_warns_and_terminates(self):
        self.shared.prompt_styles.styles = {
            str(index): core.PromptStyle(str(index), f'x#include<{index + 1}>', '')
            for index in range(8)
        }
        self.shared.prompt_styles.styles['8'] = core.PromptStyle('8', 'end', '')
        p = self.prompt('#include<0>')
        output = io.StringIO()
        with mock.patch.object(self.module, 'MAX_INCLUDE_DEPTH', 4), contextlib.redirect_stdout(output):
            self.script.before_process(p)
        self.assertIn('depth limit', output.getvalue())
        self.assertNotIn('include', p.prompt)
        self.assertLessEqual(len(p.prompt), 4)

    def test_exponentially_growing_acyclic_includes_are_bounded(self):
        data = {'0': core.PromptStyle('0', 'x' * 10, '')}
        for index in range(1, 8):
            data[str(index)] = core.PromptStyle(str(index), f'#include<{index - 1}>' * 2, '')
        self.shared.prompt_styles.styles = data
        p = self.prompt('#include<7>')
        output = io.StringIO()
        with mock.patch.object(self.module, 'MAX_PROMPT_LENGTH', 64), contextlib.redirect_stdout(output):
            self.script.before_process(p)
        self.assertIn('length limit', output.getvalue())
        self.assertLessEqual(len(p.prompt), 64)
        self.assertTrue(all(len(style.prompt) <= 64 for style in self.shared.prompt_styles.styles.values()))

    def test_replacement_length_failure_does_not_publish_partial_changes(self):
        original = self.shared.prompt_styles.styles
        text = '#replace<a|aaaaaa>' + 'a' * 12
        p = self.prompt(text)
        with mock.patch.object(self.module, 'MAX_PROMPT_LENGTH', 64):
            with self.assertRaisesRegex(ValueError, 'length limit'):
                self.script.before_process(p)
        self.assertIs(self.shared.prompt_styles.styles, original)
        self.assertEqual(p.prompt, text)
        following = self.prompt('plain')
        self.script.before_process(following)
        following.close()
        self.assertIs(self.shared.prompt_styles.styles, original)

    def test_directives_in_positive_and_negative_do_not_cross(self):
        p = self.prompt('#replace<cat|dog>cat', '#replace<cat|bird>cat')
        self.script.before_process(p)
        self.assertEqual((p.prompt, p.negative_prompt), ('dog', 'bird'))

    def test_selected_style_preserves_whitespace_but_include_trims_it(self):
        self.shared.prompt_styles.styles['space'] = core.PromptStyle('space', '  cat  ', '  bad  ')
        p = self.prompt('#include<space>', '#include<space>', selected=['space'])
        self.script.before_process(p)
        self.assertEqual((p.prompt, p.negative_prompt), ('cat', 'bad'))
        self.assertEqual(self.shared.prompt_styles.styles['space'].prompt, '  cat  ')

    def test_empty_fields_and_empty_deletion_are_supported(self):
        p = self.prompt(None, None)
        self.script.before_process(p)
        self.assertEqual((p.prompt, p.negative_prompt), ('', ''))
        p.close()
        p = self.prompt('#delete<>keep')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'keep')

    def test_adetailer_numbered_negative_metadata_and_other_values(self):
        p = self.prompt(extra={
            'ADetailer negative prompt 2': '$include<base>',
            'ADetailer prompt 3': ['%include<base>', 'plain'],
            'ADetailer prompt 2nd': '#include<base>',
            'ADetailer negative prompt 3rd': '$include<base>',
            'ADetailer prompt 4th': '%include<base>',
            'ADetailer prompt count': 3,
            'Other prompt': '#include<base>',
        })
        self.script.process(p)
        self.assertEqual(p.extra_generation_params['ADetailer negative prompt 2'], '基本ネガ')
        self.assertEqual(p.extra_generation_params['ADetailer prompt 3'], ['基本', 'plain'])
        self.assertEqual(p.extra_generation_params['ADetailer prompt 2nd'], '基本')
        self.assertEqual(p.extra_generation_params['ADetailer negative prompt 3rd'], '基本ネガ')
        self.assertEqual(p.extra_generation_params['ADetailer prompt 4th'], '基本')
        self.assertEqual(p.extra_generation_params['ADetailer prompt count'], 3)
        self.assertEqual(p.extra_generation_params['Other prompt'], '#include<base>')

    def test_other_worker_waits_until_styles_are_restored(self):
        original = self.shared.prompt_styles.styles
        parent = self.prompt()
        self.script.before_process(parent)
        started, prepared = threading.Event(), threading.Event()
        errors = []

        def worker():
            p = self.prompt('#include<base>')
            try:
                started.set()
                self.module.IncludeStyleScript().before_process(p)
                prepared.set()
                self.assertEqual(p.prompt, '基本')
            except BaseException as error:
                errors.append(error)
            finally:
                p.close()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        try:
            self.assertTrue(started.wait(2))
            self.assertFalse(prepared.wait(0.05))
        finally:
            parent.close()
            thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(prepared.is_set())
        self.assertIs(self.shared.prompt_styles.styles, original)


if __name__ == '__main__':
    unittest.main()
