"""IncludeStyle のホスト非依存な回帰テスト。"""

import contextlib
import importlib.util
import io
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "includestyle.py"


class PromptStyle:
    def __init__(self, name, prompt, negative_prompt, path=None):
        self.name = name
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.path = path


class PromptStyles:
    def __init__(self, styles):
        self.styles = styles


class HostScript:
    pass


class HostProcessing:
    def __init__(self, prompt, negative_prompt, styles, extra_generation_params):
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.styles = styles
        self.extra_generation_params = extra_generation_params
        self.closed = False

    def close(self):
        self.closed = True


class IncludeStyleTests(unittest.TestCase):
    def setUp(self):
        self.styles = {
            "base": PromptStyle("base", "基本", "基本ネガ"),
        }
        shared = types.SimpleNamespace(prompt_styles=PromptStyles(self.styles))
        scripts = types.SimpleNamespace(Script=HostScript, AlwaysVisible=object())
        host = types.ModuleType("modules")
        host.shared = shared
        host.styles = types.SimpleNamespace(PromptStyle=PromptStyle)
        host.scripts = scripts
        self.infotext_callbacks = []
        host.script_callbacks = types.SimpleNamespace(on_infotext_pasted=self.infotext_callbacks.append)
        self.module_patch = mock.patch.dict(sys.modules, {"modules": host})
        self.module_patch.start()
        spec = importlib.util.spec_from_file_location("includestyle_test_target", SOURCE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.shared = shared
        self.script = self.module.IncludeStyleScript()

    def tearDown(self):
        for p in reversed(getattr(self, "processing_objects", [])):
            self.script.postprocess(p)
        self.module_patch.stop()

    def prompt(self, positive="", negative="", selected=None, extra=None):
        p = HostProcessing(positive, negative, list(selected or []), extra or {})
        self.processing_objects = getattr(self, "processing_objects", [])
        self.processing_objects.append(p)
        return p

    def test_script_registration_has_no_ui(self):
        self.assertEqual(self.script.title(), "IncludeStyle")
        self.assertIs(self.script.show(False), self.module.scripts.AlwaysVisible)
        self.assertEqual(self.script.ui(False), ())

    def test_include_markers_whitespace_japanese_and_nested_forward_negative(self):
        self.shared.prompt_styles.styles.update({
            "後方": PromptStyle("後方", "後ろ", "後ろネガ"),
            "前方": PromptStyle("前方", "A #include < 後方 > Z", "N $include<後方>"),
            "日本語": PromptStyle("日本語", "#include<前方>", "%include < 後方 >"),
        })
        p = self.prompt("x #include < 日本語 > y", "#include<日本語>")
        self.script.before_process(p)
        self.assertEqual(p.prompt, "x A 後ろ Z y")
        self.assertEqual(p.negative_prompt, "後ろネガ")
        self.assertEqual(self.shared.prompt_styles.styles["日本語"].negative_prompt, "後ろネガ")

    def test_missing_include_warns_and_becomes_empty(self):
        p = self.prompt("left #include<存在しない> right")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.script.before_process(p)
        self.assertEqual(p.prompt, "left  right")
        self.assertIn("存在しない", output.getvalue())

    def test_include_trims_edges_and_preserves_internal_and_surrounding_whitespace(self):
        self.shared.prompt_styles.styles["spacing"] = PromptStyle(
            "spacing", " \t\r\nbody \t\r\nend\u3000", "\u3000bad\t \nbad end\r\n",
        )
        p = self.prompt(" \t[#include<spacing>]\n", "[$include<spacing>]",
                        extra={"ADetailer prompt": "%include<spacing>",
                               "ADetailer negative prompt": "#include<spacing>"})
        self.script.before_process(p)
        self.script.process(p)
        self.assertEqual(p.prompt, " \t[body \t\r\nend]\n")
        self.assertEqual(p.negative_prompt, "[bad\t \nbad end]")
        self.assertEqual(p.extra_generation_params["ADetailer prompt"], "body \t\r\nend")
        self.assertEqual(p.extra_generation_params["ADetailer negative prompt"], "bad\t \nbad end")

    def test_selected_styles_remain_selected_and_shared_styles_restore(self):
        original = self.shared.prompt_styles.styles.copy()
        original_obj = original["base"]
        p = self.prompt("", selected=["選択"])
        self.shared.prompt_styles.styles["選択"] = PromptStyle("選択", "red", "bad")
        original = self.shared.prompt_styles.styles.copy()
        p.styles = ["選択"]
        self.script.before_process(p)
        self.assertEqual(p.styles, ["選択"])
        self.assertEqual(self.shared.prompt_styles.styles["選択"].prompt, "red")
        self.script.postprocess(p)
        self.assertEqual(self.shared.prompt_styles.styles, original)
        self.assertIs(self.shared.prompt_styles.styles["base"], original_obj)

    def test_directive_only_style_is_cleaned_in_both_fields(self):
        self.shared.prompt_styles.styles["rules"] = PromptStyle("rules", "#delete<remove>", "$delete<bad>")
        self.shared.prompt_styles.styles["target"] = PromptStyle("target", "remove keep", "bad keep")
        p = self.prompt("", selected=["rules"])
        self.script.before_process(p)
        self.assertEqual(self.shared.prompt_styles.styles["rules"].prompt, "")
        self.assertEqual(self.shared.prompt_styles.styles["rules"].negative_prompt, "")
        self.assertEqual(self.shared.prompt_styles.styles["target"].prompt, " keep")
        self.assertEqual(self.shared.prompt_styles.styles["target"].negative_prompt, " keep")

    def test_delete_precedes_replace_and_replacements_cascade(self):
        p = self.prompt("#delete<red> #replace<black|pink> #replace<pink|white> black")
        self.shared.prompt_styles.styles["target"] = PromptStyle("target", "red black", "")
        self.script.before_process(p)
        self.assertEqual(p.prompt, "   white")
        self.assertEqual(self.shared.prompt_styles.styles["target"].prompt, " white")

    def test_selected_style_replace_order_is_stable(self):
        self.shared.prompt_styles.styles.update({
            "a": PromptStyle("a", "#replace<black|pink>", ""),
            "b": PromptStyle("b", "#replace<pink|white>", ""),
        })
        for _ in range(6):
            p = self.prompt("black", selected=["a", "b"])
            self.script.before_process(p)
            self.assertEqual(p.prompt, "white")
            self.script.postprocess(p)

    def test_empty_replace_source_is_removed_without_insertion(self):
        p = self.prompt("#replace<|added> keep")
        self.script.before_process(p)
        self.assertEqual(p.prompt, " keep")

    def test_none_style_fields_are_treated_as_empty(self):
        self.shared.prompt_styles.styles["none"] = PromptStyle("none", None, None)
        p = self.prompt("#include<none>", "#include<none>")
        self.script.before_process(p)
        self.assertEqual(p.prompt, "")
        self.assertEqual(p.negative_prompt, "")

    def test_prompt_lists_keep_their_shape(self):
        p = self.prompt(["#include<base>", "plain"], ["#include<base>"])
        self.script.before_process(p)
        self.assertEqual(p.prompt, ["基本", "plain"])
        self.assertEqual(p.negative_prompt, ["基本ネガ"])

    def test_adetailer_prompt_keys_expand_positive_and_negative_suffix_keys(self):
        extra = {
            "ADetailer prompt": "#include<base>",
            "ADetailer prompt 2": "before #include<base>",
            "ADetailer negative prompt": "#include<base>",
        }
        p = self.prompt(extra=extra)
        self.script.process(p)
        self.assertEqual(extra["ADetailer prompt"], "基本")
        self.assertEqual(extra["ADetailer prompt 2"], "before 基本")
        self.assertEqual(extra["ADetailer negative prompt"], "基本ネガ")

    def test_self_and_mutual_cycles_warn_and_remove_only_cyclic_reference(self):
        self.shared.prompt_styles.styles.update({
            "self": PromptStyle("self", "before #include<self> after", ""),
            "left": PromptStyle("left", "L #include<right> R", ""),
            "right": PromptStyle("right", "Q #include<left> Z", ""),
        })
        p = self.prompt("#include<self>")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.script.before_process(p)
        self.assertNotIn("#include", p.prompt)
        self.assertIn("Warning", output.getvalue())
        self.assertLess(len(p.prompt), 100)
        self.assertTrue(p.prompt.startswith("before "))

    def test_failed_expansion_preserves_shared_styles_and_prompts(self):
        original = self.shared.prompt_styles.styles.copy()
        p = self.prompt("before", "negative")
        broken_factory = mock.Mock(side_effect=RuntimeError("再構築失敗"))
        self.module.styles.PromptStyle = broken_factory
        with self.assertRaises(RuntimeError):
            self.script.before_process(p)
        self.assertEqual(p.prompt, "before")
        self.assertEqual(p.negative_prompt, "negative")
        self.assertEqual(self.shared.prompt_styles.styles, original)

    def test_nested_processing_restores_child_then_parent_then_original_state(self):
        original = self.shared.prompt_styles.styles.copy()
        self.shared.prompt_styles.styles.update({
            "parent-rule": PromptStyle("parent-rule", "#replace<cat|dog>", ""),
            "child-rule": PromptStyle("child-rule", "#replace<cat|bird>", ""),
            "target": PromptStyle("target", "cat", ""),
        })
        original = self.shared.prompt_styles.styles.copy()
        parent = self.prompt("cat", selected=["parent-rule"])
        child = self.prompt("cat", selected=["child-rule"])
        self.script.before_process(parent)
        parent_state = self.shared.prompt_styles.styles.copy()
        self.script.before_process(child)
        self.assertEqual(child.prompt, "bird")
        self.script.postprocess(child)
        self.assertEqual(self.shared.prompt_styles.styles, parent_state)
        self.script.postprocess(parent)
        self.assertEqual(self.shared.prompt_styles.styles, original)
        self.assertEqual(parent.prompt, "dog")

    def test_postprocess_accepts_shallow_prompt_copy_and_is_idempotent(self):
        original = self.shared.prompt_styles.styles.copy()
        p = self.prompt("#include<base>")
        self.script.before_process(p)
        self.script.postprocess(self.prompt_copy(p))
        self.assertEqual(self.shared.prompt_styles.styles, original)
        self.script.postprocess(p)
        self.assertEqual(self.shared.prompt_styles.styles, original)

    def prompt_copy(self, p):
        return types.SimpleNamespace(**vars(p))

    def test_close_restores_styles_when_postprocess_was_skipped(self):
        original = self.shared.prompt_styles.styles.copy()
        p = self.prompt("#include<base>")
        self.script.before_process(p)
        self.assertTrue(callable(getattr(p, "close", None)))
        p.close()
        self.assertTrue(p.closed)
        self.assertEqual(self.shared.prompt_styles.styles, original)


if __name__ == "__main__":
    unittest.main()
