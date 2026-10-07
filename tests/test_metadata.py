"""infotext に保存する IncludeStyle metadata の回帰テスト。"""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_includestyle as core


class IncludeStyleMetadataTests(unittest.TestCase):
    """既存ホストスタブを使い metadata の入出力を確認する。"""

    setUp = core.IncludeStyleTests.setUp
    tearDown = core.IncludeStyleTests.tearDown

    def prompt(self, positive="", negative="", selected=None, extra=None):
        return core.IncludeStyleTests.prompt(self, positive, negative, selected, extra)

    def _capture(self, processing, **locals_):
        params = processing.extra_generation_params
        callback = params.get(self.module.METADATA_KEY)
        if callable(callback):
            value = callback(**locals_)
            if value is not None:
                return json.loads(value)
        return {}

    def test_positive_negative_and_both_restore_original_values(self):
        cases = [
            ("#include<base>", "plain"),
            ("plain", "#include<base>"),
            ("#include<base>", "#include<base>"),
            ("#inc < base >", "$inc<base>"),
        ]
        for positive, negative in cases:
            with self.subTest(positive=positive, negative=negative):
                p = self.prompt(positive, negative)
                self.script.before_process(p)
                self.script.postprocess_batch(p, [], batch_number=0)
                got = self._capture(p, p=p, index=0, all_prompts=[p.prompt], use_main_prompt=True,
                                    iteration=0, position_in_batch=0)
                self.assertEqual(got, {
                    "prompt": positive, "negative prompt": negative, "styles": [],
                })
                parsed = {self.module.METADATA_KEY: json.dumps(got)}
                self.module._on_infotext_pasted('', parsed)
                self.assertEqual(parsed['Prompt'], positive)
                self.assertEqual(parsed['Negative prompt'], negative)
                self.assertEqual(parsed['Styles array'], [])

    def test_selected_style_commands_trigger_metadata_even_for_empty_original(self):
        self.shared.prompt_styles.styles["outer"] = core.PromptStyle("outer", "#include<inner>", "")
        self.shared.prompt_styles.styles["inner"] = core.PromptStyle("inner", "#delete<x>", "")
        p = self.prompt("", selected=["outer", "unused"])
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        payload = self._capture(p, p=p, index=0, all_prompts=[""], use_main_prompt=True,
                                iteration=0, position_in_batch=0)
        self.assertEqual(payload, {"prompt": "", "negative prompt": "", "styles": ["outer", "unused"]})
        self.assertEqual(set(p.extra_generation_params), {self.module.METADATA_KEY})

    def test_unused_selected_style_command_does_not_trigger_metadata(self):
        self.shared.prompt_styles.styles["unused"] = core.PromptStyle("unused", "#delete<x>", "")
        p = self.prompt("plain", "", selected=[])
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        self.assertEqual(self._capture(p, p=p, index=0, all_prompts=[p.prompt], use_main_prompt=True,
                                       iteration=0, position_in_batch=0), {})

    def test_adetailer_only_expansion_does_not_activate_main_metadata(self):
        p = self.prompt("plain", "", extra={"ADetailer prompt": "#include<base>"})
        self.script.before_process(p)
        self.script.process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        self.assertEqual(self._capture(p, p=p, index=0, all_prompts=[p.prompt], use_main_prompt=True,
                                       iteration=0, position_in_batch=0), {})

    def test_empty_and_nonmatching_directives_are_still_recorded(self):
        for marker in ("#", "$", "%"):
            with self.subTest(marker=marker):
                p = self.prompt(f"{marker}delete<> {marker}replace<|add> {marker}replace<missing|x>")
                self.script.before_process(p)
                self.script.postprocess_batch(p, [], batch_number=0)
                got = self._capture(p, p=p, index=0, all_prompts=[p.prompt], use_main_prompt=True,
                                    iteration=0, position_in_batch=0)
                self.assertEqual(got["prompt"], f"{marker}delete<> {marker}replace<|add> {marker}replace<missing|x>")

    def test_batch_callback_uses_requested_local_or_global_prompt_and_grid_first_item(self):
        originals = ["#delete<x> first", "plain", "#delete<y> third", "plain", "#delete<z> fifth", "plain"]
        p = self.prompt(originals, "")
        p.prompts = originals[3:]
        p.all_prompts = originals
        p.batch_size = 3
        p.iteration = 1
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        callback = p.extra_generation_params[self.module.METADATA_KEY]
        self.assertEqual(json.loads(callback(p=p, index=4, all_prompts=p.all_prompts, use_main_prompt=True,
                                             iteration=0, position_in_batch=0))["prompt"], "#delete<x> first")
        self.assertEqual(json.loads(callback(p=p, index=1, all_prompts=["local0", "local1", "local2"],
                                             use_main_prompt=False, iteration=1, position_in_batch=1))["prompt"], "#delete<z> fifth")
        self.assertEqual(json.loads(callback(p=p, index=4, all_prompts=p.all_prompts, use_main_prompt=False,
                                             iteration=1, position_in_batch=1))["prompt"], "#delete<z> fifth")
        self.assertIsNone(callback(p=p, index=5, all_prompts=p.all_prompts, use_main_prompt=False,
                                   iteration=1, position_in_batch=2))

    def test_metadata_captures_after_cross_field_rules_change_other_prompt(self):
        self.shared.prompt_styles.styles["cross"] = core.PromptStyle("cross", "", "#replace<cat|dog>")
        p = self.prompt("#include<cross>", "cat")
        self.script.before_process(p)
        self.assertEqual(p.negative_prompt, "dog")
        self.script.postprocess_batch(p, [], batch_number=0)
        payload = self._capture(p, p=p, index=0, all_prompts=[p.prompt], use_main_prompt=True,
                                iteration=0, position_in_batch=0)
        self.assertEqual(payload["prompt"], "#include<cross>")
        self.assertEqual(payload["negative prompt"], "cat")

    def test_restore_japanese_quotes_whitespace_and_newlines(self):
        original = '  日本語 "引用"\n  終わり  #include<base>'
        p = self.prompt(original, "changed")
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        payload = self._capture(p, p=p, index=0, all_prompts=[p.prompt], use_main_prompt=True,
                                iteration=0, position_in_batch=0)
        parsed_params = {
            "Prompt": "transformed",
            "Negative prompt": "keep negative",
            self.module.METADATA_KEY: json.dumps(payload, ensure_ascii=False),
        }
        self.module._on_infotext_pasted("test infotext", parsed_params)
        self.assertEqual(parsed_params["Prompt"], original)
        self.assertEqual(parsed_params["Negative prompt"], "changed")
        self.assertEqual(parsed_params["Styles array"], [])

    def test_malformed_metadata_is_ignored_and_stale_metadata_is_removed(self):
        valid = {"prompt": "raw", "negative prompt": "raw negative", "styles": ["base"]}
        malformed_values = ["{", "[]", '{"text": 2}', "null", None, 123]
        for field in valid:
            missing = dict(valid)
            del missing[field]
            malformed_values.append(json.dumps(missing))
        for field, wrong in (("prompt", 2), ("negative prompt", None),
                             ("styles", "base"), ("styles", [2])):
            malformed_values.append(json.dumps({**valid, field: wrong}))
        for malformed in malformed_values:
            with self.subTest(malformed=malformed):
                parsed_params = {"Prompt": "keep", "Negative prompt": "keep negative",
                    "Styles array": ["keep style"], self.module.METADATA_KEY: malformed,
                }
                previous = copy.deepcopy(parsed_params)
                self.module._on_infotext_pasted("test infotext", parsed_params)
                self.assertEqual(parsed_params, previous)
        p = self.prompt("clean")
        p.extra_generation_params[self.module.METADATA_KEY] = "old"
        self.script.before_process(p)
        self.assertNotIn(self.module.METADATA_KEY, p.extra_generation_params)

    def test_expansion_failure_does_not_add_metadata(self):
        p = self.prompt("#replace<a|replacement> a")
        self.module.MAX_PROMPT_LENGTH = 1
        with self.assertRaises(ValueError):
            self.script.before_process(p)
        self.assertNotIn(self.module.METADATA_KEY, p.extra_generation_params)

    def test_adetailer_resume_copy_is_isolated_and_keeps_parent_original(self):
        parent = self.prompt("parent #include<base>")
        self.script.before_process(parent)
        self.script.postprocess_batch(parent, [], batch_number=0)
        parent_callback = parent.extra_generation_params[self.module.METADATA_KEY]
        copied = copy.copy(parent)
        copied.closed = False
        self.script.before_process(copied)
        self.script.postprocess_batch(copied, [], batch_number=0)
        self.assertIsNot(copied.extra_generation_params, parent.extra_generation_params)
        self.assertIs(parent.extra_generation_params.get(self.module.METADATA_KEY), parent_callback)
        self.assertIsNot(copied.extra_generation_params[self.module.METADATA_KEY],
                         parent.extra_generation_params.get(self.module.METADATA_KEY))
        parent_payload = parent_callback(p=parent, index=0, all_prompts=[parent.prompt], use_main_prompt=True,
                                         iteration=0, position_in_batch=0)
        copied_payload = copied.extra_generation_params[self.module.METADATA_KEY](
            p=copied, index=0, all_prompts=[copied.prompt], use_main_prompt=True,
            iteration=0, position_in_batch=0)
        self.assertEqual(parent_payload, copied_payload)

    def test_independent_child_keeps_its_own_original(self):
        parent = self.prompt("parent #include<base>")
        child = self.prompt("child #include<base>")
        self.script.before_process(parent)
        self.script.before_process(child)
        self.script.postprocess_batch(child, [], batch_number=0)
        payload = self._capture(child, p=child, index=0, all_prompts=[child.prompt], use_main_prompt=True,
                                iteration=0, position_in_batch=0)
        self.assertEqual(payload["prompt"], "child #include<base>")

    def test_callback_is_registered_for_both_ui_modes(self):
        self.assertEqual(self.infotext_callbacks, [self.module._on_infotext_pasted])

    def test_list_rules_also_record_changed_elements_without_commands(self):
        original = ['#replace<cat|dog>', 'cat', 'unaffected']
        p = self.prompt(original)
        p.batch_size = 3
        p.all_prompts = original
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        second = self._capture(p, all_prompts=p.all_prompts, index=1)
        self.assertEqual(second['prompt'], 'cat')
        self.assertEqual(self._capture(p, all_prompts=p.all_prompts, index=2), {})
        # 呼び出し元がリストを変更しても、保存した原本は変わらない
        original[1] = 'mutated'
        self.assertEqual(self._capture(p, all_prompts=p.all_prompts, index=1)['prompt'], 'cat')

    def test_file_commands_record_both_raw_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'sample.txt').write_text('#include<base>', encoding='utf-8')
            for command in ('includefile', 'file'):
                with self.subTest(command=command):
                    positive, negative = f'${command}<sample>', f'%{command}<sample.txt>'
                    p = self.prompt(positive, negative)
                    with mock.patch.object(self.module, 'PROMPTS_DIRECTORY', Path(folder)):
                        self.script.before_process(p)
                    self.script.postprocess_batch(p, [], batch_number=0)
                    payload = self._capture(p, index=0, use_main_prompt=True)
                    self.assertEqual(payload['prompt'], positive)
                    self.assertEqual(payload['negative prompt'], negative)
                    parsed = {self.module.METADATA_KEY: json.dumps(payload)}
                    self.module._on_infotext_pasted('', parsed)
                    self.assertEqual(parsed['Prompt'], positive)
                    self.assertEqual(parsed['Negative prompt'], negative)
                    self.script.postprocess(p)

    def test_failed_reuse_cannot_publish_previous_generation_metadata(self):
        p = self.prompt('#include<base>')
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        self.script.postprocess(p)
        p.prompt = 'too long'
        with mock.patch.object(self.module, 'MAX_PROMPT_LENGTH', 1), self.assertRaises(ValueError):
            self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        self.assertEqual(self._capture(p, index=0), {})

    def test_changed_copy_uses_new_original_without_overwriting_parent(self):
        parent = self.prompt('#include<base>')
        self.script.before_process(parent)
        self.script.postprocess_batch(parent, [], batch_number=0)
        child = copy.copy(parent)
        child.prompt = 'new #delete<x>'
        self.script.before_process(child)
        self.script.postprocess_batch(child, [], batch_number=0)
        self.assertEqual(self._capture(child, index=0)['prompt'], 'new #delete<x>')
        self.assertEqual(self._capture(parent, index=0)['prompt'], '#include<base>')

    def test_restore_replaces_inferred_styles_and_preserves_other_generation_parameters(self):
        self.shared.prompt_styles.styles['chosen'] = core.PromptStyle('chosen', '#include<base>', 'bad')
        for selected in ([], ['chosen']):
            with self.subTest(selected=selected):
                params = {
                    'Prompt': 'expanded', 'Negative prompt': 'safe, bad',
                    'Styles array': ['inferred'],
                    self.module.METADATA_KEY: json.dumps({
                        'prompt': '#include<base>', 'negative prompt': 'safe', 'styles': selected,
                    }),
                    'Seed': '123',
                }
                self.module._on_infotext_pasted('', params)
                self.assertEqual(params['Prompt'], '#include<base>')
                self.assertEqual(params['Negative prompt'], 'safe')
                self.assertEqual(params['Styles array'], selected)
                self.assertEqual(params['Seed'], '123')

    def test_only_requested_metadata_keys_are_added(self):
        p = self.prompt('#include<base>', '#include<base>', extra={'Other extension': 'keep'})
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        self.assertEqual(set(p.extra_generation_params), {
            self.module.METADATA_KEY, 'Other extension',
        })
        self.assertEqual(p.extra_generation_params['Other extension'], 'keep')

    def test_negative_list_activates_only_its_image_and_preserves_both_originals(self):
        positive = ['first', 'second', 'third']
        negative = ['plain', '#delete<x> x', 'plain']
        p = self.prompt(positive, negative)
        p.batch_size = 3
        p.all_prompts = positive
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        self.assertEqual(self._capture(p, index=0), {})
        self.assertEqual(self._capture(p, index=1), {
            'prompt': 'second', 'negative prompt': '#delete<x> x', 'styles': [],
        })
        self.assertEqual(self._capture(p, index=2), {})

    def test_selected_styles_snapshot_keeps_names_and_order(self):
        selected = ['base', '日本語 "引用"', 'base']
        p = self.prompt('#include<base>', selected=selected)
        self.script.before_process(p)
        selected[:] = ['mutated']
        self.script.postprocess_batch(p, [], batch_number=0)
        payload = self._capture(p, index=0)
        self.assertEqual(payload['styles'], ['base', '日本語 "引用"', 'base'])
        params = {self.module.METADATA_KEY: json.dumps(payload)}
        self.module._on_infotext_pasted('', params)
        self.assertEqual(params['Styles array'], payload['styles'])

    def test_metadata_is_published_only_after_generated_batch(self):
        p = self.prompt('#include<base>')
        self.script.before_process(p)
        self.assertNotIn(self.module.METADATA_KEY, p.extra_generation_params)
        self.script.postprocess_batch(p, [], batch_number=0)
        self.assertIn(self.module.METADATA_KEY, p.extra_generation_params)

    def test_absent_metadata_keeps_parsed_fields(self):
        params = {'Prompt': 'plain', 'Negative prompt': 'bad', 'Styles array': ['base'], 'Seed': '123'}
        original = copy.deepcopy(params)
        self.module._on_infotext_pasted('', params)
        self.assertEqual(params, original)


if __name__ == "__main__":
    unittest.main()

