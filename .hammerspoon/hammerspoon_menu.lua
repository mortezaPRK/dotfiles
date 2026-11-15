local M = {}
local openTask

local function openConfig()
    local path = hs.configdir .. "/init.lua"
    if hs.open(path) then return end

    -- Fall back to TextEdit if no editor handles Lua files.
    openTask = hs.task.new("/usr/bin/open", function(code, _, stderr)
        openTask = nil
        if code ~= 0 then hs.alert.show(stderr) end
    end, { "-a", "TextEdit", path })
    if openTask then openTask:start() end
end

function M.items()
    return {
        { title = "Reload Config", fn = function() hs.reload() end },
        { title = "Open Config", fn = openConfig },
        { title = "-" },
        { title = "Console...", fn = function() hs.openConsole() end },
        { title = "Preferences...", fn = function() hs.openPreferences() end },
    }
end

return M
