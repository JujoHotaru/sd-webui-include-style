"""貼り付け時のスタイル自動検出に関する回帰テスト。"""

import json
import types
import unittest

import test_includestyle as core


EXAMPLE = (
    "1girl, black hair, outdoors\n"
    "Negative prompt: bad hands\n"
    "Steps: 1, Seed: 123, Size: 64x64"
)


class AutoIncludeTests(unittest.TestCase):
    """既存のホストスタブを使って貼り付けコールバックを確認する。"""

    tearDown = core.IncludeStyleTests.tearDown

    def setUp(self):
        core.IncludeStyleTests.setUp(self)
        self.shared.opts = types.SimpleNamespace(strip_whitespaces=True)
        self.module.AUTO_INCLUDE_ON_PASTE = True

    def _paste(self, infotext=EXAMPLE, params=None):
        if params is None:
            positive, _, negative = infotext.rsplit('\n', 1)[0].partition('\nNegative prompt:')
            params = {'Prompt': positive.strip(), 'Negative prompt': negative.strip()}
        self.module._on_infotext_pasted(infotext, params)
        return params

    def prompt(self, positive="", negative="", selected=None, extra=None):
        return core.IncludeStyleTests.prompt(self, positive, negative, selected, extra)

    def test_full_matches_keep_native_extraction_and_selection(self):
        self.shared.prompt_styles.styles["portrait"] = core.PromptStyle(
            "portrait", "1girl, black hair, outdoors", "bad hands",
        )
        parsed = {"Prompt": "", "Negative prompt": "", "Styles array": ["portrait"]}

        self._paste(params=parsed)

        self.assertEqual(parsed, {"Prompt": "", "Negative prompt": "", "Styles array": ["portrait"]})

    def test_exact_full_text_match_handles_position_and_repetition(self):
        self.shared.prompt_styles.styles.update({
            "piece": core.PromptStyle("piece", "black hair", ""),
            "phrase": core.PromptStyle("phrase", "black hair, outdoors", ""),
        })
        cases = [
            ("black hair, outdoors", "black hair, outdoors"),
            ("black hair, outdoors, x", "#include<phrase>, x"),
            ("x, black hair, outdoors", "x, black hair, outdoors"),
            ("x, black hair, outdoors, black hair, outdoors", "x, #include<phrase>, black hair, outdoors"),
            ("x, black hair, outdoors, black hair, outdoors, tail", "x, #include<phrase>, #include<phrase>, tail"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                text = raw + "\nNegative prompt: none\nSteps: 1, Seed: 2, Size: 8x8"
                parsed = self._paste(text, {"Prompt": raw, "Negative prompt": "none"})
                self.assertEqual(parsed["Prompt"], expected)

    def test_longest_candidate_at_same_start_and_registration_order_for_equal_text(self):
        styles = self.shared.prompt_styles.styles
        styles.update({
            "short": core.PromptStyle("short", "red", ""),
            "long": core.PromptStyle("long", "red hair", ""),
            "first": core.PromptStyle("first", "blue eyes", ""),
            "second": core.PromptStyle("second", "blue eyes", ""),
        })
        parsed = self._paste(
            "red hair and blue eyes, tail\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8",
            {"Prompt": "red hair and blue eyes, tail", "Negative prompt": "n"},
        )
        self.assertEqual(parsed["Prompt"], "#include<long> and #include<first>, tail")

    def test_matching_is_case_sensitive_and_preserves_internal_whitespace(self):
        self.shared.prompt_styles.styles["exact"] = core.PromptStyle("exact", "Black  hair", "")
        text = "black  hair and Black hair\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8"
        parsed = self._paste(text, {"Prompt": "black  hair and Black hair", "Negative prompt": "n"})
        self.assertEqual(parsed["Prompt"], "black  hair and Black hair")

    def test_command_and_prompt_placeholder_regions_are_protected(self):
        self.shared.prompt_styles.styles["hair"] = core.PromptStyle("hair", "black hair", "")
        raw = (
            "#include<black hair> $includefile<black hair> %delete<black hair> "
            "#replace<black hair|red hair> {prompt} (black hair) __black hair__"
        )
        text = raw + "\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8"
        parsed = self._paste(text, {"Prompt": raw, "Negative prompt": "n"})
        self.assertEqual(parsed["Prompt"], (
            "#include<black hair> $includefile<black hair> %delete<black hair> "
            "#replace<black hair|red hair> {prompt} (#include<hair>) __#include<hair>__"
        ))

    def test_styles_with_commands_or_prompt_placeholder_are_excluded(self):
        styles = self.shared.prompt_styles.styles
        styles.update({
            "command": core.PromptStyle("command", "black hair", "#delete<x>"),
            "negative-command": core.PromptStyle("negative-command", "black hair", "#replace<a|b>"),
            "placeholder": core.PromptStyle("placeholder", "black hair", "{prompt}"),
            "include": core.PromptStyle("include", "black hair", "#include<base>"),
            "valid": core.PromptStyle("valid", "black hair", ""),
        })
        parsed = self._paste(
            "black hair, tail\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8",
            {"Prompt": "black hair, tail", "Negative prompt": "n"},
        )
        self.assertEqual(parsed["Prompt"], "#include<valid>, tail")

    def test_invalid_style_names_and_empty_bodies_are_excluded(self):
        styles = self.shared.prompt_styles.styles
        for name, body in (("", "match"), (" padded ", "match"), ("bad>name", "match"),
                           ("line\nname", "match"), ("empty", "")):
            styles[name] = core.PromptStyle(name, body, "")
        styles["usable"] = core.PromptStyle("usable", "match", "")
        parsed = self._paste(
            "match, tail\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8",
            {"Prompt": "match, tail", "Negative prompt": "n"},
        )
        self.assertEqual(parsed["Prompt"], "#include<usable>, tail")

    def test_replacement_results_are_not_searched_again(self):
        self.shared.prompt_styles.styles.update({
            "first": core.PromptStyle("first", "alpha", ""),
            "second": core.PromptStyle("second", "first", ""),
        })
        parsed = self._paste(
            "alpha, tail\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8",
            {"Prompt": "alpha, tail", "Negative prompt": "n"},
        )
        self.assertEqual(parsed["Prompt"], "#include<first>, tail")

    def test_existing_include_style_metadata_restores_originals_before_auto_detection(self):
        payload = {"prompt": "raw #include<base>", "negative prompt": "raw negative", "styles": ["base"]}
        parsed = {self.module.METADATA_KEY: json.dumps(payload), "Prompt": "already processed"}
        self._paste("raw #include<base>\nNegative prompt: raw negative\nSteps: 1, Seed: 2, Size: 8x8", parsed)
        self.assertEqual(parsed["Prompt"], payload["prompt"])
        self.assertEqual(parsed["Negative prompt"], payload["negative prompt"])
        self.assertEqual(parsed["Styles array"], ["base"])

    def test_malformed_metadata_does_not_fall_through_to_auto_detection(self):
        self.shared.prompt_styles.styles["raw"] = core.PromptStyle("raw", "match", "")
        parsed = {self.module.METADATA_KEY: "{", "Prompt": "keep", "Negative prompt": "keep n",
                  "Styles array": ["keep"]}
        previous = dict(parsed)
        self._paste("match\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8", parsed)
        self.assertEqual(parsed, previous)

    def test_disabled_switch_preserves_params_without_metadata_but_still_restores_metadata(self):
        self.shared.prompt_styles.styles["raw"] = core.PromptStyle("raw", "match", "")
        self.module.AUTO_INCLUDE_ON_PASTE = False
        parsed = {"Prompt": "match", "Negative prompt": "n", "other": 4}
        previous = dict(parsed)
        self._paste("match\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8", parsed)
        self.assertEqual(parsed, previous)
        parsed = {self.module.METADATA_KEY: json.dumps(
            {"prompt": "original", "negative prompt": "original n", "styles": []})}
        self._paste("match\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8", parsed)
        self.assertEqual(parsed["Prompt"], "original")
        self.assertEqual(parsed["Negative prompt"], "original n")

    def test_no_match_or_insufficient_standard_generation_fields_preserves_all_params(self):
        self.shared.prompt_styles.styles["raw"] = core.PromptStyle("raw", "different", "")
        for text in (EXAMPLE, "different\nNegative prompt: n\nSteps: 1, Seed: 2"):
            params = {"Prompt": "keep", "Negative prompt": "keep n", "other": object()}
            previous = dict(params)
            self._paste(text, params)
            self.assertEqual(params, previous)

    def test_mid_match_keeps_native_style_selection_and_hires_fields(self):
        self.shared.prompt_styles.styles["style"] = core.PromptStyle("style", "front", "back")
        text = (
            'front, tail, suffix\nNegative prompt: back, tail, bad suffix\nSteps: 1, Seed: 2, Size: 8x8, '
            'Hires prompt: "hires, front", Hires negative prompt: "hires bad"'
        )
        parsed = {"Prompt": "front, tail", "Negative prompt": "back, tail", "Styles array": ["suffix"],
                  "Hires prompt": "parsed hires", "Hires negative prompt": "parsed negative", 'Seed': '2'}
        self._paste(text, parsed)
        self.assertEqual(parsed["Prompt"], "#include<style>, tail")
        self.assertEqual(parsed["Negative prompt"], "#include<style>, tail")
        self.assertEqual(parsed["Styles array"], ["suffix"])
        self.assertEqual(parsed["Hires prompt"], "parsed hires")
        self.assertEqual(parsed["Hires negative prompt"], "parsed negative")
        self.assertEqual(parsed['Seed'], '2')

    def test_unspecified_hires_values_are_left_untouched(self):
        self.shared.prompt_styles.styles['style'] = core.PromptStyle('style', 'alpha', '')
        parsed = {"Prompt": "alpha, tail", "Negative prompt": "n", "Hires prompt": "keep",
                  "Hires negative prompt": "keep n"}
        self._paste("alpha, tail\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8", parsed)
        self.assertEqual(parsed['Prompt'], '#include<style>, tail')
        self.assertEqual(parsed["Hires prompt"], "keep")
        self.assertEqual(parsed["Hires negative prompt"], "keep n")

    def test_strip_whitespaces_false_preserves_negative_separator_space(self):
        self.shared.opts.strip_whitespaces = False
        self.shared.prompt_styles.styles["negative"] = core.PromptStyle("negative", "", "bad hands")
        parsed = self._paste(EXAMPLE, {"Prompt": "unmatched", "Negative prompt": " bad hands, tail"})
        self.assertEqual(parsed["Negative prompt"], " #include<negative>, tail")

    def test_candidates_use_source_styles_while_generation_holds_the_style_lock(self):
        self.shared.prompt_styles.styles.update({
            "rule": core.PromptStyle("rule", "#replace<red|blue>", ""),
            "source": core.PromptStyle("source", "red", ""),
        })
        processing = self.prompt("plain", selected=["rule"])
        self.script.before_process(processing)
        self.assertEqual(self.shared.prompt_styles.styles["source"].prompt, "blue")
        parsed = self._paste(
            "red, tail\nNegative prompt: n\nSteps: 1, Seed: 2, Size: 8x8",
            {"Prompt": "red, tail", "Negative prompt": "n"},
        )
        self.assertEqual(parsed["Prompt"], "#include<source>, tail")

    def test_full_and_suffix_matches_are_untouched_in_either_field(self):
        self.shared.prompt_styles.styles['style'] = core.PromptStyle('style', 'front', 'back')
        for positive, negative in (('front', 'back'), ('prefix, front', 'prefix, back'),
                                   ('front \t', 'back \t'), ('prefix, front \t', 'prefix, back \t')):
            with self.subTest(positive=positive, negative=negative):
                params = {'Prompt': positive, 'Negative prompt': negative, 'Styles array': ['keep']}
                previous = dict(params)
                self._paste(params=params)
                self.assertEqual(params, previous)

    def test_suffix_after_protected_command_is_not_converted(self):
        self.shared.prompt_styles.styles['style'] = core.PromptStyle('style', 'front', '')
        params = {'Prompt': '#delete<x> front  ', 'Negative prompt': ''}
        self._paste(params=params)
        self.assertEqual(params['Prompt'], '#delete<x> front  ')


if __name__ == "__main__":
    unittest.main()
