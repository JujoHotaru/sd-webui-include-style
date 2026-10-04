import io
import re
import threading
from pathlib import Path, PureWindowsPath
from types import MethodType

from modules import shared, styles, scripts


RE_PAT_INCLUDE = r'([#$%]include\s*<([^>]*)>)'
RE_PAT_INCLUDEFILE = r'([#$%]includefile\s*<([^>]*)>)'
RE_PAT_EXPAND = r'([#$%](include|includefile)\s*<([^>]*)>)'
RE_PAT_DELETE = r'([#$%]delete\s*<([^>]*)>)'
RE_PAT_REPLACE = r'([#$%]replace\s*<([^>|]*)\s*\|\s*([^>]*)>)'
RE_PAT_ADETAILER = r'^ADetailer (negative )?prompt(?: \d+(?:st|nd|rd|th)?)?$'

MAX_INCLUDE_DEPTH = 100
MAX_PROMPT_LENGTH = 1_000_000
PROMPTS_DIRECTORY = Path(__file__).resolve().parent.parent / 'prompts'

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


class _IncludeResolver:
    def __init__(self, source):
        self.source = source
        self.cache = {}
        self.active = set()
        self.warned = set()
        self.file_texts = {}

    def _warning(self, key, reason, kind='Style'):
        warning = (kind, key, reason)
        if warning not in self.warned:
            print(f'[IncludeStyle] Warning: {kind} "{key}": {reason}')
            self.warned.add(warning)

    def style_content(self, key, negative, depth=0):
        cache_key = ('style', key, negative)
        if cache_key in self.active:
            self._warning(key, 'Circular include ignored.')
            return ''
        if depth >= MAX_INCLUDE_DEPTH:
            self._warning(key, 'Include depth limit exceeded; reference ignored.')
            return ''
        if cache_key in self.cache:
            return self.cache[cache_key]
        if key not in self.source:
            self._warning(key, 'not found!')
            return ''

        style = self.source[key]
        content = (style.negative_prompt if negative else style.prompt) or ''
        self.active.add(cache_key)
        try:
            content = self.expand(content, negative, depth + 1)
        except ValueError:
            self._warning(key, 'Expanded prompt length limit exceeded; reference ignored.')
            content = ''
        finally:
            self.active.remove(cache_key)
        self.cache[cache_key] = content
        return content

    def file_content(self, key, negative, depth=0):
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
            self._warning(key, f'Invalid prompt file path: {error}', 'File')
            return ''

        cache_key = ('file', path, negative)
        if cache_key in self.active:
            self._warning(key, 'Circular include ignored.', 'File')
            return ''
        if depth >= MAX_INCLUDE_DEPTH:
            self._warning(key, 'Include depth limit exceeded; reference ignored.', 'File')
            return ''
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
            content = self.expand(self.file_texts[path], negative, depth + 1)
        except (OSError, UnicodeError) as error:
            self._warning(key, f'Cannot read prompt file: {error}', 'File')
            content = ''
        except ValueError:
            self._warning(key, 'Expanded prompt length limit exceeded; reference ignored.', 'File')
            content = ''
        finally:
            self.active.remove(cache_key)
        self.cache[cache_key] = content
        return content

    def expand(self, prompt, negative, depth=0):
        parts = []
        length = 0
        offset = 0
        for found in re.finditer(RE_PAT_EXPAND, prompt):
            key = found[3].strip()
            if found[2] == 'includefile':
                content = self.file_content(key, negative, depth)
            else:
                content = self.style_content(key, negative, depth).strip()
            literal = prompt[offset:found.start()]
            length += len(literal) + len(content)
            if length > MAX_PROMPT_LENGTH:
                raise ValueError('IncludeStyle expanded prompt length limit exceeded')
            parts.extend((literal, content))
            offset = found.end()
        length += len(prompt) - offset
        if length > MAX_PROMPT_LENGTH:
            raise ValueError('IncludeStyle expanded prompt length limit exceeded')
        parts.append(prompt[offset:])
        return ''.join(parts)


class _StyleState:
    def __init__(self, database, source, working, original_close, owner, file_texts, copied_from):
        self.database = database
        self.original = database.styles
        self.source = source
        self.working = working
        self.original_close = original_close
        self.owner = owner
        self.file_texts = file_texts
        self.copied_from = copied_from
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
    # 現在のバージョンでは UI は持たない
    def title(self):
        return 'IncludeStyle'

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        return ()

    def _replace_common(self, prompt, negative):
        resolver = _IncludeResolver(shared.prompt_styles.styles)
        return _map_prompts(prompt, lambda text: resolver.expand(text, negative))

    def process(self, p, *args):
        state = getattr(p, _STATE_ATTRIBUTE, None)
        source = state.working if state is not None and state.active else shared.prompt_styles.styles
        resolver = _IncludeResolver(source)
        if state is not None and state.active:
            resolver.file_texts = state.file_texts
        params = getattr(p, 'extra_generation_params', None)
        if params:
            for key in params:
                found = re.fullmatch(RE_PAT_ADETAILER, key)
                if found and isinstance(params[key], (str, list)):
                    negative = bool(found[1])
                    params[key] = _map_prompts(params[key], lambda text: resolver.expand(text, negative))

    def postprocess(self, p, *args):
        _restore_processing(p)

    def before_process(self, p, *args):
        previous = getattr(p, _STATE_ATTRIBUTE, None)
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
            resolver = _IncludeResolver(source)
            working = {
                key: _new_style(style, resolver.style_content(key, False), resolver.style_content(key, True))
                for key, style in source.items()
            }

            used_styles = []
            for value in (p.prompt, p.negative_prompt):
                for text in _prompt_strings(value):
                    used_styles.extend(found[1].strip() for found in re.findall(RE_PAT_INCLUDE, text or ''))
            used_styles.extend(p.styles or [])
            used_styles = list(dict.fromkeys(used_styles))

            prompt = _map_prompts(p.prompt, lambda text: resolver.expand(text, False))
            negative_prompt = _map_prompts(p.negative_prompt, lambda text: resolver.expand(text, True))
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
            state = _StyleState(database, source, working, original_close, p, resolver.file_texts, copied_from)
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
