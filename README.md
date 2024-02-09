# sd-webui-include-style

Currently, Only Japanese language document is available.

## はじめに（免責事項）

- 本拡張機能は、現時点では基本的に作者が個人使用するために開発されています。
  - 仕様や動作が予告なく変更される可能性があります。
- 作者の使用範囲内での動作確認は行っていますが、作者の知らない機能や拡張機能との相性問題が存在する可能性があります。
- その他、本拡張機能を使用したことで万一なんらかの損害が発生したりした場合、作者および関係者は一切の責を負わないものとします。

## 概要

Stable Diffusion Automatic1111 WebUIの「スタイル」機能を強化します。[WebUI Forge](https://github.com/lllyasviel/stable-diffusion-webui-forge)でも動作します。

プロンプトで`#include<スタイル名>`という構文を記述することで、特定のスタイルの内容をプロンプト内に取り込むことができます。

通常のプロンプト欄・NegativePrompt欄のほか、ADetailer拡張機能の追加プロンプト欄に対応。また、Dynamic Prompts拡張機能と併用ができます。  
スタイル内でも使用できますので、複数スタイル間で共通使用されている要素を別スタイルに括り出して管理するといったことも可能です（主にそれを目的として開発しました）。

## インストール

WebUIの「Extension」-「Install from URL」を開き、「URL for extension’s git repository」に以下URLを指定してインストールできます。

```
https://github.com/JujoHotaru/sd-webui-include-style
```

## 使用例

スタイル（styles.csv）を以下のような内容にしている場合の例です。

```csv
name,prompt,negative_prompt
黒髪ロング,"black hair, long hair"
標準Negative指定,"","EasyNegative, bad face"
```

プロンプトで以下のように記述すると、指定スタイルの内容が取り込まれます。

`#include`と`<>`の間にはスペースを入れることができ、`< スタイル名 >`のようにスタイル名の前後にもスペースを入れることができます。  
スタイル名に`>`を使用することはできません。書式文字と誤認するためです。（エスケープ書式はありません）

```
1girl, #include < 黒髪ロング >, in school, wearing school uniform
```
↓
```
1girl, black hair, long hair, in school, wearing school uniform
```

Negativeプロンプトで記述する場合は、スタイルのNegative要素のほうを取り込みます。  

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
ロングヘアー,"long hair"
黒髪ロング,"black hair, #include<ロングヘアー>"
標準Negative指定,"","EasyNegative, bad face"
```

上記のように記述した状態で、「教室で黒髪ロングの女の子」のスタイルを適用して生成すると、結果のプロンプトは以下のようになります。

```
Prompt : 1girl, black hair, long hair, in school, wearing school uniform
Negative prompt : EasyNegative, bad face
```

include結果は単純な文字列置換で、カンマなど余計な文字の付与は行われません。このため強調構文と組み合わせることができますし、Dynami Promptsなど他の構文拡張機能とも併用が可能です。

以下の例では`黒髪ロング`で置換されるプロンプト（`black hair, long hair`）を強度1.3倍に指定しています。

```csv
name,prompt,negative_prompt
教室で黒髪ロングの女の子,"1girl, (#include<黒髪ロング>:1.3), in school, wearing school uniform","#include<標準Negative指定>"
ロングヘアー,"long hair"
黒髪ロング,"black hair, #include<ロングヘアー>"
標準Negative指定,"","EasyNegative, bad face"
```

以下の例では、Dynamic Promptsを使って髪色を4色および髪の長さ2種類からランダムに選択されるよう指定しています。

```
name,prompt,negative_prompt
教室にいる女の子,"1girl, {#include<ロングヘアー>|#include<ショートヘアー>}, in school, wearing school uniform","#include<標準Negative指定>"
髪の色ランダム,"{black|pink|blonde|white} hair"
ロングヘアー,"#include<髪の色ランダム>, long hair"
ショートヘアー,"#include<髪の色ランダム>, short hair"
標準Negative指定,"","EasyNegative, bad face"
```

## ADetailerとの併用について

ADetailer拡張機能の「ADetailer prompt」および「ADetailer negative prompt」欄でもincludeを使用可能ですが、以下のような事前設定が必要です。

1. WebUIの「Settings」を開く
2. 「ADetailer」に移動
3. 「Script names to apply to ADetailer (separated by comma)」テキストボックスに移動
4. テキストボックス内容の文字列の最後に「,includestyle」を追加
5. 「Apply Settings」を実行

## 注意事項

- 現在のバージョンでは、設定や拡張機能用のUIは存在しません。本拡張機能を使わない場合（無効化したい場合）は、WebUIの拡張機能一覧でチェックを外してください。
- スタイル内で自分自身をincludeすると無限ループになり、エラーチェックされていませんので記述しないようにしてください。

---

Copyright© Jujo Hotaru / 十条 蛍
