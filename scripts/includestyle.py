import modules.scripts as scripts
import modules
from modules import shared
import re

RE_PATTERN = r'(#include\s*<([^>]*)>)'

class IncludeStyleScript(scripts.Script):

    def title(self):
        return "IncludeStyle"
    def show(self, is_img2img):
        return modules.scripts.AlwaysVisible
    def ui(self, is_img2img):
        return ()

    def _replace_common(self, prompt, negative):

        founds = (re.findall(RE_PATTERN, prompt))
        for found in founds:
            key = str.strip(found[1])
            if key in shared.prompt_styles.styles:
                if(negative):
                    content = str.strip(shared.prompt_styles.styles[key].negative_prompt)
                else:
                    content = str.strip(shared.prompt_styles.styles[key].prompt)
                #print(f"[IncludeStyle] Includes style \"{key}\" : \"{content}\"")
            else:
                print(f"[IncludeStyle] Warning: Style \"{key}\" not found!")
                content = ""
            prompt = prompt.replace(found[0], content)
        
        #print(f"prompt = {prompt}")
        return prompt

    def process(self, p, *args):

        if p.extra_generation_params and "ADetailer prompt" in p.extra_generation_params:
            #print("_replace_common() for p.extra_generation_params[ADetailer prompt]")
            p.extra_generation_params["ADetailer prompt"] = self._replace_common(p.extra_generation_params["ADetailer prompt"], False)

    def before_process(self, p, *args):

        #import pprint
        #pprint.pprint(vars(p))
        if p.prompt and len(p.prompt) > 0:
            #print("_replace_common() for p.prompt")
            p.prompt = self._replace_common(p.prompt, False)
        if p.negative_prompt and len(p.negative_prompt) > 0:
            #print("_replace_common() for p.negative_prompt")
            p.negative_prompt = self._replace_common(p.negative_prompt, True)
