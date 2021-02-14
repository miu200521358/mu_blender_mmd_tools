# -*- coding: utf-8 -*-

import bpy
import logging
import numpy as np

from miu_mmd_tools import register_wrap
from bpy.types import Operator

@register_wrap
class ExportFullVmd(Operator):
    bl_idname = 'miu_mmd_tools.curve2bone'
    bl_label = 'Curve to Bone'
    bl_description = 'カーブの制御点に沿ったボーンを出力します。'
    bl_options = {'REGISTER', 'UNDO'}

    # メニューを実行したときに呼ばれる関数
    def execute(self, context):
        level, message = self.curve2bone()
        self.report({level}, message)
        return {'FINISHED'}

    # カーブの制御点にボーン生成
    def curve2bone(self):
        D = bpy.data
        C = bpy.context

        # カーブの制御点をアーマチュアのボーンに変換する
        if not hasattr(C, 'active_object'):
            return 'ERROR', "アクティブオブジェクトなし"
        
        # 選択されているカーブオブジェクトを取得する
        active_obj = bpy.context.active_object
        
        if active_obj is None:
            # 未選択の場合、終了
            print("オブジェクト未選択")
            return 'ERROR', "オブジェクト未選択"

        print(f'active: {active_obj}')

        if active_obj.type != "CURVE":
            # カーブオブジェクトでない場合、終了
            print("カーブオブジェクト未選択")
            return 'ERROR', "カーブオブジェクト未選択"

        # カーブデータ取得
        curve = active_obj.data

        top_points = [[spline.points[0].co[0], spline.points[0].co[1], spline.points[0].co[2]] for spline in curve.splines]
        top_mean_point = np.mean(top_points, axis=0)

        if bpy.ops.object.armature_add.poll():
            # 追加したボーンはとりあえず無視
            bpy.ops.object.armature_add(radius=0.5, enter_editmode=True, align='WORLD', location=(top_mean_point[0], top_mean_point[1], top_mean_point[2]))

        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='EDIT', toggle=False)

        # 最後に追加したアーマチュアを処理対象とする
        amt = bpy.context.view_layer.objects.active.data
        print(f'amt: {amt}')
        # amt = D.armatures[-1]
        # print(f'D.armatures: {D.armatures}')
        root_bone = amt.edit_bones.active
        # print(f'mode: {C.mode}')
        # if not root_bone:
        #     if bpy.ops.object.mode_set.poll():
        #         bpy.ops.object.mode_set(mode='EDIT', toggle=False)
        #         print(f'mode2: {C.mode}')
        #         root_bone = amt.edit_bones.new('Head')
        root_bone.head = (0, 0, 1)
        root_bone.tail = (0, 0, 0)

        # カーブの制御点ごとにボーンを追加
        for sidx, spline in enumerate(curve.splines):
            # ボーン追加

            head_point = None
            parent_bone = root_bone
            for pidx, point in enumerate(spline.points):
                print(point.co)

                if pidx == 0:
                    # 根元はポイントだけ保持してスルー
                    head_point = point
                    continue

                # if pidx % 2 == 1 or pidx == len(spline.points) - 1:
                    # 1個飛ばしもしくは最後のみボーン追加

                # ボーン追加
                b = amt.edit_bones.new('Bone')
                b.head = (head_point.co[0] - top_mean_point[0], head_point.co[1] - top_mean_point[1], head_point.co[2] - top_mean_point[2])
                b.tail = (point.co[0] - top_mean_point[0], point.co[1] - top_mean_point[1], point.co[2] - top_mean_point[2])
                b.name = f'curve_bone_{sidx+1}_{pidx}'

                if parent_bone:
                    # 親ボーンが居る場合、定義
                    b.parent = parent_bone
                
                # 親ボーンとして保持
                parent_bone = b
                # 根元ボーンとして保持
                head_point = point

        return 'INFO', "ボーン追加成功"
        