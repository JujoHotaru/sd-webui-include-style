# sd-webui-include-style

[日本語](README.md) | English

## Introduction (Disclaimer)

- This extension is currently developed primarily for the author's personal use.
  - Its specifications and behavior may change without notice.
- It has been tested within the scope of the author's use, but compatibility issues may exist with features or extensions unknown to the author.
- The author and related parties accept no responsibility for any damage that may result from using this extension.

## Overview

This extension enhances the “Styles” feature in [Stable Diffusion WebUI (AUTOMATIC1111)](https://github.com/AUTOMATIC1111/stable-diffusion-webui), its derivatives such as [WebUI Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge), and [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo).

Write syntax such as `#include<Style Name>` or `#includefile<File Name>` in a prompt to insert the contents of a style or text file into the prompt.

You can use these commands in the positive and negative prompt fields in txt2img and img2img, and in styles. You can also use `#delete` to remove specified text and `#replace` to replace it. A setting described below is required to use them in ADetailer's additional prompt fields. Examples combining these commands with Dynamic Prompts are also provided below.

You can also use these commands in styles, which lets you define shared elements in separate styles and reuse them across multiple styles. This was the main purpose of the extension.

## Installation

Open “Extensions” > “Install from URL” in WebUI and enter the following URL in “URL for extension’s git repository” to install the extension.

```
https://github.com/JujoHotaru/sd-webui-include-style
```

Restart WebUI after installation. The extension has no dedicated settings page or control panel. When enabled, it processes prompt syntax during generation.

## Syntax

The four syntax forms below are available. In each form, you can replace the leading `#` with `$` or `%`. Write command names in lowercase.

| Syntax | Action |
| --- | --- |
| `#include<Style Name>` | Inserts the style contents at this position |
| `#includefile<File Name>` | Inserts a text file from the `prompts` folder at this position |
| `#delete<Text to Delete>` | Deletes all occurrences of the specified text |
| `#replace<Old Text\|New Text>` | Replaces all occurrences of the specified text |

You can shorten `include` to `inc` and `includefile` to `file`. For example, `#inc<Long Black Hair>` produces the same result as `#include<Long Black Hair>`, and `#file<foobar>` produces the same result as `#includefile<foobar>`. Both aliases support `#`, `$`, and `%`, including forms such as `$inc < Long Black Hair >` and `%file<foobar.txt>`. You can use them in positive and negative prompts, styles, file contents, and ADetailer, and mix them with the original command names. The examples and restrictions below also apply to the aliases.

You can include spaces between the command and `<`, and around the argument, as in `#include < Style Name >`. Spaces around the argument are removed; spaces within it are kept. Style names and delete/replace targets are case-sensitive.

After nested references are expanded, leading and trailing whitespace (spaces, tabs, newlines, and similar characters) is removed from text inserted by `include` and `includefile`. Whitespace within the inserted text and around commands in the input prompt is preserved.

The argument cannot contain `>`. The old text in `replace` cannot contain `|`. There is no syntax for escaping these delimiters.

In environments such as Forge that treat `#` as a comment, or where the syntax conflicts with another extension, use forms such as `$include<Style Name>` or `%include<Style Name>`.

## Using include

Register the styles you want to reference in advance, for example by using WebUI's style-saving feature. The `styles.csv` below illustrates the mapping between style names and contents. In practice, use the style file loaded by WebUI. If you edit the CSV directly, reload it, for example by restarting WebUI.

Suppose the styles have the following contents:

```csv
name,prompt,negative_prompt
Long Black Hair,"black hair, long hair",""
Default Negative Prompt,"","EasyNegative, bad face"
```

Writing the following in a prompt inserts the contents of the specified style. You do not need to select the referenced style in WebUI's style selector just to use include. Applying the same style in the selector as well may duplicate its contents.

```
1girl, #include < Long Black Hair >, in school, wearing school uniform
```
↓

```
1girl, black hair, long hair, in school, wearing school uniform
```

In a negative prompt, the style's `negative_prompt` field is inserted. In the positive prompt field, only its `prompt` field is inserted. To use both, write an include in each field.

```
#include<Default Negative Prompt>
```
↓

```
EasyNegative, bad face
```

Styles can reference other styles, and those styles can include further styles. A referenced style can be defined after the style that includes it. In the example below, “Long Black Hair” is defined after “Girl with Long Black Hair in a Classroom,” which includes it. “Long Black Hair” also includes “Long Hair.”

```csv
name,prompt,negative_prompt
Girl with Long Black Hair in a Classroom,"1girl, #include<Long Black Hair>, in school, wearing school uniform","#include<Default Negative Prompt>"
Long Hair,"long hair",""
Long Black Hair,"black hair, #include<Long Hair>",""
Default Negative Prompt,"","EasyNegative, bad face"
```

When you generate with the “Girl with Long Black Hair in a Classroom” style applied, the resulting prompts are:

```
Prompt : 1girl, black hair, long hair, in school, wearing school uniform
Negative prompt : EasyNegative, bad face
```

Include expansion is simple text replacement and does not add separators such as commas. This lets you combine it with prompt emphasis/weighting and Dynamic Prompts. Expansion happens during generation; the extension does not change the text displayed in the input fields or the contents of style files.

In the example below, the prompt inserted by “Long Black Hair” (`black hair, long hair`) is assigned 1.3x emphasis.

```csv
name,prompt,negative_prompt
Girl with Long Black Hair in a Classroom,"1girl, (#include<Long Black Hair>:1.3), in school, wearing school uniform","#include<Default Negative Prompt>"
Long Hair,"long hair",""
Long Black Hair,"black hair, #include<Long Hair>",""
Default Negative Prompt,"","EasyNegative, bad face"
```

The following example uses Dynamic Prompts to randomly select one of four hair colors and one of two hair lengths.

```csv
name,prompt,negative_prompt
Girl in a Classroom,"1girl, {#include<Long Hair>|#include<Short Hair>}, in school, wearing school uniform","#include<Default Negative Prompt>"
Random Hair Color,"{black|pink|blonde|white} hair",""
Long Hair,"#include<Random Hair Color>, long hair",""
Short Hair,"#include<Random Hair Color>, short hair",""
Default Negative Prompt,"","EasyNegative, bad face"
```

Dynamic Prompts performs the random selection. This extension expands include commands before that happens. The result when combining extensions also depends on their versions and processing order.

WebUI's standard style feature uses `{prompt}` as a placeholder, but include does not expand it. For example, including `prefix, {prompt}, suffix` inserts that text with `{prompt}` unchanged. To wrap the input prompt, apply the style from WebUI's style selector.

## Using includefile

Place a text file encoded as UTF-8 (with or without a BOM), or BOM-prefixed UTF-16LE/UTF-16BE, in the extension's `prompts` folder. You can omit the file extension, as in `#includefile<foobar>`. You can also specify `.txt`, as in `#includefile<foobar.txt>`. For example, save the following text in `prompts/foobar.txt`:

```text
black hair, long hair
```

Write the following in a prompt to insert the text with its surrounding whitespace removed:

```
1girl, #includefile<foobar>
```
↓

```
1girl, black hair, long hair
```

You can specify a relative path containing a subfolder, such as `foo/bar`, and you can also use the Windows path separator `\`. All file references are resolved from `prompts`. Whitespace at the beginning and end of file contents is removed; spaces, tabs, and newlines within the contents are preserved. The BOM is not included in the prompt. Files without a BOM are read as UTF-8; UTF-16 is not guessed. File contents can also contain `#include` and `#includefile`. Nested `includefile` references are always resolved from the `prompts` folder. Style references in file contents use the style's `prompt` field in positive prompts and its `negative_prompt` field in negative prompts. The file contents themselves are shared by both fields.

File names must be relative paths based on the `prompts` folder. If a file or subfolder inside `prompts` is a symbolic link, its target is read, even when the target is outside `prompts`. References in file contents continue to be resolved from `prompts`. Absolute paths, drive specifications, `..`, alternate data streams, and device names are not allowed. If a file is missing, cannot be read (for example, because a link is broken), or has an invalid path, a warning is issued and that reference is replaced with an empty string.

You can use `#includefile` in styles and ADetailer's additional prompt fields as well. You can also apply `delete` and `replace` to the inserted text. Changes to a file take effect on the next generation.

## Using delete and replace

With the “Long Black Hair” style described above, you can write:

| Input prompt | Expanded prompt |
| --- | --- |
| `#delete<, long hair>#include<Long Black Hair>` | `black hair` |
| `#replace<black hair\|pink hair>#include<Long Black Hair>` | `pink hair, long hair` |
| `#replace<black\|pink>#delete<, long hair>#include<Long Black Hair>` | `pink hair` |

Regardless of where the commands appear, processing order is: expand `include` and `includefile` → delete text with `delete` → replace text with `replace`. Commands in the positive prompt field affect the positive prompt; commands in the negative prompt field affect the negative prompt. They also affect expanded file contents, included content, and the contents of styles applied through WebUI's style selector.

You can also put `delete` and `replace` in a style. A command in a style affects not only that style's contents, but also the input prompt and other styles on the same side (positive or negative).

Delete and replace operate on substrings without considering tag separators or word boundaries. For example, `#delete<hair>` removes `hair` from both `long hair` and `hairpin`. They are not regular expressions. Extra commas and spaces are not cleaned up. In the deletion example above, `, ` is included in the target text.

Multiple replace commands are applied in order, so the result of one replacement may match the target of the next. The order is commands in the input prompt, directly included styles in positive/negative prompt order of appearance, then styles in the order selected in WebUI. Empty delete targets and empty old text in replace commands are ignored.

## Using ADetailer

You can use include in ADetailer's “ADetailer prompt” and “ADetailer negative prompt” fields after completing this setup:

1. Open “Settings” in WebUI.
2. Go to “ADetailer”.
3. Find the “Script names to apply to ADetailer (separated by comma)” text box.
4. Keep any existing entries and add `includestyle`, separated by a comma. If the box is empty, enter only `includestyle`.
5. Click “Apply Settings”.

For example, enter `$include<Long Black Hair>` in “ADetailer prompt” and `$include<Default Negative Prompt>` in “ADetailer negative prompt”. Processing order varies by ADetailer and WebUI versions, so after updating, check that prompts for additional processing are expanded.

## Saving and restoring raw prompts

When a command from this extension is used in either prompt field or in a selected style and generation succeeds, the image stores the following restoration data:

- The positive prompt before include and other commands were expanded
- The negative prompt before expansion
- The styles selected during generation

If a command was used in either field, both prompts and the style selection are saved together. When generating multiple images, each image stores the corresponding input. Newlines, quotation marks, and leading or trailing whitespace are preserved. The image's regular generation parameters also retain the expanded prompts used for generation.

This works with PNG, JPEG, and WebP. Enable WebUI's image metadata saving setting.

To restore in Forge Neo:

1. Drop the image into the positive prompt field. The full generation parameters are loaded.
2. Click the “Read generation parameters...” button.
3. The raw positive and negative prompts and selected styles are restored. Other generation settings are applied through WebUI's normal loading behavior.

You can also restore by sending an image from PNG Info to txt2img or img2img. If no style was selected during generation, the style selection is cleared when the data is loaded. Dropping an image alone does not apply its data to the fields; click the read button. If the restoration data is damaged, the original input may not be recoverable.

The contents of referenced styles and files are not saved. If their contents change, the result of the next expansion changes as well.

## Automatically converting prompts to include commands

When loading an image without this extension's restoration data, a portion at the beginning or middle of a prompt that matches the current contents of a style is converted to `#include<Style Name>`. The positive prompt is matched against positive style contents, and the negative prompt against negative style contents. If only the entire prompt or its ending matches, WebUI restores it as a selected style as before. Trailing spaces and newlines are ignored when checking for an ending match.

For example, if the positive prompt in the “Hairstyle” style is `black hair, long hair`, `1girl, black hair, long hair, outdoors` is converted to `1girl, #include<Hairstyle>, outdoors`. Matching is case-sensitive and distinguishes spaces and newlines within the style text. Leading and trailing whitespace in the style text is removed before matching, consistent with include expansion. When candidates overlap at the same position, the longest text is preferred; if multiple styles have the same text, the first in the registration order is used. Repeated occurrences of the text are also converted.

Text inside existing `include`, `includefile`, `delete`, and `replace` commands is not converted. Styles with empty contents, or with one of this extension's commands or `{prompt}` in either the positive or negative field, are excluded. Styles are also excluded if their name is empty, has leading or trailing whitespace, or contains `>` or a newline.

An ending style and includes in the middle of the prompt can be used together. Conversion preserves the loaded style selection and Hires prompt fields. If the entire prompt or ending does not get restored as a style because of the combination of positive/negative prompts or WebUI settings, it remains as text. Hires prompt fields are not converted.

This feature works automatically and currently has no setting to turn it on or off. For images with this extension's restoration data, the saved original input is restored. Automatic conversion matches current style contents, so the matched style may differ from the one actually selected in the past.

## Notes

- To disable the extension, uncheck it in WebUI's extensions list, apply the change, and restart WebUI.
- Including a nonexistent style prints a warning in the WebUI console and replaces that include with an empty string. The result is also an empty string if the corresponding field in the referenced style is empty.
- If references form a cycle by repeatedly including the same styles or files, only the cyclic reference is removed and a warning is printed. References can be nested up to 100 levels, and the expanded prompt is limited to 1,000,000 characters. References that exceed the limits cannot be inserted; generation is stopped if the entire input prompt exceeds the character limit.
- A style can contain only `delete` or `replace` commands. Even if nothing remains after removing the commands, the command text in the style is not left in the prompt.

---

Copyright© Jujo Hotaru / 十条 蛍
