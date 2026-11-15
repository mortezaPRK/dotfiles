local M = {}
local hammerspoonMenu = require("hammerspoon_menu")
local home = os.getenv("HOME")
local command = home .. "/.local/bin/svc"
local menu, timer, refreshTask
local tasks = {}
local snapshot = { services = {} }
local busy = false
local statusImages = {}
local statusColors = {
    running = { hex = "#34C759" },
    stopped = { hex = "#8E8E93" },
    pending = { hex = "#FF9F0A" },
    failed = { hex = "#FF453A" },
}

local function openPath(path, app)
    local args = {}
    if app then args = { "-a", app } end
    table.insert(args, path)
    local task
    task = hs.task.new("/usr/bin/open", function(code, _, stderr)
        tasks[task] = nil
        if code ~= 0 then hs.alert.show(stderr) end
    end, args)
    if task then tasks[task] = true; task:start() end
end

local function notify(message)
    hs.notify.new({ title = "Services", informativeText = message }):send()
end

local function statusIcon(service)
    local state = "stopped"
    if service.status == "Unavailable" then
        state = "pending"
    elseif service.status == "Launching" or service.status == "Pending" or
        service.status == "Restarting" or service.status == "Terminating" then
        state = "pending"
    elseif service.active then
        state = service.health == "Not Ready" and "pending" or "running"
    end
    if service.status == "Error" or service.status == "Skipped" or
        (service.status == "Completed" and service.exit_code ~= 0) then
        state = "failed"
    end
    if not statusImages[state] then
        local drawing = hs.canvas.new({ x = 0, y = 0, w = 16, h = 16 })
        drawing:appendElements({
            type = "circle", action = "fill",
            center = { x = 8, y = 8 }, radius = 4.5,
            fillColor = statusColors[state],
        })
        -- Preserve status colors in light/dark menus.
        statusImages[state] = drawing:imageFromCanvas():template(false)
        drawing:delete()
    end
    return statusImages[state]
end

local function refresh()
    if refreshTask then return end
    refreshTask = hs.task.new(command, function(code, stdout, stderr)
        refreshTask = nil
        if code == 0 then
            local ok, decoded = pcall(hs.json.decode, stdout)
            if ok and decoded then snapshot = decoded end
        else
            snapshot.error = stderr ~= "" and stderr or "Unable to read service status"
        end
        if menu then menu:setTooltip(snapshot.error or "Local services") end
    end, { "status", "--json" })
    if refreshTask then refreshTask:start() end
end

local function action(verb, name)
    if busy or snapshot.busy then return end
    busy = true
    local args = { verb }
    if name then table.insert(args, name) end
    local task
    task = hs.task.new(command, function(code, stdout, stderr)
        tasks[task] = nil
        busy = false
        if code ~= 0 then
            notify((stderr ~= "" and stderr or stdout):sub(-1800))
        end
        refresh()
    end, args)
    if not task then
        busy = false
        notify("Unable to launch svc")
        return
    end
    tasks[task] = true
    task:start()
end

local function buildMenu()
    local entries = {}
    local locked = busy or snapshot.busy ~= nil
    if snapshot.error then
        table.insert(entries, { title = "Supervisor unavailable — see logs", disabled = true })
    end
    if locked then
        table.insert(entries, { title = snapshot.busy or "Operation in progress…", disabled = true })
    end
    for _, item in ipairs(snapshot.services or {}) do
        local service = item
        local children = {
            { title = "Status: " .. service.status .. (service.health ~= "-" and (" / " .. service.health) or ""), disabled = true },
            { title = "-" },
            { title = service.kind == "action" and "Run" or "Start", disabled = locked or service.active,
              fn = function() action("start", service.name) end },
            { title = "Stop", disabled = locked or not service.active,
              fn = function() action("stop", service.name) end },
            { title = "Restart", disabled = locked or service.kind == "action",
              fn = function() action("restart", service.name) end },
            { title = "Start at login", checked = service.enabled, disabled = locked,
              fn = function() action(service.enabled and "disable" or "enable", service.name) end },
        }
        if service.url then
            table.insert(children, { title = "Open web UI", fn = function() hs.urlevent.openURL(service.url) end })
        end
        if service.app then
            table.insert(children, { title = "Show application", fn = function() hs.application.open(service.app) end })
        end
        if service.log then
            table.insert(children, { title = "Open log", fn = function() openPath(service.log, "Console") end })
        end
        if service.source then
            table.insert(children, { title = "Edit definition", fn = function() openPath(service.source) end })
        end
        table.insert(entries, { title = service.title, image = statusIcon(service), menu = children })
    end
    table.insert(entries, { title = "-" })
    table.insert(entries, { title = "Manage services", menu = {
        { title = "Refresh status", fn = refresh },
        { title = "Reload definitions…", disabled = locked, fn = function()
            local button = hs.dialog.blockAlert("Reload service definitions?",
                "Running services will stop, then restart with the new definitions.", "Reload", "Cancel")
            if button == "Reload" then action("reload") end
        end },
        { title = "Open definitions", fn = function() openPath(home .. "/.config/services/definitions") end },
    } })
    table.insert(entries, { title = "Hammerspoon", menu = hammerspoonMenu.items() })
    return entries
end

function M.start()
    if menu then return M end
    menu = hs.menubar.new()
    local gear = assert(hs.image.imageFromName("NSActionTemplate"), "System gear icon unavailable")
    menu:setIcon(gear:size({ w = 18, h = 18 }):template(true))
    menu:setTooltip("Services")
    menu:setMenu(buildMenu)
    timer = hs.timer.doEvery(5, refresh)
    refresh()
    -- Hide the stock icon after its replacement is ready.
    hs.menuIcon(false)
    return M
end

function M.status()
    return snapshot
end

function M.menu()
    return buildMenu()
end

return M
