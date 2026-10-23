import io
import json
import re
import threading
from pathlib import Path, PureWindowsPath
from types import MethodType

import gradio as gr

from modules import shared, styles, scripts, script_callbacks


RE_PAT_INCLUDE = r'([#$%](?:include|inc)\s*<([^>]*)>)'
RE_PAT_INCLUDEFILE = r'([#$%](?:includefile|file)\s*<([^>]*)>)'
RE_PAT_EXPAND = r'([#$%](include|inc|includefile|file)\s*<([^>]*)>)'
RE_PAT_DELETE = r'([#$%]delete\s*<([^>]*)>)'
RE_PAT_REPLACE = r'([#$%]replace\s*<([^>|]*)\s*\|\s*([^>]*)>)'
RE_PAT_ADETAILER = r'^ADetailer (negative )?prompt(?: \d+(?:st|nd|rd|th)?)?$'
RE_PAT_FILE_POSITION = r'(?<![^\r\n])##(?P<position>positive|negative)##(?:\r\n|\r|\n|$)'

MAX_INCLUDE_DEPTH = 100
MAX_PROMPT_LENGTH = 1_000_000
PROMPTS_DIRECTORY = Path(__file__).resolve().parent.parent / 'prompts'
METADATA_KEY = 'Include-style'
AUTO_INCLUDE_ON_PASTE = True
_UI_SETTINGS_LOCK = threading.Lock()
_TEMPLATE_PROMPT_CHECKBOXES = {}

# 共有スタイルを使う期間を直列化し、同じスレッドの入れ子処理を許可する
_STYLE_LOCK = threading.RLock()
_STYLE_STATES = []
_STATE_ATTRIBUTE = '_include_style_state'


def _map_prompts(value, transform):
    if isinstance(value, list):
        return [transform(item or '') for item in value]
    return transform(value or '')


def _prompt_strings(value):
    return value if isinstance(value, list) else [value or '']


def _has_commands(text):
    return any(re.search(pattern, text or '') for pattern in
               (RE_PAT_EXPAND, RE_PAT_DELETE, RE_PAT_REPLACE))


def _append_prompt(text, addition):
    if not addition:
        return text
    separator = ', ' if text else ''
    if len(text) + len(separator) + len(addition) > MAX_PROMPT_LENGTH:
        raise ValueError('IncludeStyle expanded prompt length limit exceeded')
    return text + separator + addition


class _Expansion:
    def __init__(self, texts, end_negative):
        self.texts = tuple(texts)
        self.end_negative = end_negative


class _DeferredIncludeError(RuntimeError):
    pass


def _combine_prompt_pair(values, expanded):
    outputs = []
    for side in (0, 1):
        own, opposite = expanded[side], expanded[1 - side]
        has_additions = any(result.texts[side] for result in opposite)
        own_list, other_list = (isinstance(values[index], list) for index in (side, 1 - side))
        if has_additions and own_list and other_list and len(own) != len(opposite):
            raise ValueError('IncludeStyle requires matching positive and negative prompt list lengths')
        count = len(opposite) if has_additions and not own_list and other_list else len(own)
        texts = []
        for index in range(count):
            text = own[index if own_list else 0].texts[side]
            if has_additions:
                text = _append_prompt(text, opposite[index if other_list else 0].texts[side])
            texts.append(text)
        outputs.append(texts if own_list or count != 1 else texts[0])
    return tuple(outputs)


class _OriginalPrompts:
    def __init__(self, p, source, working, prompt, negative_prompt, previous):
        self.styles = list(p.styles or [])
        self.values = []
        self.changed = []
        self.outputs = tuple(_map_prompts(value, lambda text: text) for value in (prompt, negative_prompt))
        inherited = previous.originals if previous is not None and previous.owner is not p else None
        for side, (raw, result) in enumerate(zip((p.prompt, p.negative_prompt), self.outputs)):
            raw = _map_prompts(raw, lambda text: text)
            # ADetailer の再開用コピーには、既に解決済みの入力と親の原本が渡される
            if inherited is not None and raw == inherited.outputs[side] and self.styles == inherited.styles:
                self.values.append(inherited.values[side])
                self.changed.append(inherited.changed[side])
                continue
            field = 'negative_prompt' if side else 'prompt'
            selected_changed = any(
                key in source and (
                    _has_commands(getattr(source[key], field)) or
                    (getattr(source[key], field) or '') != getattr(working[key], field)
                ) for key in self.styles
            )
            raw_texts = _prompt_strings(raw)
            flags = []
            for index, transformed in enumerate(_prompt_strings(result)):
                text = raw_texts[index if isinstance(raw, list) else 0]
                flags.append(selected_changed or _has_commands(text) or text != transformed)
            self.values.append(raw)
            self.changed.append(flags)

    def is_changed(self, side, index):
        position = index if isinstance(self.outputs[side], list) else 0
        return 0 <= position < len(self.changed[side]) and self.changed[side][position]

    def value(self, index):
        if not any(self.is_changed(side, index) for side in (0, 1)):
            return None
        texts = []
        for raw in self.values:
            if isinstance(raw, list):
                if not 0 <= index < len(raw):
                    return None
                texts.append(raw[index])
            else:
                texts.append(raw)
        # 標準の infotext の引用処理を通しても、空文字と前後空白を失わない
        return json.dumps({
            'prompt': texts[0], 'negative prompt': texts[1], 'styles': self.styles,
        }, ensure_ascii=False)


def _original_index(p, fields):
    if fields.get('use_main_prompt', False):
        return 0
    batch_size = getattr(p, 'batch_size', 1)
    index = fields.get('index')
    if index is None:
        return fields.get('iteration', 0) * batch_size + fields.get('position_in_batch', 0)
    all_prompts = fields.get('all_prompts')
    if all_prompts is not None and (
        all_prompts is getattr(p, 'all_prompts', None) or len(all_prompts) > batch_size
    ):
        return index
    return getattr(p, 'iteration', 0) * batch_size + index


def _update_original_metadata(p):
    state = getattr(p, _STATE_ATTRIBUTE, None)
    params = getattr(p, 'extra_generation_params', None)
    if state is None or state.owner is not p or not state.metadata_valid or params is None:
        return
    originals = state.originals
    params.pop(METADATA_KEY, None)
    if any(any(flags) for flags in originals.changed):
        def value(**fields):
            return originals.value(_original_index(p, fields))
        params[METADATA_KEY] = value


def _auto_include_enabled():
    # 将来の設定 UI は、この判定へ値を渡す
    return AUTO_INCLUDE_ON_PASTE


def _auto_include_candidates():
    with _STYLE_LOCK:
        database = shared.prompt_styles
        source = database.styles
        if _STYLE_STATES and _STYLE_STATES[-1].database is database:
            source = _STYLE_STATES[-1].source
        candidates = ({}, {})
        for name, style in source.items():
            if not name or name != name.strip() or any(char in name for char in '>\r\n'):
                continue
            bodies = (style.prompt or '', style.negative_prompt or '')
            # 反対側の指示も発動するため、両欄とも副作用のないスタイルだけを使う
            if any(_has_commands(body) or '{prompt}' in body for body in bodies):
                continue
            for side, body in enumerate(bodies):
                body = body.strip()
                if body:
                    candidates[side].setdefault(body, name)
        return candidates


def _include_matching_styles(text, candidates):
    if not candidates:
        return text
    matcher = re.compile('|'.join(re.escape(body) for body in sorted(candidates, key=len, reverse=True)))
    protected = re.compile('|'.join((RE_PAT_EXPAND, RE_PAT_DELETE, RE_PAT_REPLACE)))
    end = len(text.rstrip())

    def replace_segment(start, stop):
        def replace(found):
            # 全文・末尾の一致はホスト標準のスタイル指定に任せる
            if start + found.end() == end:
                return found[0]
            return f'#include<{candidates[found[0]]}>'
        return matcher.sub(replace, text[start:stop])

    parts, offset = [], 0
    for command in protected.finditer(text):
        parts.append(replace_segment(offset, command.start()))
        parts.append(command[0])
        offset = command.end()
    parts.append(replace_segment(offset, len(text)))
    return ''.join(parts)


def _auto_include_from_infotext(infotext, params):
    if not _auto_include_enabled():
        return
    fields = {field: params.get(field) for field in ('Prompt', 'Negative prompt')}
    if not all(isinstance(text, str) for text in fields.values()):
        return
    candidates = _auto_include_candidates()
    converted = {
        field: _include_matching_styles(fields[field], candidates[side])
        for side, field in enumerate(('Prompt', 'Negative prompt'))
    }
    if all(converted[field] == fields[field] for field in converted):
        return
    # ホストが抽出した本文・スタイル選択・hires設定は保持し、残った部分だけを変換する
    params.update(converted)


def _on_infotext_pasted(_infotext, params):
    if METADATA_KEY not in params:
        _auto_include_from_infotext(_infotext, params)
        return
    if not _load_template_prompts_enabled():
        return
    raw = params.get(METADATA_KEY)
    if not isinstance(raw, str):
        return
    try:
        payload = json.loads(raw)
    except (ValueError, RecursionError):
        return
    if not isinstance(payload, dict):
        return
    prompt, negative_prompt, selected = (
        payload.get('prompt'), payload.get('negative prompt'), payload.get('styles'),
    )
    if not (isinstance(prompt, str) and isinstance(negative_prompt, str)
            and isinstance(selected, list) and all(isinstance(style, str) for style in selected)):
        return
    # 原本の両欄と選択スタイルを一緒に戻し、展開済みスタイルの二重適用を防ぐ
    params['Prompt'] = prompt
    params['Negative prompt'] = negative_prompt
    params['Styles array'] = list(selected)


def _register_ui_settings():
    for key in ('include_style_txt2img_error_on_missing',
                'include_style_img2img_error_on_missing',
                'include_style_load_template_prompts'):
        shared.opts.add_option(key, shared.OptionInfo(True, section=(None, 'IncludeStyle')))


def _save_ui_setting(key, enabled):
    with _UI_SETTINGS_LOCK:
        if shared.opts.set(key, bool(enabled)):
            shared.opts.save(shared.config_filename)
        return getattr(shared.opts, key)


def _load_template_prompts_enabled():
    return getattr(shared.opts, 'include_style_load_template_prompts', True)


def _set_load_template_prompts(enabled):
    return _save_ui_setting('include_style_load_template_prompts', enabled)


def _reset_template_prompt_checkboxes():
    _TEMPLATE_PROMPT_CHECKBOXES.clear()


class _IncludeResolver:
    def __init__(self, source, processing=None, error_on_missing=True):
        self.source = source
        self.processing = processing
        self.error_on_missing = error_on_missing
        self.cache = {}
        self.active = set()
        self.warned = set()
        self.file_texts = {}
        self.defer_errors = False

    def _warning(self, key, reason, kind='Style'):
        warning = (kind, key, reason)
        if warning not in self.warned:
            print(f'[IncludeStyle] Warning: {kind} "{key}": {reason}')
            self.warned.add(warning)

    def _error(self, key, reason, kind='Style'):
        message = f'IncludeStyle: {kind}「{key}」{reason}。生成を中止しました。'
        if self.defer_errors:
            raise _DeferredIncludeError(message)
        print(f'[IncludeStyle] Error: {message}')
        if self.processing is not None:
            # ホストはスクリプトコールバック内の例外を捕捉して続行するため、後段でも失敗させる
            def abort_generation(*args, **kwargs):
                raise RuntimeError(message)

            self.processing.init = abort_generation
        raise RuntimeError(message)

    def _missing(self, key, kind):
        # 未使用スタイルの参照エラーは保留し、使用されたときだけ警告する
        if self.error_on_missing or self.defer_errors:
            self._error(key, 'が見つかりません', kind)
        self._warning(key, 'が見つかりません。参照を空文字として生成を続行します。', kind)

    def style_content(self, key, negative, depth=0):
        return self._style_result(key, negative, depth).texts[negative]

    def _style_result(self, key, negative, depth=0):
        empty = _Expansion(('', ''), negative)
        cache_key = ('style', key, negative)
        if cache_key in self.active:
            self._error(key, '循環参照が発生しました')
        if depth >= MAX_INCLUDE_DEPTH:
            self._warning(key, 'Include depth limit exceeded; reference ignored.')
            return empty
        if cache_key in self.cache:
            return self.cache[cache_key]
        if key not in self.source:
            self._missing(key, 'スタイル')
            return empty

        style = self.source[key]
        content = (style.negative_prompt if negative else style.prompt) or ''
        self.active.add(cache_key)
        try:
            content = self._expand_result(content, negative, depth + 1)
        except ValueError:
            self._warning(key, 'Expanded prompt length limit exceeded; reference ignored.')
            content = empty
        finally:
            self.active.remove(cache_key)
        self.cache[cache_key] = content
        return content

    def file_content(self, key, negative, depth=0):
        return self._file_result(key, negative, depth).texts[negative]

    def _file_result(self, key, negative, depth=0):
        empty = _Expansion(('', ''), negative)
        try:
            relative = PureWindowsPath(key)
            if not relative.parts or relative.is_absolute() or relative.drive or relative.root:
                raise ValueError('An extension-relative filename is required.')
            if '..' in relative.parts or relative.is_reserved() or any(':' in part for part in relative.parts):
                raise ValueError('Paths outside the prompts folder are not allowed.')
            root = PROMPTS_DIRECTORY.resolve()
            path = root.joinpath(*relative.parts)
            if path.suffix.lower() != '.txt':
                path = path.with_name(path.name + '.txt')
            # prompts 内のリンクから外部実体も読み、実体パスで循環とキャッシュを管理する
            path = path.resolve()
        except (OSError, ValueError, RuntimeError) as error:
            self._error(key, f'のパスが無効です: {error}', 'プロンプトファイル')

        cache_key = ('file', path, negative)
        if any(('file', path, side) in self.active for side in (False, True)):
            self._error(key, '循環参照が発生しました', 'プロンプトファイル')
        if depth >= MAX_INCLUDE_DEPTH:
            self._warning(key, 'Include depth limit exceeded; reference ignored.', 'File')
            return empty
        if cache_key in self.cache:
            return self.cache[cache_key]

        self.active.add(cache_key)
        try:
            if path not in self.file_texts:
                # UTF-16 は BOM がある場合だけ判定し、本文の空白と改行を保持する
                with path.open('rb') as binary:
                    header = binary.read(2)
                    binary.seek(0)
                    encoding = 'utf-16' if header in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'
                    with io.TextIOWrapper(binary, encoding=encoding, newline='') as stream:
                        self.file_texts[path] = stream.read(MAX_PROMPT_LENGTH + 1)
            if len(self.file_texts[path]) > MAX_PROMPT_LENGTH:
                raise ValueError('IncludeStyle prompt file length limit exceeded')
            content = self._expand_result(self.file_texts[path], negative, depth + 1, file_mode=True)
        except FileNotFoundError:
            self._missing(key, 'プロンプトファイル')
            content = empty
        except (OSError, UnicodeError) as error:
            self._error(key, f'を読み込めません: {error}', 'プロンプトファイル')
        except ValueError:
            self._warning(key, 'Expanded prompt length limit exceeded; reference ignored.', 'File')
            content = empty
        finally:
            self.active.remove(cache_key)
        self.cache[cache_key] = content
        return content

    def expand(self, prompt, negative, depth=0):
        return self._expand_result(prompt, negative, depth).texts[negative]

    def expand_pair(self, prompt, negative_prompt):
        values = (prompt, negative_prompt)
        expanded = [[self._expand_result(text or '', bool(side)) for text in _prompt_strings(value)]
                    for side, value in enumerate(values)]
        return _combine_prompt_pair(values, expanded)

    def style_pair(self, key):
        expanded = [self._style_result(key, bool(side)) for side in (0, 1)]
        texts = []
        for side in (0, 1):
            try:
                texts.append(_append_prompt(expanded[side].texts[side], expanded[1 - side].texts[side]))
            except ValueError:
                self._warning(key, 'Expanded prompt length limit exceeded; reference ignored.')
                texts.append('')
        return tuple(texts)

    def _expand_result(self, prompt, negative, depth=0, file_mode=False):
        parts = [[], []]
        lengths = [0, 0]
        offset = 0
        current = negative

        def emit(text, side):
            # ファイル内は節をそのまま連結し、欄をまたぐ独立した参照間だけを区切る
            if text and not file_mode and side != negative and lengths[side]:
                text = ', ' + text
            lengths[side] += len(text)
            if lengths[side] > MAX_PROMPT_LENGTH:
                raise ValueError('IncludeStyle expanded prompt length limit exceeded')
            parts[side].append(text)

        pattern = RE_PAT_EXPAND + '|' + RE_PAT_FILE_POSITION if file_mode else RE_PAT_EXPAND
        for found in re.finditer(pattern, prompt):
            emit(prompt[offset:found.start()], current)
            if file_mode and found['position'] is not None:
                current = found['position'] == 'negative'
                offset = found.end()
                continue
            key = found[3].strip()
            if found[2] in ('includefile', 'file'):
                content = self._file_result(key, current, depth)
                next_side = content.end_negative if file_mode else current
            else:
                content = self._style_result(key, current, depth)
                next_side = current
            for side in (0, 1):
                emit(content.texts[side].strip(), side)
            current = next_side
            offset = found.end()
        emit(prompt[offset:], current)
        return _Expansion((''.join(part) for part in parts), current)


class _StyleState:
    def __init__(self, database, source, working, original_close, owner, file_texts, copied_from, originals,
                 style_results, error_on_missing):
        self.database = database
        self.original = database.styles
        self.source = source
        self.working = working
        self.original_close = original_close
        self.owner = owner
        self.file_texts = file_texts
        self.style_results = style_results
        self.error_on_missing = error_on_missing
        self.copied_from = copied_from
        self.originals = originals
        self.metadata_valid = True
        self.thread = threading.get_ident()
        self.active = True


def _restore_styles(state):
    if state is None or not state.active:
        return
    if state.thread != threading.get_ident():
        raise RuntimeError('IncludeStyle callbacks must run on the same thread')
    state.active = False
    try:
        # 親が先に終了した場合は、子の終了時にまとめて復元する
        while _STYLE_STATES and not _STYLE_STATES[-1].active:
            finished = _STYLE_STATES.pop()
            if finished.database.styles is finished.working:
                finished.database.styles = finished.original
    finally:
        _STYLE_LOCK.release()


def _close_processing(p, *args, **kwargs):
    state = getattr(p, _STATE_ATTRIBUTE, None)
    try:
        return state.original_close(*args, **kwargs)
    finally:
        # ホストが例外で postprocess を省略しても close で復元する
        _restore_processing(p)


def _restore_processing(p):
    state = getattr(p, _STATE_ATTRIBUTE, None)
    if state is not None and state.owner is p:
        # ADetailer が再開用コピーを閉じない場合も、元の処理の終了時に回収する
        for child in list(reversed(_STYLE_STATES)):
            ancestor = child.copied_from
            while ancestor is not None and ancestor is not state:
                ancestor = ancestor.copied_from
            if ancestor is state:
                _restore_styles(child)
    _restore_styles(state)


def _extract_rules(prompt, deletes, replacements):
    def delete(found):
        word = found[2].strip()
        if word:
            deletes.append(word)
        return ''

    def replace(found):
        old, new = found[2].strip(), found[3].strip()
        if old:
            replacements.append((old, new))
        return ''

    prompt = re.sub(RE_PAT_DELETE, delete, prompt)
    return re.sub(RE_PAT_REPLACE, replace, prompt)


def _apply_rules(prompt, deletes, replacements):
    for word in deletes:
        prompt = prompt.replace(word, '')
    for old, new in replacements:
        length = len(prompt) + prompt.count(old) * (len(new) - len(old))
        if length > MAX_PROMPT_LENGTH:
            raise ValueError('IncludeStyle replaced prompt length limit exceeded')
        prompt = prompt.replace(old, new)
    return prompt


def _new_style(style, prompt, negative_prompt):
    return styles.PromptStyle(style.name, prompt, negative_prompt, style.path)


class IncludeStyleScript(scripts.Script):
    def title(self):
        return 'IncludeStyle'

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        tab = 'img2img' if is_img2img else 'txt2img'
        error_setting = f'include_style_{tab}_error_on_missing'
        with gr.Accordion('IncludeStyle', open=False):
            error_on_missing = gr.Checkbox(
                value=lambda: getattr(shared.opts, error_setting, True),
                label='Stop with an error if the target is not found during generation',
                elem_id=f'include_style_{tab}_error_on_missing',
            )
            error_on_missing.do_not_save_to_config = True
            error_on_missing.input(
                fn=lambda enabled: _save_ui_setting(error_setting, enabled),
                inputs=[error_on_missing], queue=False,
            )
            load_template_prompts = gr.Checkbox(
                value=_load_template_prompts_enabled,
                label='Load template prompts when reading image information',
                elem_id=f'include_style_{tab}_load_template_prompts',
            )
            # チェック状態はshared.optsで保存し、UIの既定値による上書きを防ぐ
            load_template_prompts.do_not_save_to_config = True
            load_template_prompts.input(
                fn=_set_load_template_prompts, inputs=[load_template_prompts], queue=False,
            )
            for other in _TEMPLATE_PROMPT_CHECKBOXES.values():
                # input イベントだけを使い、相方の更新で再発火させない
                for source, target in ((load_template_prompts, other), (other, load_template_prompts)):
                    source.input(
                        fn=_set_load_template_prompts, inputs=[source], outputs=[target], queue=False,
                    )
            _TEMPLATE_PROMPT_CHECKBOXES[tab] = load_template_prompts
        return (error_on_missing,)

    def _replace_common(self, prompt, negative):
        resolver = _IncludeResolver(shared.prompt_styles.styles)
        return _map_prompts(prompt, lambda text: resolver.expand(text, negative))

    def process(self, p, error_on_missing=True, *args):
        state = getattr(p, _STATE_ATTRIBUTE, None)
        source = state.working if state is not None and state.active else shared.prompt_styles.styles
        if state is not None and state.active:
            error_on_missing = state.error_on_missing
        resolver = _IncludeResolver(source, p, error_on_missing)
        if state is not None and state.active:
            resolver.file_texts = state.file_texts
            resolver.cache.update(state.style_results)
        params = getattr(p, 'extra_generation_params', None)
        if params:
            groups = {}
            for key in list(params):
                found = re.fullmatch(RE_PAT_ADETAILER, key)
                if found and isinstance(params[key], (str, list)):
                    suffix = key[len('ADetailer negative ') if found[1] else len('ADetailer '):]
                    groups.setdefault(suffix, {})[bool(found[1])] = key
            updates = {}
            for suffix, keys in groups.items():
                positive_key = keys.get(False, 'ADetailer ' + suffix)
                negative_key = keys.get(True, 'ADetailer negative ' + suffix)
                values = tuple(params[keys[side]] if side in keys else '' for side in (False, True))
                prompt, negative_prompt = resolver.expand_pair(*values)
                for side, (key, value) in enumerate(((positive_key, prompt), (negative_key, negative_prompt))):
                    if side in keys or (key not in params and value):
                        updates[key] = value
            params.update(updates)

    def postprocess(self, p, *args):
        _restore_processing(p)

    def postprocess_batch(self, p, images, **kwargs):
        _update_original_metadata(p)

    def before_process(self, p, error_on_missing=True, *args):
        previous = getattr(p, _STATE_ATTRIBUTE, None)
        if previous is not None and previous.owner is p:
            previous.metadata_valid = False
        params = getattr(p, 'extra_generation_params', None)
        if params is not None:
            # 浅いコピーの再入処理で親の生成情報を消さない
            if previous is not None and previous.owner is not p:
                params = p.extra_generation_params = dict(params)
            params.pop(METADATA_KEY, None)
        if previous is not None and previous.active and previous.owner is p:
            # 同じ処理オブジェクトの再実行では、前回の状態を残さない
            _restore_processing(p)

        _STYLE_LOCK.acquire()
        installed = False
        try:
            database = shared.prompt_styles
            source = database.styles
            if _STYLE_STATES and _STYLE_STATES[-1].database is database:
                # ADetailer の子処理に親の削除・置換済みスタイルを引き継がせない
                source = _STYLE_STATES[-1].source
            resolver = _IncludeResolver(source, p, error_on_missing)
            resolver.defer_errors = True
            working = {}
            for key, style in source.items():
                try:
                    prompt, negative_prompt = resolver.style_pair(key)
                except _DeferredIncludeError:
                    # 未使用スタイルの不備は保留し、実際に参照された時点でエラーにする
                    resolver.cache.clear()
                    prompt, negative_prompt = style.prompt or '', style.negative_prompt or ''
                working[key] = _new_style(style, prompt, negative_prompt)
            resolver.defer_errors = False

            used_styles = []
            for value in (p.prompt, p.negative_prompt):
                for text in _prompt_strings(value):
                    used_styles.extend(found[1].strip() for found in re.findall(RE_PAT_INCLUDE, text or ''))
            used_styles.extend(p.styles or [])
            used_styles = list(dict.fromkeys(used_styles))

            # 警告で続行する場合は、事前展開で保留した参照も解決して作業用辞書へ反映する
            check_styles = (p.styles or []) if resolver.error_on_missing else used_styles
            for key in dict.fromkeys(check_styles):
                if key in source:
                    positive, negative = resolver.style_pair(key)
                    working[key] = _new_style(source[key], positive, negative)

            prompt, negative_prompt = resolver.expand_pair(p.prompt, p.negative_prompt)
            deletes, negative_deletes = [], []
            replacements, negative_replacements = [], []

            # 入力欄、直接参照、選択欄の順を維持して指示を取り出す
            prompt = _map_prompts(prompt, lambda text: _extract_rules(text, deletes, replacements))
            negative_prompt = _map_prompts(negative_prompt, lambda text: _extract_rules(text, negative_deletes, negative_replacements))
            for key in used_styles:
                if key in working:
                    style = working[key]
                    working[key] = _new_style(
                        style, _extract_rules(style.prompt, deletes, replacements),
                        _extract_rules(style.negative_prompt, negative_deletes, negative_replacements),
                    )

            for key, style in working.items():
                working[key] = _new_style(
                    style, _apply_rules(style.prompt, deletes, replacements),
                    _apply_rules(style.negative_prompt, negative_deletes, negative_replacements),
                )
            prompt = _map_prompts(prompt, lambda text: _apply_rules(text, deletes, replacements))
            negative_prompt = _map_prompts(negative_prompt, lambda text: _apply_rules(text, negative_deletes, negative_replacements))

            original_close = getattr(p, 'close', None)
            if getattr(original_close, '__func__', None) is _close_processing:
                original_close = previous.original_close
                if getattr(original_close, '__self__', None) is not None:
                    original_close = MethodType(original_close.__func__, p)
            copied_from = previous if previous is not None and previous.owner is not p else None
            originals = _OriginalPrompts(p, source, working, prompt, negative_prompt, previous)
            style_results = {}
            resolver.defer_errors = True
            for key in source:
                for negative in (False, True):
                    try:
                        result = resolver._style_result(key, negative)
                    except _DeferredIncludeError:
                        continue
                    texts = []
                    for side, text in enumerate(result.texts):
                        if key in used_styles:
                            text = _extract_rules(text, [], [])
                        texts.append(_apply_rules(text, negative_deletes if side else deletes,
                                                  negative_replacements if side else replacements))
                    style_results[('style', key, negative)] = _Expansion(texts, result.end_negative)
            resolver.defer_errors = False
            state = _StyleState(database, source, working, original_close, p, resolver.file_texts, copied_from,
                                originals, style_results, error_on_missing)
            setattr(p, _STATE_ATTRIBUTE, state)
            if original_close is not None:
                p.close = MethodType(_close_processing, p)
            _STYLE_STATES.append(state)
            database.styles = working
            p.prompt, p.negative_prompt = prompt, negative_prompt
            installed = True
        finally:
            # 展開に失敗した場合は共有データを変更せず、ロックを解放する
            if not installed:
                _STYLE_LOCK.release()


script_callbacks.on_infotext_pasted(_on_infotext_pasted)
script_callbacks.on_before_ui(_reset_template_prompt_checkboxes)
script_callbacks.on_ui_settings(_register_ui_settings)
