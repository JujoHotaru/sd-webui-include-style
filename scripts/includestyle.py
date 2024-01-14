import modules
from modules import shared, styles, scripts
import re

RE_PAT_INCLUDE = r'(#include\s*<([^>]*)>)'
RE_PAT_DELETE = r'(#delete\s*<([^>]*)>)'
RE_PAT_REPLACE = r'(#replace\s*<([^>|]*)\s*\|\s*([^>]*)>)'

class IncludeStyleScript(scripts.Script):

    original_styles_ : object = None
    prompt_delete_words_ = []
    negative_prompt_delete_words_ = []
    prompt_replace_elements_ = []
    negative_prompt_replace_elements_ = []

    # 現在のバージョンではUIは無い
    def title(self):
        return "IncludeStyle"
    def show(self, is_img2img):
        return modules.scripts.AlwaysVisible
    def ui(self, is_img2img):
        return ()

    def _replace_common(self, prompt, negative):

        # include指定をすべて探す
        founds = (re.findall(RE_PAT_INCLUDE, prompt))
        for found in founds:
            key = str.strip(found[1]) # keyにスタイル名が入る
            if key in shared.prompt_styles.styles:
                if(negative): # Negativeプロンプトの場合
                    content = str.strip(shared.prompt_styles.styles[key].negative_prompt)
                else: # Positiveプロンプトの場合
                    content = str.strip(shared.prompt_styles.styles[key].prompt)
                #print(f"[IncludeStyle] Includes style \"{key}\" : \"{content}\"")
            else:
                # includeで指定したスタイルが見つからない
                print(f"[IncludeStyle] Warning: Style \"{key}\" not found!")
                content = ""
            prompt = prompt.replace(found[0], content)
        
        #print(f"prompt = {prompt}")
        return prompt

    def process(self, p, *args):

        #import pprint
        #pprint.pprint(vars(p))
        #pprint.pprint(vars(p.scripts))

        # ADetailer用プロンプトの置換はこのタイミングで行う
        if p.extra_generation_params and "ADetailer prompt" in p.extra_generation_params:
            #print("_replace_common() for p.extra_generation_params[ADetailer prompt]")
            p.extra_generation_params["ADetailer prompt"] = self._replace_common(p.extra_generation_params["ADetailer prompt"], False)

    def postprocess(self, p, *args):

        # before_processで差し替えたスタイルデータを元に戻す
        if(self.original_styles_) :
            shared.prompt_styles.styles = self.original_styles_
            self.original_styles_ = None
        pass

    def before_process(self, p, *args):

        import pprint
        #pprint.pprint(vars(p))

        # 他拡張機能より優先してinclude処理を行うため、processではなくbefore_processで置換処理を行う。
        # スタイルはこの時点ではプロンプトに反映されていないため、スタイルマネージャー側に記録されているデータを置換してしまう。
        # 処理が終わったら戻すため、オリジナルデータをコピーしておく
        self.original_styles_ = shared.prompt_styles.styles.copy()

        # メモリ上のスタイルデータのincludeをすべて解決（再帰対応）
        processed = True
        while processed:
            processed = False
            for key in shared.prompt_styles.styles:

                # 通常プロンプト
                new_prompt = ""
                if(shared.prompt_styles.styles[key].prompt and len(shared.prompt_styles.styles[key].prompt) > 0):
                    new_prompt = self._replace_common(shared.prompt_styles.styles[key].prompt, False)
                    if(new_prompt != shared.prompt_styles.styles[key].prompt):
                        processed = True

                # Negativeプロンプト
                new_negative_prompt = ""
                if(shared.prompt_styles.styles[key].negative_prompt and len(shared.prompt_styles.styles[key].negative_prompt) > 0):
                    new_negative_prompt = self._replace_common(shared.prompt_styles.styles[key].negative_prompt, True)
                    if(new_negative_prompt != shared.prompt_styles.styles[key].negative_prompt):
                        processed = True

                # スタイル差し替え
                shared.prompt_styles.styles[key] = styles.PromptStyle(
                        shared.prompt_styles.styles[key].name, new_prompt, new_negative_prompt,
                        shared.prompt_styles.styles[key].path)

        #pprint.pprint(shared.prompt_styles.styles)

        if p.prompt and len(p.prompt) > 0:
            #print("_replace_common() for p.prompt")
            p.prompt = self._replace_common(p.prompt, False)
        if p.negative_prompt and len(p.negative_prompt) > 0:
            #print("_replace_common() for p.negative_prompt")
            p.negative_prompt = self._replace_common(p.negative_prompt, True)

        # 続いてdeleteの処理
        # promptからdelete指定をすべて探し、指定そのものは消す
        founds = (re.findall(RE_PAT_DELETE, p.prompt))
        for found in founds:
            delete_word = str.strip(found[1])
            p.prompt = p.prompt.replace(found[0], "")
            self.prompt_delete_words_.append(delete_word)
        founds = (re.findall(RE_PAT_DELETE, p.negative_prompt))
        for found in founds:
            delete_word = str.strip(found[1])
            p.negative_prompt = p.negative_prompt.replace(found[0], "")
            self.negative_prompt_delete_words_.append(delete_word)

        for key in shared.prompt_styles.styles:

            replaced = False

            # 通常プロンプト
            new_prompt = ""
            if(shared.prompt_styles.styles[key].prompt and len(shared.prompt_styles.styles[key].prompt) > 0):
                new_prompt = shared.prompt_styles.styles[key].prompt
                for delete_word in self.prompt_delete_words_:
                    new_prompt = new_prompt.replace(delete_word, "")
                if(new_prompt != shared.prompt_styles.styles[key].prompt):
                    replaced = True
            
            # Negativeプロンプト
            new_negative_prompt = ""
            if(shared.prompt_styles.styles[key].negative_prompt and len(shared.prompt_styles.styles[key].negative_prompt) > 0):
                new_negative_prompt = shared.prompt_styles.styles[key].negative_prompt
                for delete_word in self.negative_prompt_delete_words_:
                    new_negative_prompt = new_negative_prompt.replace(delete_word, "")
                if(new_negative_prompt != shared.prompt_styles.styles[key].negative_prompt):
                    replaced = True
            
            # スタイル差し替え
            if(replaced):
                shared.prompt_styles.styles[key] = styles.PromptStyle(
                    shared.prompt_styles.styles[key].name, new_prompt, new_negative_prompt,
                    shared.prompt_styles.styles[key].path)

        # 続いてreplaceの処理
        # promptからreplace指定をすべて探し、指定そのものは消す
        founds = (re.findall(RE_PAT_REPLACE, p.prompt))
        for found in founds:
            replace_from = str.strip(found[1])
            replace_to = str.strip(found[2])
            p.prompt = p.prompt.replace(found[0], "")
            self.prompt_replace_elements_.append((replace_from, replace_to))
            #print(f"add replace element : {replace_from} to {replace_to}")
        founds = (re.findall(RE_PAT_DELETE, p.negative_prompt))
        for found in founds:
            replace_from = str.strip(found[1])
            replace_to = str.strip(found[2])
            p.negative_prompt = p.negative_prompt.replace(found[0], "")
            self.negative_prompt_replace_elements_.append((replace_from, replace_to))

        for key in shared.prompt_styles.styles:

            replaced = False

            # 通常プロンプト
            new_prompt = ""
            if(shared.prompt_styles.styles[key].prompt and len(shared.prompt_styles.styles[key].prompt) > 0):
                new_prompt = shared.prompt_styles.styles[key].prompt
                for replace_element in self.prompt_replace_elements_:
                    new_prompt = new_prompt.replace(replace_element[0], replace_element[1])
                if(new_prompt != shared.prompt_styles.styles[key].prompt):
                    replaced = True
            
            # Negativeプロンプト
            new_negative_prompt = ""
            if(shared.prompt_styles.styles[key].negative_prompt and len(shared.prompt_styles.styles[key].negative_prompt) > 0):
                new_negative_prompt = shared.prompt_styles.styles[key].negative_prompt
                for replace_element in self.negative_prompt_replace_elements_:
                    new_negative_prompt = new_negative_prompt.replace(replace_element[0], replace_element[1])
                if(new_negative_prompt != shared.prompt_styles.styles[key].negative_prompt):
                    replaced = True
            
            # スタイル差し替え
            if(replaced):
                shared.prompt_styles.styles[key] = styles.PromptStyle(
                    shared.prompt_styles.styles[key].name, new_prompt, new_negative_prompt,
                    shared.prompt_styles.styles[key].path)
