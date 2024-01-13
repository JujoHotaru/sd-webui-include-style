# sd-webui-include-style

## 概要

Stable Diffusion Automatic1111 WebUIの「スタイル」機能を拡張します。

プロンプトで`#include<スタイル名>`という構文を記述することで、特定のスタイルの内容をプロンプト内に取り込むことができます。

通常のプロンプト欄・NegativePrompt欄のほか、ADetailer拡張機能の追加プロンプト欄に対応。また、Dynamic Prompts拡張機能と併用ができます。  
スタイル内でも使用できますので、複数スタイル間で共用される要素を別要素に括り出して管理するといったことも可能です。

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
教室で黒髪ロングの女の子,"1girl, #include<黒髪ロング>, in school, wearing school uniform","#include<標準Negative指定>"
name,prompt,negative_prompt
ロングヘアー,"long hair"
黒髪ロング,"black hair, #include<ロングヘアー>"
標準Negative指定,"","EasyNegative, bad face"
```

上記のように記述した状態で、「教室で黒髪ロングの女の子」のスタイルを適用して生成すると、結果のプロンプトは以下のようになります。

```
Prompt : 1girl, black hair, long hair, in school, wearing school uniform
Negative prompt : EasyNegative, bad face
```

ADetailer拡張機能の「ADetailer prompt」および「ADetailer negative prompt」欄でもincludeを使用可能です。
