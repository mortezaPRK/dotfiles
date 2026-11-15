-- Run inside Hammerspoon; all application/UI actions are mocked.
local configdir = hs.configdir
local calls = {}
local openSucceeds = true
local function record(name)
    return function() table.insert(calls, name) end
end
local fake = {
    configdir = "/example/.hammerspoon",
    reload = record("reload"),
    open = function(path)
        assert(path == "/example/.hammerspoon/init.lua")
        table.insert(calls, "open")
        return openSucceeds
    end,
    openConsole = record("console"),
    openPreferences = record("preferences"),
    task = { new = function(command, _, args)
        assert(command == "/usr/bin/open")
        assert(table.concat(args, "|") == "-a|TextEdit|/example/.hammerspoon/init.lua")
        return { start = record("fallback editor") }
    end },
}
local environment = setmetatable({ hs = fake }, { __index = _G })
local module = assert(loadfile(configdir .. "/hammerspoon_menu.lua", "t", environment))()
local entries = module.items()
local expected = {
    "Reload Config", "Open Config", "-", "Console...", "Preferences...",
}
assert(#entries == #expected)
for index, title in ipairs(expected) do
    assert(entries[index].title == title)
    if entries[index].fn then entries[index].fn() end
end
assert(table.concat(calls, "|") == "reload|open|console|preferences")
openSucceeds = false
entries[2].fn()
assert(calls[#calls] == "fallback editor")
return "Hammerspoon submenu tests passed."
