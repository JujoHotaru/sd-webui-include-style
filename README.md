# sd-webui-include-style

Stable Diffusion Automatic1111 WebUIの「スタイル」機能を拡張します。

プロンプトで`#include<スタイル名>`という構文を記述することで、特定のスタイルの内容をプロンプト内に取り込むことができます。

通常のプロンプト欄・NegativePrompt欄のほか、ADetailerの追加プロンプト欄に対応。また、Dynamic Promptと併用ができます。  
スタイル内でも使用できますので、複数スタイル間で共用される要素を別要素に括り出して管理するといったことも可能です。
