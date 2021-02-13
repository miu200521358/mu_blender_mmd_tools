miu_mmd_tools 
===========

# fork元

[blender_mmd_tools](https://github.com/powroupi/blender_mmd_tools/)

# パネル

- 右側のパネル群の「miu」パネル

# 機能

## 多段ボーン出力機能

- 指定されたボーンを、移動三軸・回転三軸に分けて出力する
    - 指定はパネル内の「`多段対象ボーン選択`」のチェックボックスで指定する
- 読み込み先モデルは事前に多段化しておくこと
    - [BoneDoublerX](http://www.paperguitar.com/mmd-related-items/135-bonedobulerx.html) を使うと便利
    - 移動三軸：`ボーン名`MY、`ボーン名`MX、`ボーン名`MZ の順番で登録
    - 回転三軸：`ボーン名`RY、`ボーン名`RX、`ボーン名`RZ の順番で登録

