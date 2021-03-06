# Copyright (c) 2020 BlenderNPR and contributors. MIT license.

import math
import ctypes
import copy

import pyrr

from Malt.GL import *
from Malt.UBO import UBO
from Malt.Texture import TextureArray
from Malt.RenderTarget import ArrayLayerTarget, RenderTarget
from Malt.Render import Common


LIGHT_SUN = 1
LIGHT_POINT = 2
LIGHT_SPOT = 3

class C_Light(ctypes.Structure):
    _fields_ = [
        ('color', ctypes.c_float*3),
        ('type', ctypes.c_int32),
        ('position', ctypes.c_float*3),
        ('radius', ctypes.c_float),
        ('direction', ctypes.c_float*3),
        ('spot_angle', ctypes.c_float),
        ('spot_blend', ctypes.c_float),
        ('type_index', ctypes.c_int32),
        ('__padding', ctypes.c_int32*2),
    ]

#TODO: This values should be dynamic and configurable
max_spots = 8
spot_resolution = 2048

sun_cascades = 6
max_suns = 8 * sun_cascades
sun_resolution = 2048

max_points = 8
point_resolution = 2048

#TODO: Hard-coded for Blender conventions for now
def make_projection_matrix(fov, aspect_ratio, near, far):
    x_scale = 1.0 / math.tan(fov / 2.0)
    y_scale = x_scale * aspect_ratio
    return pyrr.Matrix44([
        x_scale, 0, 0, 0,
        0, y_scale, 0, 0,
        0, 0, (-(far + near)) / (far - near), -1,
        0, 0, (-2.0 * far * near) / (far - near), 0
    ])


class C_LightsBuffer(ctypes.Structure):
    
    _fields_ = [
        ('lights', C_Light*128),
        ('lights_count', ctypes.c_int),
        ('__padding', ctypes.c_int32*3),
        ('spot_matrices', ctypes.c_float*16*max_spots),
        ('sun_matrices', ctypes.c_float*16*max_suns),
    ]


class ShadowMaps(object):

    def __init__(self):
        self.spot_t = None
        self.spot_fbos = []

        self.sun_t = None
        self.sun_fbos = []

        self.initialized = False

    def setup(self):
        
        self.spot_t = TextureArray((spot_resolution, spot_resolution), max_spots, GL_DEPTH_COMPONENT32F)
        for i in range(self.spot_t.length):
            self.spot_fbos.append(RenderTarget(depth_stencil=ArrayLayerTarget(self.spot_t, i)))

        self.sun_t = TextureArray((sun_resolution, sun_resolution), max_suns, GL_DEPTH_COMPONENT32F)
        for i in range(self.sun_t.length):
            self.sun_fbos.append(RenderTarget(depth_stencil=ArrayLayerTarget(self.sun_t, i)))

        #self.point = TextureArray(spot_resolution, max_points, GL_DEPTH_COMPONENT32F)

        self.initialized = True

    def load(self, scene):
        if self.initialized is False:
            self.setup()


class LightsBuffer(object):
    
    def __init__(self):
        self.data = C_LightsBuffer()
        self.UBO = UBO()
        self.shadowmaps = ShadowMaps()
        self.common_buffer = Common.CommonBuffer()
    
    def load(self, scene, pipeline, pass_name, cascades_distribution_exponent):
        #TODO: Automatic distribution exponent based on FOV
        #TODO: Configurable cascades number ???

        scene = copy.copy(scene)
        real_scene_camera = scene.camera
        scene.camera = copy.deepcopy(scene.camera)
        self.shadowmaps.load(scene)
        UBOS = {
            'COMMON_UNIFORMS' : self.common_buffer
        }
        spot_count = 0
        sun_count = 0
        point_count = 0

        for i, light in enumerate(scene.lights):
            self.data.lights[i].color = light.color
            self.data.lights[i].type = light.type
            self.data.lights[i].position = light.position
            self.data.lights[i].radius = light.radius
            self.data.lights[i].direction = light.direction
            self.data.lights[i].spot_angle = light.spot_angle
            self.data.lights[i].spot_blend = light.spot_blend

            if light.type == LIGHT_SPOT:
                self.data.lights[i].type_index = spot_count

                camera_matrix = pyrr.Matrix44(light.matrix)
                
                projection_matrix = make_projection_matrix(light.spot_angle,1,0.01,light.radius)
                spot_matrix = projection_matrix * camera_matrix
                
                self.data.spot_matrices[spot_count] = tuple([e for vector in spot_matrix for e in vector])

                scene.camera.camera_matrix = light.matrix
                scene.camera.projection_matrix = tuple([e for vector in projection_matrix for e in vector])
                
                offset = pipeline.get_samples()[pipeline.sample_count]
                self.common_buffer.load(scene, (spot_resolution, spot_resolution), offset, pipeline.sample_count)

                self.shadowmaps.spot_fbos[spot_count].clear(depth=1)
                pipeline.draw_scene_pass(self.shadowmaps.spot_fbos[spot_count], 
                    scene.objects, pass_name, pipeline.default_shader[pass_name], UBOS)

                spot_count+=1
            
            if light.type == LIGHT_SUN:
                self.data.lights[i].type_index = sun_count

                sun_matrix = pyrr.Matrix44(light.matrix)
                projection_matrix = pyrr.Matrix44(real_scene_camera.projection_matrix)
                view_matrix = projection_matrix * pyrr.Matrix44(real_scene_camera.camera_matrix)

                cascades_matrices = get_sun_cascades(sun_matrix, projection_matrix, view_matrix, sun_cascades, cascades_distribution_exponent)
                
                for i, cascade in enumerate(cascades_matrices):
                    cascade = tuple([e for vector in cascade for e in vector])
                    
                    scene.camera.camera_matrix = cascade
                    scene.camera.projection_matrix = tuple([e for vector in pyrr.Matrix44.identity() for e in vector])

                    self.data.sun_matrices[sun_count * sun_cascades + i] = cascade
                
                    offset = pipeline.get_samples()[pipeline.sample_count]
                    self.common_buffer.load(scene, (sun_resolution, sun_resolution), offset, pipeline.sample_count)

                    fbo = self.shadowmaps.sun_fbos[sun_count * sun_cascades + i]
                    fbo.clear(depth=1)
                    glEnable(GL_DEPTH_CLAMP)
                    pipeline.draw_scene_pass(fbo, scene.objects, pass_name, pipeline.default_shader[pass_name], UBOS)
                    glDisable(GL_DEPTH_CLAMP)

                sun_count+=1
            
            
        self.data.lights_count = len(scene.lights)
        
        self.UBO.load_data(self.data)
    
    def bind(self, location):
        self.UBO.bind(location)

    def shader_callback(self, shader):
        shader.textures['SPOT_SHADOWMAPS'] = self.shadowmaps.spot_t
        shader.textures['SUN_SHADOWMAPS'] = self.shadowmaps.sun_t


def get_sun_cascades(sun_from_world_matrix, projection_matrix, view_from_world_matrix, cascades_count, cascades_distribution_exponent):
    cascades = []
    splits = []
    
    #if is ortho
    if projection_matrix[3][3] == 1.0:
        for i in range(cascades_count):
            split = -1.0 + (2.0 / cascades_count) * (i+1)
            splits.append(split)
    #is perspective
    else:
        clip_end = projection_matrix.inverse * pyrr.Vector4([0,0,1,1])
        clip_end /= clip_end.w
        clip_end = -clip_end.z
        
        step_size = clip_end / cascades_count
        for i in range(cascades_count):
            split = (i+1) * step_size
            projected = projection_matrix * pyrr.Vector4([0,0,-split,1])
            projected = (projected / projected.w) * (1.0 if projected.w >= 0 else -1.0)
            depth = projected.z
            #normalize depth (0,1)
            depth = depth * 0.5 + 0.5
            #make steps less linear
            depth = depth ** cascades_distribution_exponent
            #back to (-1,+1) range
            depth = depth * 2.0 - 1.0
            splits.append(depth)
        
    for i in range(len(splits)):
        near = -1
        if i > 0:
            near = splits[i-1]
        far = splits[i]
        cascades.append(sun_shadowmap_matrix(sun_from_world_matrix, view_from_world_matrix, near, far))
    
    return cascades


def frustum_corners(view_from_world_matrix, near, far):
    m = view_from_world_matrix.inverse
    corners = []

    for x in (-1, 1):
        for y in (-1, 1):
            for z in (near, far):
                v = pyrr.Vector4([x, y, z, 1])
                v = m * v
                v /= v.w
                corners.append(v)
    
    return corners

def sun_shadowmap_matrix(sun_from_world_matrix, view_from_world_matrix, near, far):
    INFINITY = float('inf')
    aabb = {
        'min': pyrr.Vector3([ INFINITY,  INFINITY,  INFINITY]),
        'max': pyrr.Vector3([-INFINITY, -INFINITY, -INFINITY])
    }
    
    for corner in frustum_corners(view_from_world_matrix, near, far):
        corner = sun_from_world_matrix * corner
        aabb['min'].x = min(aabb['min'].x, corner.x)
        aabb['min'].y = min(aabb['min'].y, corner.y)
        aabb['min'].z = min(aabb['min'].z, corner.z)
        aabb['max'].x = max(aabb['max'].x, corner.x)
        aabb['max'].y = max(aabb['max'].y, corner.y)
        aabb['max'].z = max(aabb['max'].z, corner.z)

    world_from_light_space = sun_from_world_matrix.inverse

    size = aabb['max'] - aabb['min']
    aabb['min'] = world_from_light_space * pyrr.Vector4([*aabb['min'].tolist(), 1.0])
    aabb['max'] = world_from_light_space * pyrr.Vector4([*aabb['max'].tolist(), 1.0])
    center = (aabb['min'] + aabb['max']) / 2.0
    center = pyrr.Vector3(center.tolist()[:3])

    scale = pyrr.Matrix44.from_scale(size)
    translate = pyrr.Matrix44.from_translation(center)
    
    matrix = translate * world_from_light_space * scale

    screen = pyrr.Matrix44([
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0,-1, 0,
        0, 0, 0, 1
    ])

    return screen * matrix.inverse

