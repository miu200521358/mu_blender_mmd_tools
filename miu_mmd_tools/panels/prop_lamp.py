# -*- coding: utf-8 -*-

from bpy.types import Panel

from miu_mmd_tools import register_wrap
from miu_mmd_tools.core.lamp import MMDLamp

@register_wrap
class MMDLampPanel(Panel):
    bl_idname = 'OBJECT_PT_miu_mmd_tools_lamp'
    bl_label = 'MMD Lamp Tools'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'object'

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and (MMDLamp.isLamp(obj) or MMDLamp.isMMDLamp(obj))

    def draw(self, context):
        obj = context.active_object

        layout = self.layout

        if MMDLamp.isMMDLamp(obj):
            mmd_lamp = MMDLamp(obj)
            empty = mmd_lamp.object()
            lamp = mmd_lamp.lamp()

            c = layout.column()
            c.prop(lamp.data, 'color')
            c.prop(lamp, 'location', text='Light Source')
        else:
            layout.operator('miu_mmd_tools.convert_to_mmd_lamp', text='Convert')

