-- Keep the stock menu if the replacement fails to load.
hs.menuIcon(true)
require("hs.ipc")
hs.autoLaunch(true)
require("services").start()
