-- Local compatibility adapter. The fragment is the unchanged official
-- GeneralEffect dissolve shader; this only binds native scene inputs/time.
local exports = exports or {}
local SeekModeScript = {}
SeekModeScript.__index = SeekModeScript

function SeekModeScript.new()
    return setmetatable({}, SeekModeScript)
end

function SeekModeScript:onStart(comp)
    self.material = comp.entity.scene:findEntityBy("passBlend3")
        :getComponent("MeshRenderer").material
end

function SeekModeScript:seekToTime(comp, time)
    if not self.material then self:onStart(comp) end
    local left = Amaz.BuiltinObject.getUserTexture("#TransitionInput0")
    local right = Amaz.BuiltinObject.getUserTexture("#TransitionInput1")
    if left and right then
        self.material:setTex("inputImageTexture", left)
        self.material:setTex("inputImageTexture2", right)
    end
    self.material:setFloat("progress", math.min(1, math.max(0, Amaz.Input.frameTimestamp)))
end

function SeekModeScript:onUpdate(comp, deltaTime)
    self:seekToTime(comp, 0)
end

exports.SeekModeScript = SeekModeScript
return exports
