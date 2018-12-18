#!/usr/bin/env python3.7

import iterm2
# To install packages from PyPI, use this command, changing package_name to the package you
# wish to install:
#   "$$PYTHON_BIN$$/pip3" install package_name

async def main(connection):
    # Your code goes here. Here's a bit of example code that adds a tab to the current window:
    app = await iterm2.async_get_app(connection)
    window = app.current_terminal_window
    if window is not None:
        await iterm2.Window.async_create(connection)
    else:
        # You can view this message in the script console.
        print("No current window")

iterm2.run_until_complete(main)
