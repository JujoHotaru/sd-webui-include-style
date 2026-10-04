# sd-webui-include-style

Currently, Only Japanese language document is available.

## はじめに（免責事項）

- 本拡張機能は、現時点では基本的に作者が個人使用するために開発されています。
  - 仕様や動作が予告なく変更される可能性があります。
- 作者の使用範囲内での動作確認は行っていますが、作者の知らない機能や拡張機能との相性問題が存在する可能性があります。
- その他、本拡張機能を使用したことで万一なんらかの損害が発生したりした場合、作者および関係者は一切の責を負わないものとします。

## 概要

[Stable Diffusion WebUI（AUTOMATIC1111）](https://github.com/AUTOMATIC1111/stable-diffusion-webui)や、その派生である[WebUI Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge)、[Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)などの「スタイル」機能を強化する拡張機能です。WebUI本体のスクリプト機構とスタイル管理機能を利用して動作します。

プロンプトで`#include<スタイル名>`または`#includefile<ファイル名>`という構文を記述すると、スタイルやテキストファイルの内容をプロンプト内に取り込めます。

txt2img・img2imgの通常のプロンプト欄・Negative prompt欄と、スタイル内で使用できます。指定した文字列を削除する`#delete`、置換する`#replace`も使用できます。ADetailerの追加プロンプト欄で使用するには、後述の設定が必要です。Dynamic Promptsの構文と組み合わせる例も後述します。

スタイル内でも使用できますので、複数スタイル間で共通使用されている要素を別スタイルに括り出して管理するといったことも可能です（主にそれを目的として開発しました）。

## インストール

WebUIの「Extensions」-「Install from URL」を開き、「URL for extension’s git repository」に以下URLを指定してインストールできます。

```
https://github.com/JujoHotaru/sd-webui-include-style
```

インストール後は、WebUIを再起動してください。拡張機能専用の設定画面や操作パネルはありません。有効になっていれば、生成時にプロンプトの構文を処理します。

## 構文

以下の4種類の構文を使用できます。いずれも先頭の`#`を`$`または`%`に変更できます。コマンド名は小文字で記述してください。

| 構文 | 動作 |
| --- | --- |
| `#include<スタイル名>` | 入力した位置にスタイルの内容を取り込む |
| `#includefile<ファイル名>` | `prompts`フォルダー内のテキストファイルを入力した位置に取り込む |
| `#delete<削除する文字列>` | 対象の文字列をすべて削除する |
| `#replace<置換前\|置換後>` | 対象の文字列をすべて置換する |

`#include < スタイル名 >`のように、コマンドと`<`の間や引数の前後に空白を入れられます。引数の前後の空白は取り除かれますが、途中の空白はそのまま扱われます。スタイル名と削除・置換対象は、大文字と小文字を区別します。

引数に`>`は使用できません。`replace`の置換前に`|`は使用できません。これらの区切り文字をエスケープする書式はありません。

Forge系など、`#`をコメントとして扱う環境や他の拡張機能と構文が競合する環境では、`$include<スタイル名>`や`%include<スタイル名>`などを使用してください。

## includeの使用例

参照するスタイルは、WebUIのスタイル保存機能などであらかじめ登録してください。以下の`styles.csv`は、スタイル名と内容の対応を示す例です。実際にはWebUIが読み込んでいるスタイルファイルを使用します。CSVを直接編集した場合は、WebUIを再起動するなどして再読み込みしてください。

スタイルが以下のような内容になっている場合の例です。

```csv
name,prompt,negative_prompt
黒髪ロング,"black hair, long hair",""
標準Negative指定,"","EasyNegative, bad face"
```

プロンプトで以下のように記述すると、指定スタイルの内容が取り込まれます。includeするだけなら、WebUIのスタイル選択欄で参照先を選ぶ必要はありません。同じスタイルを選択欄でも適用すると、内容が重複することがあります。

```
1girl, #include < 黒髪ロング >, in school, wearing school uniform
```
↓

```
1girl, black hair, long hair, in school, wearing school uniform
```

Negativeプロンプトで記述する場合は、同じスタイルの`negative_prompt`のほうを取り込みます。通常のプロンプト欄で記述した場合は、`prompt`だけを取り込みます。両方を使用する場合は、それぞれの欄にincludeを記述してください。

```
#include<標準Negative指定>
```
↓

```
EasyNegative, bad face
```

スタイル内で他のスタイルを参照することもできます。参照したスタイルがさらに別のスタイルをincludeすることも可能です。  
includeで指定するスタイルを、そのincludeを使っているスタイルより後で定義していてもかまいません。  
以下の例では、「黒髪ロング」スタイルを、それをincludeしている「教室で黒髪ロングの女の子」スタイルより後で定義しています。また、「黒髪ロング」スタイルは、さらに「ロングヘアー」スタイルをincludeしています。

```csv
name,prompt,negative_prompt
教室で黒髪ロングの女の子,"1girl, #include<黒髪ロング>, in school, wearing school uniform","#include<標準Negative指定>"
ロングヘアー,"long hair",""
黒髪ロング,"black hair, #include<ロングヘアー>",""
標準Negative指定,"","EasyNegative, bad face"
```

上記のように記述した状態で、「教室で黒髪ロングの女の子」のスタイルを適用して生成すると、結果のプロンプトは以下のようになります。

```
Prompt : 1girl, black hair, long hair, in school, wearing school uniform
Negative prompt : EasyNegative, bad face
```

include結果は単純な文字列置換で、カンマなどの区切り文字を追加しません。このため強調構文やDynamic Promptsの構文と組み合わせることができます。展開は生成時に行われ、入力欄の表示やスタイルファイルの内容を書き換える機能はありません。

以下の例では`黒髪ロング`で置換されるプロンプト（`black hair, long hair`）を強度1.3倍に指定しています。

```csv
name,prompt,negative_prompt
教室で黒髪ロングの女の子,"1girl, (#include<黒髪ロング>:1.3), in school, wearing school uniform","#include<標準Negative指定>"
ロングヘアー,"long hair",""
黒髪ロング,"black hair, #include<ロングヘアー>",""
標準Negative指定,"","EasyNegative, bad face"
```

以下の例では、Dynamic Promptsを使って髪色を4色および髪の長さ2種類からランダムに選択されるよう指定しています。

```csv
name,prompt,negative_prompt
教室にいる女の子,"1girl, {#include<ロングヘアー>|#include<ショートヘアー>}, in school, wearing school uniform","#include<標準Negative指定>"
髪の色ランダム,"{black|pink|blonde|white} hair",""
ロングヘアー,"#include<髪の色ランダム>, long hair",""
ショートヘアー,"#include<髪の色ランダム>, short hair",""
標準Negative指定,"","EasyNegative, bad face"
```

ランダム選択はDynamic Prompts側で行います。本拡張機能はその前にincludeを展開します。他の拡張機能との併用結果は、各拡張機能のバージョンと処理順序にも依存します。

WebUI標準のスタイル機能にある`{prompt}`は、include自体では展開しません。例えば`prefix, {prompt}, suffix`をincludeすると、`{prompt}`を含む文字列をそのまま挿入します。入力プロンプトを囲む用途では、そのスタイルをWebUIのスタイル選択欄から適用してください。

## includefileの使用例

拡張機能の`prompts`フォルダーにUTF-8形式（BOM可）、またはBOM付きUTF-16LE／UTF-16BE形式のテキストファイルを置き、拡張子を省略して`#includefile<foobar>`のように指定します。`.txt`を付けた`#includefile<foobar.txt>`も使用できます。例えば`prompts/foobar.txt`に次の本文を保存します。

```text
black hair, long hair
```

プロンプトに次のように記述すると、本文がそのまま展開されます。

```
1girl, #includefile<foobar>
```
↓

```
1girl, black hair, long hair
```

`foo/bar`のようなサブフォルダーを含む相対パスも指定でき、Windows形式の区切り文字`\`も使えます。すべてのファイル参照は`prompts`を基準に解決します。ファイル本文の前後空白や改行は保持され、BOMはプロンプトに含めません。BOMがなければUTF-8として読み込み、UTF-16の推測は行いません。ファイル本文にも`#include`や`#includefile`を記述できます。入れ子の`includefile`も、常に`prompts`フォルダーを基準に展開します。ファイル本文のスタイル参照は、通常プロンプトではスタイルの`prompt`欄、Negativeプロンプトでは`negative_prompt`欄を使います。ファイル本文そのものは両方の欄で共通です。

ファイル名は`prompts`フォルダーを基準とする相対パスに限られます。`prompts`内のファイルやサブフォルダーがシンボリックリンクの場合はリンク先を読み込み、リンク先が`prompts`の外にあっても使用できます。ファイル本文内の参照も引き続き`prompts`を基準にします。絶対パス、ドライブ指定、`..`、代替データストリーム、デバイス名は指定できません。ファイルが存在しない場合、リンク切れなどで読み込みに失敗した場合、またはパスが無効な場合は、警告を出してその参照を空文字に置き換えます。

スタイル内やADetailerの生成情報にも`#includefile`を記述できます。ファイル内の参照を展開した後に、プロンプト欄やスタイルから集めた`delete`・`replace`を適用します。ファイル本文の読み込み内容は1回の生成処理内で共有され、次の生成処理では再読み込みされます。

## delete・replaceの使用例

前述の「黒髪ロング」スタイルを使用した場合、次のように記述できます。

| 入力プロンプト | 展開後のプロンプト |
| --- | --- |
| `#delete<, long hair>#include<黒髪ロング>` | `black hair` |
| `#replace<black hair\|pink hair>#include<黒髪ロング>` | `pink hair, long hair` |
| `#replace<black\|pink>#delete<, long hair>#include<黒髪ロング>` | `pink hair` |

処理順序は、構文の記述位置にかかわらず「`include`・`includefile`の展開 → deleteによる削除 → replaceによる置換」です。通常のプロンプト欄の指定は通常のプロンプトに、Negativeプロンプト欄の指定はNegativeプロンプトに適用されます。指定は、展開したファイル本文やincludeした内容、WebUIの選択欄から適用するスタイルの内容にも作用します。

delete・replaceはスタイル内にも記述できます。使用するスタイルに含まれる指定は、そのスタイルの内容だけでなく、同じ側の入力プロンプトと他のスタイルの内容にも適用されます。

削除・置換は、タグの区切りや単語境界を考慮しない部分文字列の処理です。例えば`#delete<hair>`は、`long hair`だけでなく`hairpin`内の`hair`も削除します。正規表現としては扱いません。余ったカンマや空白の整理も行いません。上の削除例では、区切りの`, `も削除対象に含めています。

複数のreplaceがある場合は順番に置換するため、前の置換結果が次の置換対象になることがあります。指示は入力プロンプト欄から先に取り出し、その後、通常・Negativeの入力欄に書かれた直接のinclude参照順、最後にWebUIのスタイル選択順で取り出します。空の削除対象と空の置換前文字列は無視します。

## ADetailerとの併用について

ADetailer拡張機能の「ADetailer prompt」および「ADetailer negative prompt」欄でもincludeを使用可能ですが、以下のような事前設定が必要です。

1. WebUIの「Settings」を開く
2. 「ADetailer」に移動
3. 「Script names to apply to ADetailer (separated by comma)」テキストボックスに移動
4. 既存の指定を残して、カンマ区切りで`includestyle`を追加（空欄なら`includestyle`だけを入力）
5. 「Apply Settings」を実行

`includestyle`はスクリプトのファイル名から拡張子を除いた名前です。画面上のタイトルである`IncludeStyle`ではありません。この設定により、ADetailerが追加の画像処理を行う際にも本拡張機能を実行できるようにします。[ADetailerのスクリプト選択処理](https://github.com/Bing-su/adetailer/blob/main/scripts/%21adetailer.py)も、この名前を使用します。

例えば「ADetailer prompt」に`$include<黒髪ロング>`、「ADetailer negative prompt」に`$include<標準Negative指定>`を入力します。ADetailerのバージョンやWebUIとの組み合わせによって処理順が異なるため、更新後は追加処理のプロンプトが展開されることを確認してください。

## 注意事項

- 本拡張機能を無効化する場合は、WebUIの拡張機能一覧でチェックを外し、変更を適用して再起動してください。
- 存在しないスタイルをincludeすると、WebUIのコンソールに警告を出し、そのincludeを空文字に置き換えます。参照先の対応する欄が空の場合も、空文字になります。
- 循環するincludeは検出され、循環した参照だけが警告付きで空文字に置き換わります。展開深度は100、展開後の文字列は1,000,000文字までです。制限を超えるスタイル参照は警告付きで空文字になります。入力プロンプトの展開やdelete・replaceの結果が上限を超える場合は、本拡張機能の前処理をエラーとして中断し、共有スタイルと入力プロンプトを変更しません。
- delete・replaceの指示だけを含むスタイルも使用できます。指示を取り除いた後の内容が空でも、スタイル内の指示文字列は残りません。
- `prompt`と`negative_prompt`がリスト形式の場合は各要素を展開します。同じ生成処理のリスト全体に、入力欄と参照スタイルから集めた共通のdelete・replace指示を適用します。値が`None`の欄は空文字として扱います。
- スタイル辞書は生成処理中だけ差し替え、`postprocess`または処理オブジェクトの`close`で元の辞書オブジェクトへ戻します。ADetailerが終了処理を省略する内部コピーの状態も、元の生成処理が終了するときに復元します。復元にはホストが元の生成処理の`postprocess`または`close`を呼ぶことが必要です。
- ADetailerの追加処理でも本拡張機能を実行させるため、前述のスクリプト指定が必要です。保存する生成情報の`ADetailer prompt`、`ADetailer negative prompt`と、末尾に番号が付いた同形式の項目でもincludeとincludefileを展開します。番号は`2`のような数値と、`2nd`・`3rd`・`4th`のような序数の両方に対応します。

---

Copyright© Jujo Hotaru / 十条 蛍
