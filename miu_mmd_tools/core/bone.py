# -*- coding: utf-8 -*-

import bpy
from bpy.types import PoseBone

from math import pi
import math
from mathutils import Vector, Quaternion, Matrix
from miu_mmd_tools import bpyutils
from miu_mmd_tools.bpyutils import TransformConstraintOp


def remove_constraint(constraints, name):
    c = constraints.get(name, None)
    if c:
        constraints.remove(c)
        return True
    return False

def remove_edit_bones(edit_bones, bone_names):
    for name in bone_names:
        b = edit_bones.get(name, None)
        if b:
            edit_bones.remove(b)


class FnBone(object):
    AUTO_LOCAL_AXIS_ARMS = ('左肩', '左腕', '左ひじ', '左手首', '右腕', '右肩', '右ひじ', '右手首')
    AUTO_LOCAL_AXIS_FINGERS = ('親指','人指', '中指', '薬指','小指')
    AUTO_LOCAL_AXIS_SEMI_STANDARD_ARMS = ('左腕捩', '左手捩', '左肩P', '左ダミー', '右腕捩', '右手捩', '右肩P', '右ダミー')

    def __init__(self, pose_bone=None):
        if pose_bone is not None and not isinstance(pose_bone, PoseBone):
            raise ValueError
        self.__bone = pose_bone

    @classmethod
    def from_bone_id(cls, armature, bone_id):
        for bone in armature.pose.bones:
            if bone.mmd_bone.bone_id == bone_id:
                return cls(bone)
        return None

    @property
    def bone_id(self):
        mmd_bone = self.__bone.mmd_bone
        if mmd_bone.bone_id < 0:
            max_id = -1
            for bone in self.__bone.id_data.pose.bones:
                max_id = max(max_id, bone.mmd_bone.bone_id)
            mmd_bone.bone_id = max_id + 1
        return mmd_bone.bone_id

    def __get_pose_bone(self):
        return self.__bone

    def __set_pose_bone(self, pose_bone):
        if not isinstance(pose_bone, bpy.types.PoseBone):
            raise ValueError
        self.__bone = pose_bone

    pose_bone = property(__get_pose_bone, __set_pose_bone)


    @staticmethod
    def get_selected_pose_bones(armature):
        if armature.mode == 'EDIT':
            with bpyutils.select_object(armature): # update selected bones
                bpy.ops.object.mode_set(mode='EDIT') # back to edit mode
        context_selected_bones = bpy.context.selected_pose_bones or bpy.context.selected_bones or []
        bones = armature.pose.bones
        return (bones[b.name] for b in context_selected_bones if not bones[b.name].is_mmd_shadow_bone)

    @classmethod
    def load_bone_fixed_axis(cls, armature, enable=True):
        for b in cls.get_selected_pose_bones(armature):
            mmd_bone = b.mmd_bone
            mmd_bone.enabled_fixed_axis = enable
            lock_rotation = b.lock_rotation[:]
            if enable:
                axes = b.bone.matrix_local.to_3x3().transposed()
                if lock_rotation.count(False) == 1:
                    mmd_bone.fixed_axis = axes[lock_rotation.index(False)].xzy
                else:
                    mmd_bone.fixed_axis = axes[1].xzy # Y-axis
            elif all(b.lock_location) and lock_rotation.count(True) > 1 and \
                    lock_rotation == (b.lock_ik_x, b.lock_ik_y, b.lock_ik_z):
                # unlock transform locks if fixed axis was applied
                b.lock_ik_x, b.lock_ik_y, b.lock_ik_z = b.lock_rotation = (False, False, False)
                b.lock_location = b.lock_scale = (False, False, False)

    @classmethod
    def apply_bone_fixed_axis(cls, armature):
        bone_map = {}
        for b in armature.pose.bones:
            if b.is_mmd_shadow_bone or not b.mmd_bone.enabled_fixed_axis:
                continue
            mmd_bone = b.mmd_bone
            parent_tip = b.parent and not b.parent.is_mmd_shadow_bone and b.parent.mmd_bone.is_tip
            bone_map[b.name] = (mmd_bone.fixed_axis.normalized(), mmd_bone.is_tip, parent_tip)

        force_align = True
        with bpyutils.edit_object(armature) as data:
            for bone in data.edit_bones:
                if bone.name not in bone_map:
                    bone.select = False
                    continue
                fixed_axis, is_tip, parent_tip = bone_map[bone.name]
                if fixed_axis.length:
                    axes = [bone.x_axis, bone.y_axis, bone.z_axis]
                    direction = fixed_axis.normalized().xzy
                    idx, val = max([(i, direction.dot(v)) for i, v in enumerate(axes)], key=lambda x: abs(x[1]))
                    idx_1, idx_2 = (idx+1)%3, (idx+2)%3
                    axes[idx] = -direction if val < 0 else direction
                    axes[idx_2] = axes[idx].cross(axes[idx_1])
                    axes[idx_1] = axes[idx_2].cross(axes[idx])
                    if parent_tip and bone.use_connect:
                        bone.use_connect = False
                        bone.head = bone.parent.head
                    if force_align:
                        tail = bone.head + axes[1].normalized()*bone.length
                        if is_tip or (tail - bone.tail).length > 1e-4:
                            for c in bone.children:
                                if c.use_connect:
                                    c.use_connect = False
                                    if is_tip:
                                        c.head = bone.head
                        bone.tail = tail
                    bone.align_roll(axes[2])
                    bone_map[bone.name] = tuple(i!=idx for i in range(3))
                else:
                    bone_map[bone.name] = (True, True, True)
                bone.select = True

        for bone_name, locks in bone_map.items():
            b = armature.pose.bones[bone_name]
            b.lock_location = (True, True, True)
            b.lock_ik_x, b.lock_ik_y, b.lock_ik_z = b.lock_rotation = locks

    @classmethod
    def load_bone_local_axes(cls, armature, enable=True):
        for b in cls.get_selected_pose_bones(armature):
            mmd_bone = b.mmd_bone
            mmd_bone.enabled_local_axes = enable
            if enable:
                axes = b.bone.matrix_local.to_3x3().transposed()
                mmd_bone.local_axis_x = axes[0].xzy
                mmd_bone.local_axis_z = axes[2].xzy

    @classmethod
    def apply_bone_local_axes(cls, armature):
        bone_map = {}
        for b in armature.pose.bones:
            if b.is_mmd_shadow_bone or not b.mmd_bone.enabled_local_axes:
                continue
            mmd_bone = b.mmd_bone
            bone_map[b.name] = (mmd_bone.local_axis_x, mmd_bone.local_axis_z)

        with bpyutils.edit_object(armature) as data:
            for bone in data.edit_bones:
                if bone.name not in bone_map:
                    bone.select = False
                    continue
                local_axis_x, local_axis_z = bone_map[bone.name]
                cls.update_bone_roll(bone, local_axis_x, local_axis_z)
                bone.select = True

    @classmethod
    def update_bone_roll(cls, edit_bone, mmd_local_axis_x, mmd_local_axis_z):
        axes = cls.get_axes(mmd_local_axis_x, mmd_local_axis_z)
        idx, val = max([(i, edit_bone.vector.dot(v)) for i, v in enumerate(axes)], key=lambda x: abs(x[1]))
        edit_bone.align_roll(axes[(idx-1)%3 if val < 0 else (idx+1)%3])

    @staticmethod
    def get_axes(mmd_local_axis_x, mmd_local_axis_z):
        x_axis = Vector(mmd_local_axis_x).normalized().xzy
        z_axis = Vector(mmd_local_axis_z).normalized().xzy
        y_axis = z_axis.cross(x_axis).normalized()
        z_axis = x_axis.cross(y_axis).normalized() # correction
        return (x_axis, y_axis, z_axis)

    @classmethod
    def apply_auto_bone_roll(cls, armature):
        bone_names = []
        for b in armature.pose.bones:
            if (not b.is_mmd_shadow_bone and
                    not b.mmd_bone.enabled_local_axes and
                    cls.has_auto_local_axis(b.mmd_bone.name_j)):
                bone_names.append(b.name)
        with bpyutils.edit_object(armature) as data:
            for bone in data.edit_bones:
                if bone.name not in bone_names:
                    select = False
                    continue
                cls.update_auto_bone_roll(bone)
                bone.select = True

    @classmethod
    def update_auto_bone_roll(cls, edit_bone):
        # make a triangle face (p1,p2,p3)
        p1 = edit_bone.head.copy()
        p2 = edit_bone.tail.copy()
        p3 = p2.copy()
        # translate p3 in xz plane
        # the normal vector of the face tracks -Y direction
        xz = Vector((p2.x - p1.x, p2.z - p1.z))
        xz.normalize()
        theta = math.atan2(xz.y, xz.x)
        norm = edit_bone.vector.length
        p3.z += norm * math.cos(theta)
        p3.x -= norm * math.sin(theta)
        # calculate the normal vector of the face
        y = (p2 - p1).normalized()
        z_tmp = (p3 - p1).normalized()
        x = y.cross(z_tmp) # normal vector
        # z = x.cross(y)
        cls.update_bone_roll(edit_bone, y.xzy, x.xzy)

    @classmethod
    def has_auto_local_axis(cls, name_j):
        if name_j:
            if (name_j in cls.AUTO_LOCAL_AXIS_ARMS or
                    name_j in cls.AUTO_LOCAL_AXIS_SEMI_STANDARD_ARMS):
                return True
            for finger_name in cls.AUTO_LOCAL_AXIS_FINGERS:
                if finger_name in name_j:
                    return True
        return False

    @staticmethod
    def patch_rna_idprop(pose_bones):
        if bpy.app.version < (2, 81, 0): # workaround for Rigify conflicts (fixed in Blender 2.81)
            from rna_prop_ui import rna_idprop_ui_get
            for b in pose_bones:
                rna_idprop_ui_get(b, create=True)

    @classmethod
    def clean_additional_transformation(cls, armature):
        # clean constraints
        for p_bone in armature.pose.bones:
            p_bone.mmd_bone.is_additional_transform_dirty = True
            constraints = p_bone.constraints
            remove_constraint(constraints, 'mmd_additional_rotation')
            remove_constraint(constraints, 'mmd_additional_location')
            if remove_constraint(constraints, 'mmd_additional_parent'):
                p_bone.bone.use_inherit_rotation = True
        # clean shadow bones
        shadow_bone_types = {
            'DUMMY',
            'SHADOW',
            'ADDITIONAL_TRANSFORM',
            'ADDITIONAL_TRANSFORM_INVERT',
        }
        def __is_at_shadow_bone(b):
            return b.is_mmd_shadow_bone and b.mmd_shadow_bone_type in shadow_bone_types
        shadow_bone_names = [b.name for b in armature.pose.bones if __is_at_shadow_bone(b)]
        if len(shadow_bone_names) > 0:
            with bpyutils.edit_object(armature) as data:
                remove_edit_bones(data.edit_bones, shadow_bone_names)
        cls.patch_rna_idprop(armature.pose.bones)

    @classmethod
    def apply_additional_transformation(cls, armature):

        def __is_dirty_bone(b):
            if b.is_mmd_shadow_bone:
                return False
            mmd_bone = b.mmd_bone
            if mmd_bone.has_additional_rotation or mmd_bone.has_additional_location:
                return True
            return mmd_bone.is_additional_transform_dirty
        dirty_bones = [b for b in armature.pose.bones if __is_dirty_bone(b)]

        # setup constraints
        shadow_bone_pool = []
        for p_bone in dirty_bones:
            sb = cls.__setup_constraints(p_bone)
            if sb:
                shadow_bone_pool.append(sb)

        # setup shadow bones
        with bpyutils.edit_object(armature) as data:
            edit_bones = data.edit_bones
            for sb in shadow_bone_pool:
                sb.update_edit_bones(edit_bones)

        pose_bones = armature.pose.bones
        for sb in shadow_bone_pool:
            sb.update_pose_bones(pose_bones)

        # finish
        for p_bone in dirty_bones:
            p_bone.mmd_bone.is_additional_transform_dirty = False
        cls.patch_rna_idprop(armature.pose.bones)

    @classmethod
    def __setup_constraints(cls, p_bone):
        bone_name = p_bone.name
        mmd_bone = p_bone.mmd_bone
        influence = mmd_bone.additional_transform_influence
        target_bone = mmd_bone.additional_transform_bone
        mute_rotation = not mmd_bone.has_additional_rotation #or p_bone.is_in_ik_chain
        mute_location = not mmd_bone.has_additional_location

        constraints = p_bone.constraints
        if not target_bone or (mute_rotation and mute_location) or influence == 0:
            rot = remove_constraint(constraints, 'mmd_additional_rotation')
            loc = remove_constraint(constraints, 'mmd_additional_location')
            if rot or loc:
                return _AT_ShadowBoneRemove(bone_name)
            return None

        shadow_bone = _AT_ShadowBoneCreate(bone_name, target_bone)

        def __config(name, mute, map_type, value):
            if mute:
                remove_constraint(constraints, name)
                return
            c = TransformConstraintOp.create(constraints, name, map_type)
            c.target = p_bone.id_data
            shadow_bone.add_constraint(c)
            TransformConstraintOp.update_min_max(c, value, influence)

        __config('mmd_additional_rotation', mute_rotation, 'ROTATION', pi)
        __config('mmd_additional_location', mute_location, 'LOCATION', 100)

        return shadow_bone

    def update_additional_transform_influence(self):
        p_bone = self.__bone
        influence = p_bone.mmd_bone.additional_transform_influence
        constraints = p_bone.constraints
        c = constraints.get('mmd_additional_rotation', None)
        TransformConstraintOp.update_min_max(c, pi, influence)
        c = constraints.get('mmd_additional_location', None)
        TransformConstraintOp.update_min_max(c, 100, influence)


class _AT_ShadowBoneRemove:
    def __init__(self, bone_name):
        self.__shadow_bone_names = ('_dummy_' + bone_name, '_shadow_' + bone_name)

    def update_edit_bones(self, edit_bones):
        remove_edit_bones(edit_bones, self.__shadow_bone_names)

    def update_pose_bones(self, pose_bones):
        pass

class _AT_ShadowBoneCreate:
    def __init__(self, bone_name, target_bone_name):
        self.__dummy_bone_name = '_dummy_' + bone_name
        self.__shadow_bone_name = '_shadow_' + bone_name
        self.__bone_name = bone_name
        self.__target_bone_name = target_bone_name
        self.__constraint_pool = []

    def __is_well_aligned(self, bone0, bone1):
        return bone0.x_axis.dot(bone1.x_axis) > 0.99 and bone0.y_axis.dot(bone1.y_axis) > 0.99

    def __update_constraints(self, use_shadow=True):
        subtarget = self.__shadow_bone_name if use_shadow else self.__target_bone_name
        for c in self.__constraint_pool:
            c.subtarget = subtarget

    def add_constraint(self, constraint):
        self.__constraint_pool.append(constraint)

    def update_edit_bones(self, edit_bones):
        bone = edit_bones[self.__bone_name]
        target_bone = edit_bones[self.__target_bone_name]
        if bone != target_bone and self.__is_well_aligned(bone, target_bone):
            _AT_ShadowBoneRemove(self.__bone_name).update_edit_bones(edit_bones)
            return

        dummy_bone_name = self.__dummy_bone_name
        dummy = edit_bones.get(dummy_bone_name, None)
        if dummy is None:
            dummy = edit_bones.new(name=dummy_bone_name)
            dummy.layers = [x == 9 for x in range(len(dummy.layers))]
            dummy.use_deform = False
        dummy.parent = target_bone
        dummy.head = target_bone.head
        dummy.tail = dummy.head + bone.tail - bone.head
        dummy.roll = bone.roll

        shadow_bone_name = self.__shadow_bone_name
        shadow = edit_bones.get(shadow_bone_name, None)
        if shadow is None:
            shadow = edit_bones.new(name=shadow_bone_name)
            shadow.layers = [x == 8 for x in range(len(shadow.layers))]
            shadow.use_deform = False
        shadow.parent = target_bone.parent
        shadow.head = dummy.head
        shadow.tail = dummy.tail
        shadow.roll = bone.roll

    def update_pose_bones(self, pose_bones):
        if self.__shadow_bone_name not in pose_bones:
            self.__update_constraints(use_shadow=False)
            return

        dummy_p_bone = pose_bones[self.__dummy_bone_name]
        dummy_p_bone.is_mmd_shadow_bone = True
        dummy_p_bone.mmd_shadow_bone_type = 'DUMMY'

        shadow_p_bone = pose_bones[self.__shadow_bone_name]
        shadow_p_bone.is_mmd_shadow_bone = True
        shadow_p_bone.mmd_shadow_bone_type = 'SHADOW'

        if 'miu_mmd_tools_at_dummy' not in shadow_p_bone.constraints:
            c = shadow_p_bone.constraints.new('COPY_TRANSFORMS')
            c.name = 'miu_mmd_tools_at_dummy'
            c.target = dummy_p_bone.id_data
            c.subtarget = dummy_p_bone.name
            c.target_space = 'POSE'
            c.owner_space = 'POSE'

        self.__update_constraints()


# ボーン関係親子のペア
DISPLAY_BONE_PAIR = {
    "腰": ["グルーブ", "センター"],
    "下半身": ["腰", "グルーブ", "センター"],
    "上半身": ["上半身先", "上半身2", "グルーブ", "センター"],
    "上半身2": ["首"],
    "首": ["頭"],
    "頭": ["頭先"],
    "肩.L": ["腕.L"],
    "腕.L": ["ひじ.L"],
    "ひじ.L": ["手首.L"],
    "手首.L": ["手首先.L"],
    "親指０.L": ["親指１.L"],
    "親指１.L": ["親指２.L"],
    "親指２.L": ["親指先.L"],
    "人指０.L": ["人指１.L"],
    "人指１.L": ["人指２.L"],
    "人指２.L": ["人指３.L"],
    "人指３.L": ["人指先.L"],
    "中指０.L": ["中指１.L"],
    "中指１.L": ["中指２.L"],
    "中指２.L": ["中指３.L"],
    "中指３.L": ["中指先.L"],
    "薬指０.L": ["薬指１.L"],
    "薬指１.L": ["薬指２.L"],
    "薬指２.L": ["薬指３.L"],
    "薬指３.L": ["薬指先.L"],
    "小指０.L": ["小指１.L"],
    "小指１.L": ["小指２.L"],
    "小指２.L": ["小指３.L"],
    "小指３.L": ["小指先.L"],
    "足.L": ["ひざ"],
    "ひざ.L": ["足首.L"],
    "足首.L": ["つま先.L"],
    "肩.R": ["腕.R"],
    "腕.R": ["ひじ.R"],
    "ひじ.R": ["手首.R"],
    "手首.R": ["手首先.R"],
    "親指０.R": ["親指１.R"],
    "親指１.R": ["親指２.R"],
    "親指２.R": ["親指先.R"],
    "人指０.R": ["人指１.R"],
    "人指１.R": ["人指２.R"],
    "人指２.R": ["人指３.R"],
    "人指３.R": ["人指先.R"],
    "中指０.R": ["中指１.R"],
    "中指１.R": ["中指２.R"],
    "中指２.R": ["中指３.R"],
    "中指３.R": ["中指先.R"],
    "薬指０.R": ["薬指１.R"],
    "薬指１.R": ["薬指２.R"],
    "薬指２.R": ["薬指３.R"],
    "薬指３.R": ["薬指先.R"],
    "小指０.R": ["小指１.R"],
    "小指１.R": ["小指２.R"],
    "小指２.R": ["小指３.R"],
    "小指３.R": ["小指先.R"],
    "足.R": ["ひざ"],
    "ひざ.R": ["足首.R"],
    "足首.R": ["つま先.R"],
}

# 軸計算用のX軸取得
def get_global_x_axis(bone: bpy.types.Bone):
    if bone.name not in DISPLAY_BONE_PAIR:
        return bone.vector.normalized()

    for cbone in bone.children_recursive:
        if cbone.name in DISPLAY_BONE_PAIR[bone.name]:
            return (cbone.head - bone.head).normalized()

    return bone.vector.normalized()
    
# クォータニオンをローカル軸の回転量に分離
def separate_local_qq(qq: Quaternion, bone: bpy.types.Bone):
    if bone.name.endswith(".R"):
        # 右手系
        return separate_local_qq_by_right(qq, bone) 
    elif bone.name.endswith(".L"):
        # 左手系
        return separate_local_qq_by_right(qq, bone) 

    # ローカル座標系（ボーンベクトルが（1，0，0）になる空間）の向き
    local_axis = Vector((1, 0, 0))

    global_x_axis = get_global_x_axis(bone)
    
    # グローバル座標系（Ａスタンス）からローカル座標系（ボーンベクトルが（0，0，1）になる空間）への変換
    global2local_qq = global_x_axis.rotation_difference(local_axis)
    local2global_qq = local_axis.rotation_difference(global_x_axis)

    # Z成分を抽出する ------------

    mat_z1_r1 = Matrix.Identity(3)
    mat_z1_r1.rotate(qq)

    mat_z1_vec = (mat_z1_r1.to_4x4() @ global_x_axis).normalized()

    # YZの回転量（自身のねじれを無視する）
    xy_qq = global_x_axis.rotation_difference(mat_z1_vec)

    # 除去されたX成分を求める
    mat_z2 = Matrix.Identity(3)
    mat_z2.rotate(qq)

    mat_z3 = Matrix.Identity(3)
    mat_z3.rotate(xy_qq)

    z_qq = (mat_z2 @ mat_z3.inverted()).to_quaternion()

    # XY回転からY成分を抽出する --------------

    mat_y1_r1 = Matrix.Identity(3)
    mat_y1_r1.rotate(xy_qq)
    mat_y1_r1.rotate(global2local_qq)

    mat_y1_vec = (mat_y1_r1.to_4x4() @ local_axis).normalized()
    mat_y1_vec.y = 0

    # ローカル軸からZを潰した移動への回転量
    local_z_qq = local_axis.rotation_difference(mat_y1_vec)

    # ボーンローカル座標系の回転をグローバル座標系の回転に戻す
    mat_y2_r1 = Matrix.Identity(3)
    mat_y2_r1.rotate(local_z_qq)
    mat_y2_r1.rotate(local2global_qq)

    y_qq = mat_y2_r1.to_quaternion()

    # XY回転からX成分だけ取り出す -----------
    
    mat_x1_r1 = Matrix.Identity(3)
    mat_x1_r1.rotate(xy_qq)

    mat_x1_r2 = Matrix.Identity(3)
    mat_x1_r2.rotate(y_qq)

    mat_x2_qq = (mat_x1_r1 @ mat_x1_r2.inverted()).to_quaternion()

    # X成分の捻れが混入したので、XY回転からYZ回転を取り出すことでXキャンセルをかける。

    mat_x3_r1 = Matrix.Identity(3)
    mat_x3_r1.rotate(mat_x2_qq)  
    
    mat_x3_vec = (mat_x3_r1.to_4x4() @ global_x_axis).normalized()

    x_qq = global_x_axis.rotation_difference(mat_x3_vec)

    # Zを再度求める -------------

    mat_z4_r1 = Matrix.Identity(3)
    mat_z4_r1.rotate(qq)

    mat_z4_r2 = Matrix.Identity(3)
    mat_z4_r2.rotate(y_qq)

    mat_z4_r3 = Matrix.Identity(3)
    mat_z4_r3.rotate(x_qq)

    z_qq = (mat_z4_r2.inverted() @ mat_z4_r1 @ mat_z4_r3.inverted()).to_quaternion()

    return x_qq, y_qq, z_qq

# クォータニオンをローカル軸の回転量に分離(右手系)
def separate_local_qq_by_right(qq: Quaternion, bone: bpy.types.Bone):
    # ローカル座標系（ボーンベクトルが（1，0，0）になる空間）の向き
    local_axis = Vector((1, 0, 0))

    global_x_axis = get_global_x_axis(bone)

    # グローバル座標系（Ａスタンス）からローカル座標系（ボーンベクトルが（0，0，1）になる空間）への変換
    global2local_qq = global_x_axis.rotation_difference(local_axis)
    local2global_qq = local_axis.rotation_difference(global_x_axis)

    # Y成分を抽出する ------------

    mat_y1_r1 = Matrix.Identity(3)
    mat_y1_r1.rotate(qq)

    mat_y1_vec = (mat_y1_r1.to_4x4() @ global_x_axis).normalized()

    # XZの回転量（自身のねじれを無視する）
    xz_qq = global_x_axis.rotation_difference(mat_y1_vec)

    # 除去されたX成分を求める
    mat_y2 = Matrix.Identity(3)
    mat_y2.rotate(qq)

    mat_y3 = Matrix.Identity(3)
    mat_y3.rotate(xz_qq)

    y_qq = (mat_y2 @ mat_y3.inverted()).to_quaternion()

    # XZ回転からX成分を抽出する --------------

    mat_x1_r1 = Matrix.Identity(3)
    mat_x1_r1.rotate(xz_qq)
    mat_x1_r1.rotate(global2local_qq)

    mat_x1_vec = (mat_x1_r1.to_4x4() @ local_axis).normalized()
    mat_x1_vec.x = 0

    # ローカル軸からZを潰した移動への回転量
    local_z_qq = local_axis.rotation_difference(mat_x1_vec)

    # ボーンローカル座標系の回転をグローバル座標系の回転に戻す
    mat_x2_r1 = Matrix.Identity(3)
    mat_x2_r1.rotate(local_z_qq)
    mat_x2_r1.rotate(local2global_qq)

    x_qq = mat_x2_r1.to_quaternion()

    # XZ回転からZ成分だけ取り出す -----------
    
    mat_z1_r1 = Matrix.Identity(3)
    mat_z1_r1.rotate(xz_qq)

    mat_z1_r2 = Matrix.Identity(3)
    mat_z1_r2.rotate(x_qq)

    mat_z2_qq = (mat_z1_r1 @ mat_z1_r2.inverted()).to_quaternion()

    # Y成分の捻れが混入したので、XY回転からYZ回転を取り出すことでXキャンセルをかける。

    mat_z3_r1 = Matrix.Identity(3)
    mat_z3_r1.rotate(mat_z2_qq)
    
    mat_z3_vec = (mat_z3_r1.to_4x4() @ global_x_axis).normalized()

    z_qq = global_x_axis.rotation_difference(mat_z3_vec)

    # Yを再度求める -------------

    mat_y4_r1 = Matrix.Identity(3)
    mat_y4_r1.rotate(qq)

    mat_y4_r2 = Matrix.Identity(3)
    mat_y4_r2.rotate(x_qq)

    mat_y4_r3 = Matrix.Identity(3)
    mat_y4_r3.rotate(z_qq)

    y_qq = (mat_y4_r1 @ mat_y4_r2.inverted() @ mat_y4_r3.inverted()).to_quaternion()

    return z_qq, y_qq, x_qq

# クォータニオンをローカル軸の回転量に分離(左手系)
def separate_local_qq_by_left(qq: Quaternion, bone: bpy.types.Bone):
    # ローカル座標系（ボーンベクトルが（1，0，0）になる空間）の向き
    local_axis = Vector((1, 0, 0))

    global_x_axis = get_global_x_axis(bone)

    # グローバル座標系（Ａスタンス）からローカル座標系（ボーンベクトルが（0，0，1）になる空間）への変換
    global2local_qq = global_x_axis.rotation_difference(local_axis)
    local2global_qq = local_axis.rotation_difference(global_x_axis)

    # X成分を抽出する ------------

    mat_x1_r1 = Matrix.Identity(3)
    mat_x1_r1.rotate(qq)

    mat_x1_vec = (mat_x1_r1.to_4x4() @ global_x_axis).normalized()

    # YZの回転量（自身のねじれを無視する）
    yz_qq = global_x_axis.rotation_difference(mat_x1_vec)

    # 除去されたX成分を求める
    mat_x2 = Matrix.Identity(3)
    mat_x2.rotate(qq)

    mat_x3 = Matrix.Identity(3)
    mat_x3.rotate(yz_qq)

    x_qq = (mat_x2 @ mat_x3.inverted()).to_quaternion()

    # YZ回転からZ成分を抽出する --------------

    mat_z1_r1 = Matrix.Identity(3)
    mat_z1_r1.rotate(yz_qq)
    mat_z1_r1.rotate(global2local_qq)

    mat_z1_vec = (mat_z1_r1.to_4x4() @ local_axis).normalized()
    mat_z1_vec.z = 0

    # ローカル軸からZを潰した移動への回転量
    local_z_qq = local_axis.rotation_difference(mat_z1_vec)

    # ボーンローカル座標系の回転をグローバル座標系の回転に戻す
    mat_z2_r1 = Matrix.Identity(3)
    mat_z2_r1.rotate(local_z_qq)
    mat_z2_r1.rotate(local2global_qq)

    z_qq = mat_z2_r1.to_quaternion()

    # YZ回転からY成分だけ取り出す -----------
    
    mat_y1_r1 = Matrix.Identity(3)
    mat_y1_r1.rotate(yz_qq)

    mat_y1_r2 = Matrix.Identity(3)
    mat_y1_r2.rotate(z_qq)

    mat_y2_qq = (mat_y1_r1 @ mat_y1_r2.inverted()).to_quaternion()

    # X成分の捻れが混入したので、YZ回転からX回転を取り出すことでXキャンセルをかける。

    mat_y3_r1 = Matrix.Identity(3)
    mat_y3_r1.rotate(mat_y2_qq)
    
    mat_y3_vec = (mat_y3_r1.to_4x4() @ global_x_axis).normalized()

    y_qq = global_x_axis.rotation_difference(mat_y3_vec)

    # Xを再度求める -------------

    mat_z4_r1 = Matrix.Identity(3)
    mat_z4_r1.rotate(qq)

    mat_z4_r2 = Matrix.Identity(3)
    mat_z4_r2.rotate(y_qq)

    mat_z4_r3 = Matrix.Identity(3)
    mat_z4_r3.rotate(z_qq)

    x_qq = (mat_z4_r2.inverted() @ mat_z4_r1 @ mat_z4_r3.inverted()).to_quaternion()

    return x_qq, y_qq, z_qq