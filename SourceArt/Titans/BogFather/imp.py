import bpy,glob,os
bpy.ops.wm.read_factory_settings(use_empty=True)
src='/workspace/bogfather/src/'
bpy.ops.import_scene.fbx(filepath=glob.glob(src+'*.fbx')[0],use_anim=True,automatic_bone_orientation=False)
tex=os.path.abspath(glob.glob(src+'*.fbm/*.JPEG')[0])
img=bpy.data.images.load(tex)
meshes=[o for o in bpy.data.objects if o.type=='MESH']
arms=[o for o in bpy.data.objects if o.type=='ARMATURE']
mats=set()
for o in meshes:
  if not o.data.materials:
    o.data.materials.append(bpy.data.materials.new('BogFather_Mat'))
  for m in o.data.materials:
    m.use_nodes=True; nt=m.node_tree
    b=next((n for n in nt.nodes if n.type=='BSDF_PRINCIPLED'),None) or nt.nodes.new('ShaderNodeBsdfPrincipled')
    t=next((n for n in nt.nodes if n.type=='TEX_IMAGE'),None) or nt.nodes.new('ShaderNodeTexImage')
    t.image=img; nt.links.new(t.outputs['Color'],b.inputs['Base Color'])
    out=next((n for n in nt.nodes if n.type=='OUTPUT_MATERIAL'),None) or nt.nodes.new('ShaderNodeOutputMaterial')
    if not out.inputs[0].is_linked: nt.links.new(b.outputs[0],out.inputs[0])
    mats.add(m.name)
bpy.context.view_layer.update()
zs=[(o.matrix_world@v.co).z for o in meshes for v in o.data.vertices]
h=max(zs)-min(zs)
e=bpy.data.objects.new('Scale_Note_80m',None); bpy.context.scene.collection.objects.link(e)
e['target_height_m']=80.0; e['native_height_m']=round(h,3); e['note']='Keep Tripo native scale; scale to 80 m later'
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath='/workspace/bogfather/blend/BogFather_import.blend')
bones=[b.name for a in arms for b in a.data.bones]
r=f"""# BogFather import report
- FBX: {glob.glob(src+'*.fbx')[0]}
- Texture: {tex} (packed into blend, wired to Principled Base Color)
- Armatures: {[a.name for a in arms]}, bones: {len(bones)}
- Bone sample: {bones[:25]}
- Meshes: {len(meshes)} {[o.name for o in meshes]}; tris/polys: {sum(len(o.data.polygons) for o in meshes)} polys, UV layers: {[ [u.name for u in o.data.uv_layers] for o in meshes]}
- Materials: {sorted(mats)}
- Actions: {[a.name for a in bpy.data.actions]}; NLA tracks: {sum(len(o.animation_data.nla_tracks) for o in bpy.data.objects if o.animation_data)}
- Measured height: {h:.3f} m (Blender units). Target 80 m -> scale x{80/h:.1f} later.
- Blend: /workspace/bogfather/blend/BogFather_import.blend
"""
open('/workspace/bogfather/IMPORT_REPORT.md','w').write(r); print(r)
