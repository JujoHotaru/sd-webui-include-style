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
        captured = {}
        for key, field in (
            (self.module.ORIGINAL_PROMPT_KEY, "Prompt"),
            (self.module.ORIGINAL_NEGATIVE_KEY, "Negative prompt"),
        ):
            callback = params.get(key)
            if callable(callback):
                value = callback(**locals_)
                if value is not None:
                    captured[field] = value
        return captured

    def test_positive_negative_and_both_restore_original_values(self):
        cases = [
            ("#include<base>", "plain", {
                "Prompt": json.dumps({"text": "#include<base>"}, ensure_ascii=False),
            }),
            ("plain", "#include<base>", {
                "Negative prompt": json.dumps({"text": "#include<base>"}, ensure_ascii=False),
            }),
            ("#include<base>", "#include<base>", {
                "Prompt": json.dumps({"text": "#include<base>"}, ensure_ascii=False),
                "Negative prompt": json.dumps({"text": "#include<base>"}, ensure_ascii=False),
            }),
        ]
        for positive, negative, expected in cases:
            with self.subTest(positive=positive, negative=negative):
                p = self.prompt(positive, negative)
                self.script.before_process(p)
                self.script.postprocess_batch(p, [], batch_number=0)
                got = self._capture(p, p=p, index=0, all_prompts=[p.prompt], use_main_prompt=True,
                                    iteration=0, position_in_batch=0)
                self.assertEqual(got, expected)

    def test_selected_style_commands_trigger_metadata_even_for_empty_original(self):
        self.shared.prompt_styles.styles["outer"] = core.PromptStyle("outer", "#include<inner>", "")
        self.shared.prompt_styles.styles["inner"] = core.PromptStyle("inner", "#delete<x>", "")
        p = self.prompt("", selected=["outer", "unused"])
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        payload = self._capture(p, p=p, index=0, all_prompts=[""], use_main_prompt=True,
                                iteration=0, position_in_batch=0)
        self.assertEqual(payload["Prompt"], json.dumps({"text": ""}, ensure_ascii=False))
        self.assertEqual(set(p.extra_generation_params), {self.module.ORIGINAL_PROMPT_KEY})

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
                self.assertEqual(json.loads(got["Prompt"])["text"], f"{marker}delete<> {marker}replace<|add> {marker}replace<missing|x>")

    def test_batch_callback_uses_requested_local_or_global_prompt_and_grid_first_item(self):
        originals = ["#delete<x> first", "plain", "#delete<y> third", "plain", "#delete<z> fifth", "plain"]
        p = self.prompt(originals, "")
        p.prompts = originals[3:]
        p.all_prompts = originals
        p.batch_size = 3
        p.iteration = 1
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        callback = p.extra_generation_params[self.module.ORIGINAL_PROMPT_KEY]
        self.assertEqual(json.loads(callback(p=p, index=4, all_prompts=p.all_prompts, use_main_prompt=True,
                                             iteration=0, position_in_batch=0))["text"], "#delete<x> first")
        self.assertEqual(json.loads(callback(p=p, index=1, all_prompts=["local0", "local1", "local2"],
                                             use_main_prompt=False, iteration=1, position_in_batch=1))["text"], "#delete<z> fifth")
        self.assertEqual(json.loads(callback(p=p, index=4, all_prompts=p.all_prompts, use_main_prompt=False,
                                             iteration=1, position_in_batch=1))["text"], "#delete<z> fifth")
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
        self.assertEqual(json.loads(payload["Prompt"])["text"], "#include<cross>")
        self.assertEqual(json.loads(payload["Negative prompt"])["text"], "cat")

    def test_restore_japanese_quotes_whitespace_and_newlines_and_partial_keys(self):
        original = '  日本語 "引用"\n  終わり  #include<base>'
        p = self.prompt(original, "changed")
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        payload = self._capture(p, p=p, index=0, all_prompts=[p.prompt], use_main_prompt=True,
                                iteration=0, position_in_batch=0)
        parsed_params = {
            "Prompt": "transformed",
            "Negative prompt": "keep negative",
            self.module.ORIGINAL_PROMPT_KEY: payload["Prompt"],
        }
        self.module._on_infotext_pasted("test infotext", parsed_params)
        self.assertEqual(parsed_params["Prompt"], original)
        self.assertEqual(parsed_params["Negative prompt"], "keep negative")
        self.assertNotIn("Styles array", parsed_params)

    def test_malformed_metadata_is_ignored_and_stale_metadata_is_removed(self):
        for malformed in ("{", "[]", "{\"text\": 2}", "null"):
            with self.subTest(malformed=malformed):
                parsed_params = {"Prompt": "keep",
                    self.module.ORIGINAL_PROMPT_KEY: malformed,
                }
                self.module._on_infotext_pasted("test infotext", parsed_params)
                self.assertEqual(parsed_params["Prompt"], "keep")
        p = self.prompt("clean")
        for key in (self.module.ORIGINAL_PROMPT_KEY, self.module.ORIGINAL_NEGATIVE_KEY):
            p.extra_generation_params[key] = "old"
        self.script.before_process(p)
        self.assertFalse(set(p.extra_generation_params).intersection({
            self.module.ORIGINAL_PROMPT_KEY, self.module.ORIGINAL_NEGATIVE_KEY,
        }))

    def test_expansion_failure_does_not_add_metadata(self):
        p = self.prompt("#replace<a|replacement> a")
        self.module.MAX_PROMPT_LENGTH = 1
        with self.assertRaises(ValueError):
            self.script.before_process(p)
        self.assertFalse(any("original" in key.lower() for key in p.extra_generation_params))

    def test_adetailer_resume_copy_is_isolated_and_keeps_parent_original(self):
        parent = self.prompt("parent #include<base>")
        self.script.before_process(parent)
        self.script.postprocess_batch(parent, [], batch_number=0)
        parent_callback = parent.extra_generation_params[self.module.ORIGINAL_PROMPT_KEY]
        copied = copy.copy(parent)
        copied.closed = False
        self.script.before_process(copied)
        self.script.postprocess_batch(copied, [], batch_number=0)
        self.assertIsNot(copied.extra_generation_params, parent.extra_generation_params)
        self.assertIs(parent.extra_generation_params.get(self.module.ORIGINAL_PROMPT_KEY), parent_callback)
        self.assertIsNot(copied.extra_generation_params[self.module.ORIGINAL_PROMPT_KEY],
                         parent.extra_generation_params.get(self.module.ORIGINAL_PROMPT_KEY))
        parent_payload = parent_callback(p=parent, index=0, all_prompts=[parent.prompt], use_main_prompt=True,
                                         iteration=0, position_in_batch=0)
        copied_payload = copied.extra_generation_params[self.module.ORIGINAL_PROMPT_KEY](
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
        self.assertEqual(payload["Prompt"], json.dumps({"text": "child #include<base>"}, ensure_ascii=False))

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
        self.assertEqual(json.loads(second['Prompt'])['text'], 'cat')
        self.assertEqual(self._capture(p, all_prompts=p.all_prompts, index=2), {})
        # 呼び出し元がリストを変更しても、保存した原本は変わらない
        original[1] = 'mutated'
        self.assertEqual(json.loads(self._capture(p, all_prompts=p.all_prompts, index=1)['Prompt'])['text'], 'cat')

    def test_file_commands_record_both_raw_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'sample.txt').write_text('#include<base>', encoding='utf-8')
            p = self.prompt('$includefile<sample>', '%includefile<sample.txt>')
            with mock.patch.object(self.module, 'PROMPTS_DIRECTORY', Path(folder)):
                self.script.before_process(p)
            self.script.postprocess_batch(p, [], batch_number=0)
            payload = self._capture(p, index=0, use_main_prompt=True)
            self.assertEqual(json.loads(payload['Prompt'])['text'], '$includefile<sample>')
            self.assertEqual(json.loads(payload['Negative prompt'])['text'], '%includefile<sample.txt>')

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
        self.assertEqual(json.loads(self._capture(child, index=0)['Prompt'])['text'], 'new #delete<x>')
        self.assertEqual(json.loads(self._capture(parent, index=0)['Prompt'])['text'], '#include<base>')

    def test_restore_does_not_change_styles_or_other_generation_parameters(self):
        self.shared.prompt_styles.styles['chosen'] = core.PromptStyle('chosen', '#include<base>', 'bad')
        for inferred in ([], ['chosen']):
            with self.subTest(inferred=inferred):
                params = {
                    'Prompt': 'expanded', 'Negative prompt': 'safe' if inferred else 'safe, bad',
                    'Styles array': inferred,
                    self.module.ORIGINAL_PROMPT_KEY: json.dumps({'text': '#include<base>'}),
                    'Seed': '123',
                }
                self.module._on_infotext_pasted('', params)
                self.assertEqual(params['Prompt'], '#include<base>')
                self.assertEqual(params['Negative prompt'], 'safe' if inferred else 'safe, bad')
                self.assertEqual(params['Styles array'], inferred)
                self.assertEqual(params['Seed'], '123')

    def test_only_requested_metadata_keys_are_added(self):
        p = self.prompt('#include<base>', '#include<base>', extra={'Other extension': 'keep'})
        self.script.before_process(p)
        self.script.postprocess_batch(p, [], batch_number=0)
        self.assertEqual(set(p.extra_generation_params), {
            self.module.ORIGINAL_PROMPT_KEY, self.module.ORIGINAL_NEGATIVE_KEY, 'Other extension',
        })
        self.assertEqual(p.extra_generation_params['Other extension'], 'keep')


if __name__ == "__main__":
    unittest.main()

