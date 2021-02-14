# -*- coding: utf-8 -*-
import copy

import bpy
import logging
import numpy as np

from miu_mmd_tools import register_wrap
from bpy.types import Operator

@register_wrap
class Curve2Bone(Operator):
    bl_idname = 'miu_mmd_tools.curve2bone'
    bl_label = 'カーブに沿ったボーン生成'
    bl_description = 'カーブの制御点を指定個数ごと繋いで沿ったボーンを出力します。\nオブジェクトモードでカーブを選択してから、クリックして下さい。'
    bl_options = {'REGISTER', 'UNDO'}

    join_cnt = bpy.props.IntProperty(
        name='join_cnt',
        description='制御点何個おきにボーンを生成するか',
        default=1,
        min=1,
    )

    def execute(self, context):
        level, message = self.curve2bone()
        self.report({level}, message)
        return {'FINISHED'}

    def invoke(self, context, event):
        vm = context.window_manager
        return vm.invoke_props_dialog(self)

    # カーブの制御点にボーン生成
    def curve2bone(self):
        D = bpy.data
        C = bpy.context

        # 3Dカーソルの元の位置を記録しておく(参照型のコピー)
        cursorpos = copy.copy(bpy.context.scene.cursor.location)
        # 3Dカーソルの位置をワールド原点に移動する
        bpy.context.scene.cursor.location = (0, 0, 0)
        # オブジェクトの原点を3Dカーソル位置に移動する
        bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

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

                if pidx % self.join_cnt == 0 or pidx == len(spline.points) - 1:
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

        # 3Dカーソルの位置を元に戻す
        bpy.context.scene.cursor.location = cursorpos

        return 'INFO', "ボーン追加成功"

        