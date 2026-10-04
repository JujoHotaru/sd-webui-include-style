# sd-webui-include-style

日本語 | [English](README_en.md)

## はじめに（免責事項）

- 本拡張機能は、現時点では基本的に作者が個人使用するために開発されています。
  - 仕様や動作が予告なく変更される可能性があります。
- 作者の使用範囲内での動作確認は行っていますが、作者の知らない機能や拡張機能との相性問題が存在する可能性があります。
- その他、本拡張機能を使用したことで万一なんらかの損害が発生したりした場合、作者および関係者は一切の責を負わないものとします。

## 概要

[Stable Diffusion WebUI（AUTOMATIC1111）](https://github.com/AUTOMATIC1111/stable-diffusion-webui)や、その派生である[WebUI Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge)、[Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo)などの「スタイル」機能を強化する拡張機能です。

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

includeとincludefileで取り込むテキストは、入れ子の参照を展開した後に前後のホワイトスペース（空白、タブ、改行など）を取り除きます。本文内部の空白・タブ・改行と、入力プロンプト内のコマンドの前後にあるホワイトスペースは保持します。

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

プロンプトに次のように記述すると、本文の前後のホワイトスペースを取り除いて展開されます。

```
1girl, #includefile<foobar>
```
↓

```
1girl, black hair, long hair
```

`foo/bar`のようなサブフォルダーを含む相対パスも指定でき、Windows形式の区切り文字`\`も使えます。すべてのファイル参照は`prompts`を基準に解決します。ファイル本文の前後のホワイトスペースは取り除き、本文内部の空白・タブ・改行は保持します。BOMはプロンプトに含めません。BOMがなければUTF-8として読み込み、UTF-16の推測は行いません。ファイル本文にも`#include`や`#includefile`を記述できます。入れ子の`includefile`も、常に`prompts`フォルダーを基準に展開します。ファイル本文のスタイル参照は、通常プロンプトではスタイルの`prompt`欄、Negativeプロンプトでは`negative_prompt`欄を使います。ファイル本文そのものは両方の欄で共通です。

ファイル名は`prompts`フォルダーを基準とする相対パスに限られます。`prompts`内のファイルやサブフォルダーがシンボリックリンクの場合はリンク先を読み込み、リンク先が`prompts`の外にあっても使用できます。ファイル本文内の参照も引き続き`prompts`を基準にします。絶対パス、ドライブ指定、`..`、代替データストリーム、デバイス名は指定できません。ファイルが存在しない場合、リンク切れなどで読み込みに失敗した場合、またはパスが無効な場合は、警告を出してその参照を空文字に置き換えます。

スタイル内やADetailerの追加プロンプト欄でも`#includefile`を使用できます。取り込んだ本文にも`delete`・`replace`を適用できます。ファイルを編集した内容は、次の生成に反映されます。

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

複数のreplaceがある場合は順番に置換するため、前の置換結果が次の置換対象になることがあります。適用順は、入力プロンプト欄の指定、通常・Negative欄に直接includeしたスタイルの出現順、WebUIのスタイル選択順です。空の削除対象と空の置換前文字列は無視します。

## ADetailerとの併用について

ADetailer拡張機能の「ADetailer prompt」および「ADetailer negative prompt」欄でもincludeを使用可能ですが、以下のような事前設定が必要です。

1. WebUIの「Settings」を開く
2. 「ADetailer」に移動
3. 「Script names to apply to ADetailer (separated by comma)」テキストボックスに移動
4. 既存の指定を残して、カンマ区切りで`includestyle`を追加（空欄なら`includestyle`だけを入力）
5. 「Apply Settings」を実行

例えば「ADetailer prompt」に`$include<黒髪ロング>`、「ADetailer negative prompt」に`$include<標準Negative指定>`を入力します。ADetailerのバージョンやWebUIとの組み合わせによって処理順が異なるため、更新後は追加処理のプロンプトが展開されることを確認してください。

## 生プロンプトの保存と復元

通常・Negative欄または選択したスタイルで本拡張機能のコマンドを使って生成に成功すると、画像に次の復元情報を保存します。

- includeなどを展開する前の通常プロンプト
- 展開する前のNegativeプロンプト
- 生成時に選択していたスタイル

どちらかの欄でコマンドを使った場合も、両欄とスタイル選択をまとめて保存します。複数枚生成した場合は、各画像に対応する入力を保存します。改行・引用符・前後の空白も保持します。画像の通常の生成情報には、生成に使用した展開後のプロンプトも残ります。

PNG・JPEG・WebPで利用できます。WebUIのメタデータ保存設定を有効にしてください。

Forge Neoで復元する手順は次のとおりです。

1. 画像を通常のプロンプト欄へドロップします。画像の生成情報全体が入力されます。
2. 「Read generation parameters...」ボタンを押します。
3. 通常・Negative欄の生プロンプトと選択スタイルが復元されます。他の生成設定もWebUIの通常の読み込み操作で反映されます。

PNG Infoからtxt2img・img2imgへ送る操作でも復元できます。生成時にスタイルを選んでいなかった場合は、読み戻し時のスタイル選択も解除されます。画像をドロップしただけでは各欄へ反映されないため、読み込みボタンを押してください。復元情報が壊れている場合は、元の入力を復元できないことがあります。

参照先のスタイル・ファイルの本文は保存しません。参照先の内容が変わると次回の展開結果も変わります。

## 生成情報からのinclude自動変換

本拡張機能の復元情報がない画像を読み込む場合、プロンプトの先頭や途中に現在のスタイル本文と一致する部分があれば、`#include<スタイル名>`へ変換します。通常欄はスタイルの通常欄、Negative欄はスタイルのNegative欄と照合します。全文や末尾だけが一致する場合は、従来どおりWebUIのスタイル選択として復元します。末尾の空白や改行は、末尾一致の判定で無視します。

例えば「髪型」スタイルの通常欄が`black hair, long hair`なら、`1girl, black hair, long hair, outdoors`を`1girl, #include<髪型>, outdoors`に変換します。大文字・小文字と本文内部の空白・改行を区別し、本文の前後空白はincludeの展開規則に合わせて除いて照合します。同じ位置で重なる候補は長い本文を優先し、同じ本文のスタイルが複数ある場合は登録順で選びます。繰り返し出現する本文も変換します。

既存のinclude・includefile・delete・replaceコマンドの内部は変換しません。空の本文と、通常・Negative欄のいずれかに本拡張機能のコマンドまたは`{prompt}`を含むスタイルは、自動変換の対象外です。名前が空、前後に空白がある、`>`または改行を含むスタイルも対象外です。

末尾のスタイル指定と途中のincludeは併用できます。変換しても、読み込まれたスタイル選択やHires欄は変わりません。通常・Negative欄の組み合わせやWebUIの設定によって全文・末尾の一致がスタイルとして復元されない場合は、本文のまま残します。Hires欄は自動変換の対象外です。

この機能は自動で動作し、現在はオン・オフを切り替える設定画面はありません。本拡張機能の復元情報がある画像では、保存した元の入力を復元します。自動変換は現在のスタイル本文との一致を使うため、過去に実際に選択したスタイルとは異なる場合があります。

## 注意事項

- 本拡張機能を無効化する場合は、WebUIの拡張機能一覧でチェックを外し、変更を適用して再起動してください。
- 存在しないスタイルをincludeすると、WebUIのコンソールに警告を出し、そのincludeを空文字に置き換えます。参照先の対応する欄が空の場合も、空文字になります。
- 同じスタイルやファイルを参照し続ける循環がある場合は、循環した参照だけを取り除き、警告を出します。参照の入れ子は100段、展開後のプロンプトは1,000,000文字までです。制限を超えた参照は取り込めず、入力プロンプト全体が文字数上限を超える場合は生成を中断します。
- delete・replaceの指示だけを含むスタイルも使用できます。指示を取り除いた後の内容が空でも、スタイル内の指示文字列は残りません。

---

Copyright© Jujo Hotaru / 十条 蛍
