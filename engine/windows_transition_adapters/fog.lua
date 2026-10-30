-- Local compatibility adapter v3, appended after the unchanged original event.lua
-- prefix (Utils, AEAdapter, AE keyframes and Main). The original Main:update
-- drives all eight original Gaussian passes and the 120 original mask images.
-- No original fragment shader or effect curve is reimplemented here.
local exports = exports or {}
local SeekModeScript = {}
SeekModeScript.__index = SeekModeScript

function SeekModeScript.new()
    return setmetatable({}, SeekModeScript)
end

function SeekModeScript:onStart(comp)
    self.scene = comp.entity.scene
    self.materials = {}
    self.textures = {}
    self.masks = {}
    self.cameras = {}
    local outputRenderer = self.scene:findEntityBy("passBlend3"):getComponent("MeshRenderer")
    self.material = outputRenderer.material

    -- Keep the template's output camera and use its known mesh/camera state as
    -- a structural template. Other original cameras are unnecessary to this
    -- effect and must not write the render targets used by the new pass chain.
    local entities = self.scene.entities
    -- Template effect controllers would otherwise rewrite these cameras/RTs
    -- during continuous export. Only this adapter controls the fog pass graph.
    for i = 0, entities:size() - 1 do
        local entity = entities:get(i)
        if entity ~= comp.entity and entity:getComponent("ScriptComponent") then
            entity:removeComponent("ScriptComponent")
        end
    end
    local outputCamera = nil
    for i = 0, entities:size() - 1 do
        local camera = entities:get(i):getComponent("Camera")
        if camera then
            if camera.entity.name == "BlendCam3" then outputCamera = camera end
            camera.entity.visible = false
        end
    end
    outputCamera.entity.visible = true
    outputCamera.renderOrder = 200
    outputCamera.layerVisibleMask = Amaz.DynamicBitset.new("10000000000000000000000000000000")
    outputRenderer.entity.layer = 31

    -- Paused native-player capture uses the restored scene render graph.
    -- Reuse its serialized RT objects as a distinct ping-pong pair; freshly
    -- created cameras or RT objects are not scheduled in this player path.
    self.compatRTs = {
        self.scene:findEntityBy("mixPassCam"):getComponent("Camera").renderTexture,
        self.scene:findEntityBy("NoiseCamera"):getComponent("Camera").renderTexture
    }
    local width = Amaz.BuiltinObject.getInputTextureWidth()
    local height = Amaz.BuiltinObject.getInputTextureHeight()
    local sourceMaterials = {
        "mixPass", "NoisePass", "passMask", "PassHighlight",
        "PassHorzBlur1", "PassVertBlur1", "PassOutput", "passBlend"
    }
    for i = 1, 8 do
        local texture = self.compatRTs[((i-1)%2)+1]
        self.textures[i] = texture

        local cameraNames = {"mixPassCam", "NoiseCamera", "maskCam", "CameraHighlight", "CameraHorzBlur", "CameraVertBlur", "CameraOutput", "BlendCam"}
        local cameraEntity = self.scene:findEntityBy(cameraNames[i])
        local camera = cameraEntity:getComponent("Camera")
        camera.renderOrder = i
        camera.renderTexture = texture
        camera.layerVisibleMask = Amaz.DynamicBitset.new("1" .. string.rep("0", i))
        cameraEntity.visible = true
        self.cameras[i] = camera
        local entity = self.scene:findEntityBy(sourceMaterials[i])
        entity.layer = i
        entity.visible = true
        local renderer = entity:getComponent("MeshRenderer")
        renderer.sortingOrder = i
        self.materials[i] = renderer.material
    end

    local owner = self
    local passNames = {"b01x", "b01y", "b02x", "b02y", "b03x", "b03y", "b04x", "b04y"}
    self.feature = {
        setUniformFloat = function(_, passName, originalType, uniformName, value)
            for i, name in ipairs(passNames) do
                if name == passName then owner.materials[i]:setFloat(uniformName, value) end
            end
        end
    }
    self.animator = {
        appear = function() end,
        gotoFrame = function(_, originalFeature, originalUniform, frame)
            if not owner.masks[frame] then
                owner.masks[frame] = owner.scene.assetMgr:SyncLoad(
                    owner.scene.assetMgr.rootDir .. string.format("fogres/mask/mask_%03d.png", frame))
            end
            owner.material:setTex("u_msk1", owner.masks[frame])
        end
    }
    self.manager = {
        getInputWidth = function() return width end,
        getInputHeight = function() return height end
    }
    Main:create(self.manager, self.animator, self.feature)
end

function SeekModeScript:seekToTime(comp, time)
    if not self.material then self:onStart(comp) end
    local left = Amaz.BuiltinObject.getUserTexture("#TransitionInput0")
    local right = Amaz.BuiltinObject.getUserTexture("#TransitionInput1")
    if not left or not right then return end
    self.materials[1]:setTex("u_tex", left)
    for i = 2, 8 do self.materials[i]:setTex("u_tex", self.textures[i - 1]) end
    self.material:setTex("u_src0", self.textures[8])
    self.material:setTex("u_src1", right)
    local progress = math.min(1, math.max(0, Amaz.Input.frameTimestamp))
    Main:update(self.manager, self.animator, self.feature, progress)
end

function SeekModeScript:onUpdate(comp, deltaTime)
    self:seekToTime(comp, 0)
end

exports.SeekModeScript = SeekModeScript
return exports
