--
name: reverse
description: Reverse a string
usage: reverse <string>
---

local str = table.concat(args, " ")
local reversed = string.reverse(str)

return reversed