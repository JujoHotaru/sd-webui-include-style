"""ファイル内の挿入位置命令と正負プロンプトの連携を確認する。"""

import contextlib
import io
import json
import unittest
from unittest import mock

import test_includefile as files


class FileSectionTests(unittest.TestCase):
    setUp = files.IncludeFileTests.setUp
    tearDown = files.IncludeFileTests.tearDown
    prompt = files.IncludeFileTests.prompt
    write_prompt = files.IncludeFileTests.write_prompt

    def test_aliases_prefixes_and_absolute_destination_from_either_field(self):
        self.write_prompt('日本語.txt', 'initial\n##negative##\nnegative\n##positive##\npositive')
        for command in ('file', 'includefile'):
            for marker in ('#', '$', '%'):
                for negative in (False, True):
                    with self.subTest(command=command, marker=marker, negative=negative):
                        call = f'{marker}{command} < 日本語.txt >'
                        p = self.prompt('P' if negative else f'[{call}]',
                                        f'[{call}]' if negative else 'N')
                        self.script.before_process(p)
                        self.assertEqual(p.prompt, 'P, positive' if negative else '[initial\npositive]')
                        self.assertEqual(p.negative_prompt,
                                         '[initial\nnegative]' if negative else 'N, negative')
                        self.script.postprocess(p)

    def test_repeated_sections_preserve_internal_newlines_and_only_strip_final_edges(self):
        self.write_prompt('sections.txt', ' \tA \r\n##negative##\r\n N1 \r\n'
                          '##positive##\r\n B \r\n##negative##\r\n N2 \r\n'
                          '##positive##\r\n C \t')
        p = self.prompt('[#file<sections>]', 'existing')
        self.script.before_process(p)
        self.assertEqual(p.prompt, '[A \r\n B \r\n C]')
        self.assertEqual(p.negative_prompt, 'existing, N1 \r\n N2')

    def test_consecutive_markers_start_and_end_and_empty_sections(self):
        self.write_prompt('empty.txt', '##negative##\n##positive##\n##positive##\n'
                          'value\n##negative##\n##negative##')
        p = self.prompt('[#file<empty>]', '')
        self.script.before_process(p)
        self.assertEqual(p.prompt, '[value]')
        self.assertEqual(p.negative_prompt, '')

    def test_same_side_only_markers_are_removed_without_extra_separators(self):
        self.write_prompt('positive.txt', 'a\n##positive##\nb\n##positive##\nc')
        self.write_prompt('negative.txt', 'a\n##negative##\nb\n##negative##\nc')
        p = self.prompt('#file<positive>', '#file<negative>')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'a\nb\nc')
        self.assertEqual(p.negative_prompt, 'a\nb\nc')

    def test_markers_require_a_complete_exact_line(self):
        content = ' ##negative##\n##positive## \ninline ##negative##\n##Negative##\nend'
        self.write_prompt('literal.txt', content)
        p = self.prompt('#file<literal>', 'keep')
        self.script.before_process(p)
        self.assertEqual(p.prompt, content.strip())
        self.assertEqual(p.negative_prompt, 'keep')

    def test_prompt_and_style_literal_markers_do_not_switch_destination(self):
        text = 'before\n##negative##\nafter'
        self.shared.prompt_styles.styles['literal'] = files.core.PromptStyle('literal', text, 'other')
        p = self.prompt(text + '\n#include<literal>', 'keep')
        self.script.before_process(p)
        self.assertEqual(p.prompt, text + '\n' + text)
        self.assertEqual(p.negative_prompt, 'keep')

    def test_without_markers_keeps_legacy_replacement_and_input_spacing(self):
        self.write_prompt('legacy.txt', ' \t\r\nbody \r\nend \t')
        p = self.prompt(' A [#file<legacy>] Z ', ' B [#file<legacy>] Y ')
        self.script.before_process(p)
        self.assertEqual(p.prompt, ' A [body \r\nend] Z ')
        self.assertEqual(p.negative_prompt, ' B [body \r\nend] Y ')

    def test_utf16_bom_markers_and_current_destination_style_field(self):
        source = '##positive##\r\n#include<base>\r\n##negative##\r\n#include<base>'
        for encoding, bom in (('utf-16-le', b'\xff\xfe'), ('utf-16-be', b'\xfe\xff')):
            with self.subTest(encoding=encoding):
                self.write_prompt('utf16.txt', bom + source.encode(encoding))
                p = self.prompt('#file<utf16>')
                self.script.before_process(p)
                self.assertEqual(p.prompt, '基本')
                self.assertEqual(p.negative_prompt, '基本ネガ')
                self.script.postprocess(p)

    def test_nested_file_last_destination_flows_into_parent_but_not_main_prompt(self):
        self.write_prompt('child.txt', '##negative##\nchild')
        self.write_prompt('parent.txt', 'parent #file<child> tail')
        p = self.prompt('before [#file<parent>] after', 'existing')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'before [parent] after')
        self.assertEqual(p.negative_prompt, 'existing, child tail')

    def test_nested_final_marker_changes_parent_even_when_child_has_no_text(self):
        self.write_prompt('child.txt', '##negative##')
        self.write_prompt('parent.txt', 'parent #file<child>tail')
        p = self.prompt('#file<parent>')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'parent')
        self.assertEqual(p.negative_prompt, 'tail')

    def test_parent_marker_overrides_child_destination_and_style_uses_current_field(self):
        self.write_prompt('child.txt', '##negative##\nchild')
        self.write_prompt('parent.txt', '#file<child> #include<base>\n'
                          '##positive##\n#include<base>')
        p = self.prompt('#file<parent>')
        self.script.before_process(p)
        self.assertEqual(p.prompt, '基本')
        self.assertEqual(p.negative_prompt, 'child 基本ネガ')

    def test_missing_and_circular_nested_reference_do_not_change_destination(self):
        self.write_prompt('loop.txt', '##negative##\nN #file<loop> #file<missing> tail')
        p = self.prompt('#file<loop>', 'existing')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.script.before_process(p)
        self.assertEqual(p.prompt, '')
        self.assertEqual(p.negative_prompt, 'existing, N   tail')
        self.assertIn('Circular include', output.getvalue())
        self.assertIn('Cannot read prompt file', output.getvalue())

    def test_both_fields_and_multiple_calls_append_in_encounter_order(self):
        self.write_prompt('one.txt', '##positive##\nP1\n##negative##\nN1')
        self.write_prompt('two.txt', '##positive##\nP2\n##negative##\nN2')
        p = self.prompt('x #file<one> / #file<two>', 'y #file<two> / #file<one>')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'x P1 / P2, P2, P1')
        self.assertEqual(p.negative_prompt, 'y N2 / N1, N1, N2')

    def test_opposite_only_text_uses_no_leading_separator_for_empty_receiver(self):
        self.write_prompt('negative.txt', '##negative##\nN')
        p = self.prompt('x#file<negative>y', '')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'xy')
        self.assertEqual(p.negative_prompt, 'N')

    def test_list_cross_field_text_stays_with_matching_image(self):
        self.write_prompt('one.txt', '##negative##\nN1')
        self.write_prompt('two.txt', '##negative##\nN2')
        p = self.prompt(['P1 #file<one>', 'P2 #file<two>'], ['old1', 'old2'])
        self.script.before_process(p)
        self.assertEqual(p.prompt, ['P1 ', 'P2 '])
        self.assertEqual(p.negative_prompt, ['old1, N1', 'old2, N2'])

    def test_scalar_receiver_broadcasts_before_list_cross_field_append(self):
        self.write_prompt('one.txt', '##negative##\nN1')
        self.write_prompt('two.txt', '##negative##\nN2')
        p = self.prompt(['#file<one>', '#file<two>'], 'old')
        self.script.before_process(p)
        self.assertEqual(p.prompt, ['', ''])
        self.assertEqual(p.negative_prompt, ['old, N1', 'old, N2'])

    def test_scalar_source_cross_field_append_broadcasts_to_list_receiver(self):
        self.write_prompt('one.txt', '##negative##\nN')
        p = self.prompt('#file<one>', ['old1', 'old2'])
        self.script.before_process(p)
        self.assertEqual(p.negative_prompt, ['old1, N', 'old2, N'])

    def test_cross_field_delete_then_replace_applies_to_destination_only(self):
        self.write_prompt('rules.txt', '##negative##\n#replace<red|pink>#delete<bad>red')
        p = self.prompt('bad red #file<rules>', 'bad red')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'bad red ')
        self.assertEqual(p.negative_prompt, ' pink, pink')

    def test_direct_style_reference_routes_file_output_to_opposite_prompt(self):
        self.write_prompt('split.txt', 'P\n##negative##\nN')
        self.shared.prompt_styles.styles['bridge'] = files.core.PromptStyle('bridge', '#file<split>', '')
        p = self.prompt('[#include<bridge>]', 'old')
        self.script.before_process(p)
        self.assertEqual(p.prompt, '[P]')
        self.assertEqual(p.negative_prompt, 'old, N')

    def test_unselected_style_does_not_append_to_main_prompt(self):
        self.write_prompt('split.txt', 'P\n##negative##\nN')
        self.shared.prompt_styles.styles['unused'] = files.core.PromptStyle('unused', '#file<split>', '')
        p = self.prompt('plain', 'negative')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'plain')
        self.assertEqual(p.negative_prompt, 'negative')

    def test_selected_style_routes_file_output_into_opposite_working_style_field(self):
        self.write_prompt('split.txt', 'P\n##negative##\nN')
        self.shared.prompt_styles.styles['selected'] = files.core.PromptStyle(
            'selected', '#file<split>', 'old')
        p = self.prompt('plain', 'negative', selected=['selected'])
        self.script.before_process(p)
        style = self.shared.prompt_styles.styles['selected']
        self.assertEqual(style.prompt, 'P')
        self.assertEqual(style.negative_prompt, 'old, N')

    def test_adetailer_pairs_are_separate_and_missing_partner_is_created(self):
        self.write_prompt('split.txt', 'P\n##negative##\nN')
        extra = {'ADetailer prompt': '#file<split>',
                 'ADetailer negative prompt': 'old',
                 'ADetailer prompt 2nd': '#file<split>',
                 'ADetailer negative prompt 3': '#file<split>'}
        p = self.prompt('main', 'main negative', extra=extra)
        self.script.process(p)
        self.assertEqual(extra['ADetailer prompt'], 'P')
        self.assertEqual(extra['ADetailer negative prompt'], 'old, N')
        self.assertEqual(extra['ADetailer prompt 2nd'], 'P')
        self.assertEqual(extra['ADetailer negative prompt 2nd'], 'N')
        self.assertEqual(extra['ADetailer negative prompt 3'], 'P\nN')
        self.assertNotIn('ADetailer prompt 3', extra)
        self.assertEqual((p.prompt, p.negative_prompt), ('main', 'main negative'))

    def test_adetailer_list_receiver_broadcast_and_opposite_only_file(self):
        self.write_prompt('positive.txt', '##positive##\nP')
        extra = {'ADetailer negative prompt 4th': ['#file<positive>', 'keep'],
                 'ADetailer prompt 4th': 'old'}
        p = self.prompt(extra=extra)
        self.script.process(p)
        self.assertEqual(extra['ADetailer prompt 4th'], ['old, P', 'old'])
        self.assertEqual(extra['ADetailer negative prompt 4th'], ['', 'keep'])

    def test_cross_field_limit_failure_does_not_install_working_styles(self):
        self.write_prompt('negative.txt', '##negative##\n' + 'N' * 40)
        p = self.prompt('#file<negative>', 'old ' * 10)
        original = self.shared.prompt_styles.styles
        with mock.patch.object(self.module, 'MAX_PROMPT_LENGTH', 70):
            with self.assertRaises(ValueError):
                self.script.before_process(p)
        self.assertIs(self.shared.prompt_styles.styles, original)
        self.assertNotIn(self.module.METADATA_KEY, p.extra_generation_params)
        self.assertEqual(p.prompt, '#file<negative>')
        self.assertEqual(p.negative_prompt, 'old ' * 10)

    def test_metadata_restores_original_both_fields_after_cross_field_append(self):
        self.write_prompt('negative.txt', '##negative##\nN')
        p = self.prompt(' P #file<negative> ', ' old\nnegative ')
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        callback = p.extra_generation_params[self.module.METADATA_KEY]
        payload = callback(p=p, index=0, all_prompts=[p.prompt], use_main_prompt=True,
                           iteration=0, position_in_batch=0)
        parsed = {self.module.METADATA_KEY: payload}
        self.module._on_infotext_pasted('', parsed)
        self.assertEqual(json.loads(payload), {'prompt': ' P #file<negative> ',
                         'negative prompt': ' old\nnegative ', 'styles': []})
        self.assertEqual(parsed['Prompt'], ' P #file<negative> ')
        self.assertEqual(parsed['Negative prompt'], ' old\nnegative ')

    def test_marker_line_endings_and_utf8_bom_preserve_body_line_endings(self):
        for newline in ('\r', '\r\n', '\n'):
            for bom in (b'', b'\xef\xbb\xbf'):
                with self.subTest(newline=repr(newline), bom=bom):
                    source = newline.join(('##positive##', 'P1', 'P2',
                                           '##negative##', 'N1', 'N2'))
                    self.write_prompt('endings.txt', bom + source.encode('utf-8'))
                    p = self.prompt('#file<endings>')
                    self.script.before_process(p)
                    self.assertEqual(p.prompt, newline.join(('P1', 'P2')))
                    self.assertEqual(p.negative_prompt, newline.join(('N1', 'N2')))
                    self.script.postprocess(p)

    def test_marker_free_child_keeps_parent_current_destination(self):
        self.write_prompt('child.txt', 'child #include<base>')
        self.write_prompt('parent.txt', 'P\n##negative##\nN #file<child> tail')
        p = self.prompt('#file<parent>')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'P')
        self.assertEqual(p.negative_prompt, 'N child 基本ネガ tail')

    def test_grandchild_final_destination_propagates_through_both_parents(self):
        self.write_prompt('grandchild.txt', '##positive##\nG')
        self.write_prompt('child.txt', 'C #file<grandchild> child tail')
        self.write_prompt('parent.txt', '##negative##\nN #file<child> parent tail')
        p = self.prompt('#file<parent> main tail', 'old')
        self.script.before_process(p)
        self.assertEqual(p.prompt, 'G child tail parent tail main tail')
        self.assertEqual(p.negative_prompt, 'old, N C')

    def test_alias_cycle_after_destination_switch_stops_before_depth_limit(self):
        target = self.write_prompt('target.txt', '##negative##\nN #file<alias> tail')
        alias = self.prompts / 'alias.txt'
        try:
            alias.symlink_to(target)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f'この環境ではシンボリックリンクを作成できません: {exc}')
        p = self.prompt('#file<target>')
        output = io.StringIO()
        with mock.patch.object(self.module, 'MAX_INCLUDE_DEPTH', 1), contextlib.redirect_stdout(output):
            self.script.before_process(p)
        self.assertEqual(p.prompt, '')
        self.assertEqual(p.negative_prompt, 'N  tail')
        self.assertIn('Circular include', output.getvalue())
        self.assertNotIn('depth limit', output.getvalue())

    def test_metadata_only_activates_changed_image_after_scalar_receiver_broadcast(self):
        self.write_prompt('negative.txt', '##negative##\nN')
        originals = ['plain0', 'P #file<negative>', 'plain2']
        p = self.prompt(list(originals), 'old')
        p.batch_size = 3
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        callback = p.extra_generation_params[self.module.METADATA_KEY]
        for index in (0, 1, 2):
            with self.subTest(index=index):
                payload = callback(p=p, index=index, all_prompts=p.prompt, use_main_prompt=False,
                                   iteration=0, position_in_batch=index)
                if index != 1:
                    self.assertIsNone(payload)
                    continue
                self.assertEqual(json.loads(payload), {'prompt': originals[index],
                                 'negative prompt': 'old', 'styles': []})
        self.assertEqual(p.negative_prompt, ['old', 'old, N', 'old'])

    def test_adetailer_style_reference_keeps_cross_text_and_before_process_rules(self):
        self.write_prompt('split.txt', 'bad red\n##negative##\nbad red')
        self.shared.prompt_styles.styles['bridge'] = files.core.PromptStyle(
            'bridge', '#file<split>', 'ordinary negative')
        extra = {'ADetailer prompt 2nd': '#include<bridge>',
                 'ADetailer negative prompt 2nd': 'old'}
        p = self.prompt('#delete<bad>#replace<red|pink>',
                        '#delete<bad>#replace<red|pink>', extra=extra)
        self.script.before_process(p)
        self.script.process(p)
        self.assertEqual(extra['ADetailer prompt 2nd'], 'pink')
        self.assertEqual(extra['ADetailer negative prompt 2nd'], 'old, pink')

    def test_adetailer_ignores_non_text_partner_without_overwriting_it(self):
        self.write_prompt('split.txt', 'P\n##negative##\nN')
        for value in (None, 7, {'other': 'data'}):
            with self.subTest(value=value):
                extra = {'ADetailer prompt': '#file<split>', 'ADetailer negative prompt': value}
                p = self.prompt(extra=extra)
                self.script.process(p)
                self.assertEqual(extra['ADetailer prompt'], 'P')
                self.assertIs(extra['ADetailer negative prompt'], value)

    def test_postprocess_and_close_restore_same_dictionary_after_cross_expansion(self):
        self.write_prompt('negative.txt', '##negative##\nN')
        original = self.shared.prompt_styles.styles
        for finish in ('postprocess', 'close'):
            with self.subTest(finish=finish):
                p = self.prompt('#file<negative>', 'old')
                self.script.before_process(p)
                self.assertIsNot(self.shared.prompt_styles.styles, original)
                self.assertEqual(p.negative_prompt, 'old, N')
                if finish == 'close':
                    p.close()
                    self.assertTrue(p.closed)
                else:
                    self.script.postprocess(p)
                self.assertIs(self.shared.prompt_styles.styles, original)

    def test_different_list_lengths_with_cross_output_fail_atomically(self):
        self.write_prompt('negative.txt', '##negative##\nN')
        for positive, negative in ((['plain', '#file<negative>'], ['old']),
                                   (['#file<negative>'], ['old0', 'old1'])):
            with self.subTest(positive=positive, negative=negative):
                p = self.prompt(list(positive), list(negative))
                original = self.shared.prompt_styles.styles
                with self.assertRaises(ValueError):
                    self.script.before_process(p)
                self.assertIs(self.shared.prompt_styles.styles, original)
                self.assertEqual(p.prompt, positive)
                self.assertEqual(p.negative_prompt, negative)
                self.assertNotIn(self.module.METADATA_KEY, p.extra_generation_params)

    def test_different_list_lengths_without_cross_output_keep_legacy_behavior(self):
        self.write_prompt('plain.txt', 'text')
        p = self.prompt(['#file<plain>', 'second'], ['negative'])
        self.script.before_process(p)
        self.assertEqual(p.prompt, ['text', 'second'])
        self.assertEqual(p.negative_prompt, ['negative'])

    def test_style_cross_field_length_limit_keeps_other_field_and_main_generation(self):
        self.write_prompt('negative.txt', 'P\n##negative##\n' + 'N' * 60)
        for selected in ([], ['oversize']):
            with self.subTest(selected=selected):
                self.shared.prompt_styles.styles['oversize'] = files.core.PromptStyle(
                    'oversize', '#file<negative>', 'x' * 60)
                p = self.prompt('plain', 'negative', selected=selected)
                output = io.StringIO()
                with mock.patch.object(self.module, 'MAX_PROMPT_LENGTH', 100), \
                        contextlib.redirect_stdout(output):
                    self.script.before_process(p)
                self.assertEqual((p.prompt, p.negative_prompt), ('plain', 'negative'))
                style = self.shared.prompt_styles.styles['oversize']
                self.assertEqual(style.prompt, 'P')
                self.assertEqual(style.negative_prompt, '')
                self.assertIn('length limit', output.getvalue())
                self.script.postprocess(p)


if __name__ == '__main__':
    unittest.main()
