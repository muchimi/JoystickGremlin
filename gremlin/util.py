# -*- coding: utf-8; -*-

# Copyright (C) 2015 Lionel Ott
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
from PyQt5 import QtWidgets
import re
import sdl2
import struct
import sys

import gremlin
from gremlin import error


# Flag indicating that multiple physical devices with the same name exist
g_duplicate_devices = False


class SingletonDecorator:

    """Decorator turning a class into a singleton."""

    def __init__(self, klass):
        self.klass = klass
        self.instance = None

    def __call__(self, *args, **kwargs):
        if self.instance is None:
            self.instance = self.klass(*args, **kwargs)
        return self.instance


class JoystickDeviceData(object):

    """Represents data about a joystick like input device."""

    def __init__(self, device):
        """Initializes the device data based on the given device.

        :param device pyGame joystick object
        """
        self._hardware_id = guid_to_number(sdl2.SDL_JoystickGetGUID(device))
        self._system_id = sdl2.SDL_JoystickInstanceID(device)
        self._name = sdl2.SDL_JoystickName(device).decode("utf-8")
        self._is_virtual = self._name == "vJoy Device"
        self._axes = sdl2.SDL_JoystickNumAxes(device)
        self._buttons = sdl2.SDL_JoystickNumButtons(device)
        self._hats = sdl2.SDL_JoystickNumHats(device)

    @property
    def device_id(self):
        return self._hardware_id

    @property
    def system_id(self):
        return self._system_id

    @property
    def name(self):
        return self._name

    @property
    def is_virtual(self):
        return self._is_virtual

    @property
    def axes(self):
        return self._axes

    @property
    def buttons(self):
        return self._buttons

    @property
    def hats(self):
        return self._hats


def joystick_devices():
    """Returns the list of joystick like devices.

    :return list containing information about all joystick like devices
    """
    devices = []
    for i in range(sdl2.SDL_NumJoysticks()):
        joy = sdl2.SDL_JoystickOpen(i)
        devices.append(JoystickDeviceData(joy))

    # Check if we have duplicate physical joysticks
    names = []
    for dev in [v for v in devices if not v.is_virtual]:
        names.append(dev.name)

    global g_duplicate_devices
    if len(names) != len(set(names)):
        g_duplicate_devices = True

    return devices


def script_path():
    """Returns the path to the scripts location.

    :return path to the scripts location
    """
    return os.path.dirname(os.path.realpath(sys.argv[0]))


def display_error(msg):
    """Displays the provided error message to the user.

    :param msg the error message to display
    """
    QtWidgets.QErrorMessage.qtHandler().showMessage(msg)


def format_name(name):
    """Returns the name formatted as valid python variable name.

    :param name the name to format
    :return name formatted to be suitable as a python variable name
    """
    new_name = re.sub("[ \.,:]", "_", name.lower())
    if valid_identifier(new_name):
        return new_name
    else:
        raise error.GremlinError(
            "Invalid string provided, only letters, numbers and white"
            " space supported, \"{}\".".format(new_name)
        )


def valid_identifier(name):
    """Returns whether or not a given name can be transformed into a
    valid python identifier.

    :param name the text to check
    :return True if name is a valid python identifier, false otherwise
    """
    return re.fullmatch("^[a-zA-Z0-9 _]+$", name) is not None


def valid_python_identifier(name):
    """Returns whether a given name is a valid python identifier.

    :param name the name to check for validity
    :return True if the name is a valid identifier, False otherwise
    """
    return re.match("^[^\d\W]\w*\Z", name) is not None


def clamp(value, min_val, max_val):
    """Returns the value clamped to the provided range.

    :param value the input value
    :param min_val minimum value
    :param max_val maximum value
    :return the input value clamped to the provided range
    """
    if min_val > max_val:
        min_val, max_val = max_val, min_val
    return min(max_val, max(min_val, value))


def guid_to_number(guid):
    """Converts a byte array GUID into a string.

    :param guid the byte array to convert
    :return hex string representation of the given guid
    """
    return struct.unpack(">4I", guid)[0]


def mode_list(node):
    """Returns a list of all modes based on the given node.

    :param node a node from a profile tree
    :return list of mode names
    """
    # Get profile root node
    parent = node
    while parent.parent is not None:
        parent = parent.parent
    assert(type(parent) == gremlin.profile.Profile)
    # Generate list of modes
    mode_names = []
    for device in parent.devices.values():
        mode_names.extend(device.modes.keys())

    return sorted(list(set(mode_names)))


def convert_sdl_hat(value):
    """Converts the SDL hat representation to the Gremlin one.

    :param value the hat state representation as used by SDL
    :return the hat representation corresponding to the SDL one
    """
    direction = [0, 0]
    if value & sdl2.SDL_HAT_UP:
        direction[1] = 1
    elif value & sdl2.SDL_HAT_DOWN:
        direction[1] = -1
    if value & sdl2.SDL_HAT_RIGHT:
        direction[0] = 1
    elif value & sdl2.SDL_HAT_LEFT:
        direction[0] = -1
    return tuple(direction)


def appdata_path():
    """Returns the path to the application data folder, %APPDATA%."""
    return os.path.abspath(os.path.join(
        os.getenv("APPDATA"),
        "Joystick Gremlin")
    )


def setup_appdata():
    """Initializes the data folder in the application data folder."""
    folder = appdata_path()
    if not os.path.exists(folder):
        try:
            os.mkdir(folder)
        except Exception as e:
            raise error.GremlinError(
                "Unable to create data folder: {}".format(str(e))
            )
    elif not os.path.isdir(folder):
        raise error.GremlinError("Data folder exists but is not a folder")