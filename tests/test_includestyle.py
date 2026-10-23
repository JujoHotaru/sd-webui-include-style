"""IncludeStyle のホスト非依存な回帰テスト。"""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
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


class HostOptions:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.data_labels = {}
        self.save = mock.Mock(side_effect=self._save)

    def __getattr__(self, key):
        if key in self.data:
            return self.data[key]
        raise AttributeError(key)

    def add_option(self, key, info):
        self.data_labels[key] = info
        self.data.setdefault(key, info.default)

    def set(self, key, value):
        if self.data.get(key) == value:
            return False
        self.data[key] = value
        return True

    def _save(self, filename):
        Path(filename).write_text(json.dumps(self.data), encoding='utf-8')


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
        settings_dir = tempfile.TemporaryDirectory()
        self.addCleanup(settings_dir.cleanup)
        self.settings_dir = settings_dir
        shared = types.SimpleNamespace(
            prompt_styles=PromptStyles(self.styles), opts=HostOptions(),
            config_filename=str(Path(settings_dir.name) / 'config.json'),
            OptionInfo=lambda default, **kwargs: types.SimpleNamespace(default=default, **kwargs),
        )
        scripts = types.SimpleNamespace(Script=HostScript, AlwaysVisible=object())
        host = types.ModuleType("modules")
        host.shared = shared
        host.styles = types.SimpleNamespace(PromptStyle=PromptStyle)
        host.scripts = scripts
        self.infotext_callbacks = []
        self.before_ui_callbacks = []
        self.ui_settings_callbacks = []
        host.script_callbacks = types.SimpleNamespace(
            on_infotext_pasted=self.infotext_callbacks.append,
            on_before_ui=self.before_ui_callbacks.append,
            on_ui_settings=self.ui_settings_callbacks.append,
        )
        gradio = types.ModuleType("gradio")
        gradio.Accordion = mock.MagicMock()
        def checkbox(**kwargs):
            if callable(kwargs.get('value')):
                kwargs['value'] = kwargs['value']()
            return types.SimpleNamespace(**kwargs, input=mock.Mock())
        gradio.Checkbox = mock.Mock(side_effect=checkbox)
        self.module_patch = mock.patch.dict(sys.modules, {"modules": host, "gradio": gradio})
        self.module_patch.start()
        spec = importlib.util.spec_from_file_location("includestyle_test_target", SOURCE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        for callback in self.ui_settings_callbacks:
            callback()
        self.shared = shared
        self.script = self.module.IncludeStyleScript()

    def tearDown(self):
        for p in reversed(getattr(self, "processing_objects", [])):
            self.script.postprocess(p)
        self.module_patch.stop()
        self.settings_dir.cleanup()

    def prompt(self, positive="", negative="", selected=None, extra=None):
        p = HostProcessing(positive, negative, list(selected or []), extra or {})
        self.processing_objects = getattr(self, "processing_objects", [])
        self.processing_objects.append(p)
        return p

    def test_script_registration_has_generation_panel_in_both_modes(self):
        self.assertEqual(self.script.title(), "IncludeStyle")
        for is_img2img, tab in ((False, "txt2img"), (True, "img2img")):
            with self.subTest(tab=tab):
                self.assertIs(self.script.show(is_img2img), self.module.scripts.AlwaysVisible)
                (checkbox,) = self.script.ui(is_img2img)
                self.module.gr.Accordion.assert_called_with("IncludeStyle", open=False)
                self.assertIs(checkbox.value, True)
                self.assertEqual(checkbox.label, "Stop with an error if the target is not found during generation")
                self.assertEqual(checkbox.elem_id, f"include_style_{tab}_error_on_missing")

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

    def test_missing_include_reports_error_and_stops_generation(self):
        p = self.prompt("left #include<存在しない> right")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "生成を中止"):
                self.script.before_process(p)
        self.assertEqual(p.prompt, "left #include<存在しない> right")
        self.assertIn("存在しない", output.getvalue())
        self.assertIn("Error", output.getvalue())

    def test_inc_alias_markers_nested_styles_and_adetailer(self):
        self.shared.prompt_styles.styles.update({
            "日本語": PromptStyle("日本語", "#inc<base> / $include<base>", "%inc<base>"),
            "選択": PromptStyle("選択", "$inc<日本語>", "#inc<日本語>"),
        })
        for marker in ("#", "$", "%"):
            with self.subTest(marker=marker):
                p = self.prompt(f"({marker}inc < 日本語 >:1.3)",
                                f"{{{marker}inc<日本語>|plain}}", selected=["選択"],
                                extra={"ADetailer prompt 2nd": f"{marker}inc<日本語>",
                                       "ADetailer negative prompt": [f"{marker}inc<日本語>"]})
                self.script.before_process(p)
                self.script.process(p)
                self.assertEqual(p.prompt, "(基本 / 基本:1.3)")
                self.assertEqual(p.negative_prompt, "{基本ネガ|plain}")
                self.assertEqual(self.shared.prompt_styles.styles["選択"].prompt, "基本 / 基本")
                self.assertEqual(self.shared.prompt_styles.styles["選択"].negative_prompt, "基本ネガ")
                self.assertEqual(p.extra_generation_params["ADetailer prompt 2nd"], "基本 / 基本")
                self.assertEqual(p.extra_generation_params["ADetailer negative prompt"], ["基本ネガ"])
                self.script.postprocess(p)

    def test_inc_alias_collects_rules_from_opposite_style_field(self):
        self.shared.prompt_styles.styles["rules"] = PromptStyle(
            "rules", "#replace<red|pink>", "#delete<bad>",
        )
        p = self.prompt("red", "bad keep $inc<rules>")
        self.script.before_process(p)
        self.assertEqual(p.prompt, "pink")
        self.assertEqual(p.negative_prompt, " keep ")

    def test_inc_alias_missing_references_error_and_unknown_command_names(self):
        for marker in ("#", "$", "%"):
            with self.subTest(marker=marker):
                p = self.prompt(f"{marker}inc<存在しない>")
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    with self.assertRaisesRegex(RuntimeError, "生成を中止"):
                        self.script.before_process(p)
                self.assertIn("存在しない", output.getvalue())

                unknown = self.prompt(f"{marker}INC<base> {marker}increment<base>")
                self.script.before_process(unknown)
                self.assertEqual(unknown.prompt, f"{marker}INC<base> {marker}increment<base>")
                self.script.postprocess(unknown)

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

    def test_self_and_mutual_cycles_report_error_and_stop_generation(self):
        self.shared.prompt_styles.styles.update({
            "self": PromptStyle("self", "before #include<self> after", ""),
            "left": PromptStyle("left", "L #include<right> R", ""),
            "right": PromptStyle("right", "Q #include<left> Z", ""),
        })
        p = self.prompt("#include<self>")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError, "循環参照"):
                self.script.before_process(p)
        self.assertEqual(p.prompt, "#include<self>")
        self.assertIn("Error", output.getvalue())

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
