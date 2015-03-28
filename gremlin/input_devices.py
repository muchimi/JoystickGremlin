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

import functools
import logging

from PyQt5 import QtCore
import sdl2

from gremlin import event_handler, macro, util
from gremlin.util import SingletonDecorator, convert_sdl_hat, extract_ids
from gremlin.error import GremlinError
from vjoy.vjoy import VJoy


class CallbackRegistry(object):

    """Registry of all callbacks known to the system."""

    def __init__(self):
        self._registry = {}

    def add(self, callback, event, mode="global", always_execute=False):
        device_id = util.device_id(event)
        function_name = callback.__name__

        if device_id not in self._registry:
            self._registry[device_id] = {}
        if mode not in self._registry[device_id]:
            self._registry[device_id][mode] = {}

        if event not in self._registry[device_id][mode]:
            self._registry[device_id][mode][event] = {}
        if function_name not in self._registry[device_id][mode][event]:
            self._registry[device_id][mode][event][function_name] = \
                (callback, always_execute)
        else:
            logging.warning("Function with name {} exists multiple"
                            " times".format(function_name))

    @property
    def registry(self):
        return self._registry

    def clear(self):
        self._registry = {}


# Global registry of all registered callbacks
callback_registry = CallbackRegistry()


class VJoyProxy(object):

    """Manages the usage of vJoy and allows shared access all
    callbacks."""

    vjoy_devices = {}

    def __getitem__(self, key):
        """Returns the requested vJoy instance.

        :param key id of the vjoy device
        :return the corresponding vjoy device
        """
        if key in VJoyProxy.vjoy_devices:
            return VJoyProxy.vjoy_devices[key]
        else:
            if not isinstance(key, int):
                raise TypeError("Integer ID expected")

            device = VJoy(key)
            VJoyProxy.vjoy_devices[key] = device
            return device


class JoystickWrapper(object):

    """Wraps SDL2 joysticks and presents an API similar to vjoy."""

    def __init__(self, jid):
        """Creates a new wrapper object for the given object id.

        :param jid the id of the joystick instance to wrap
        """
        if jid > sdl2.joystick.SDL_NumJoysticks():
            raise GremlinError("No device with the provided ID exist")
        self._joystick = sdl2.SDL_JoystickOpen(jid)

    def windows_id(self):
        """Returns the system id of the wrapped joystick.

        :return system id of this device
        """
        return sdl2.joystick.SDL_JoystickInstanceID(self._joystick)

    def axis(self, index):
        """Returns the current value of the axis with the given index.

        The index is 1 based, i.e. the first axis starts with index 1.

        :param index the index of the axis to return to value of
        :return the current value of the axis
        """
        return sdl2.SDL_JoystickGetAxis(self._joystick, index-1) / float(32768)

    def button(self, index):
        """Returns the current state of the button with the given index.

        The index is 1 based, i.e. the first button starts with index 1.

        :param index the index of the axis to return to value of
        :return the current state of the button
        """
        return sdl2.SDL_JoystickGetButton(self._joystick, index-1)

    def hat(self, index):
        """Returns the current state of the hat with the given index.

        The index is 1 based, i.e. the first hat starts with index 1.

        :param index the index of the hat to return to value of
        :return the current state of the hat
        """
        return convert_sdl_hat(sdl2.SDL_JoystickGetHat(
            self._joystick, index-1)
        )


class JoystickProxy(object):

    """Allows read access to joystick state information."""

    # Dictionary of initialized joystick devices
    joystick_devices = {}

    def __getitem__(self, key):
        """Returns the requested joystick instance.

        If the joystick instance exists it is returned directly,
        otherwise it is first created and then returned.

        :param key id of the joystick device
        :return the corresponding joystick device
        """
        if key in JoystickProxy.joystick_devices:
            return JoystickProxy.joystick_devices[key]
        else:
            if type(key) != int:
                raise TypeError("Integer ID expected")
            if key > sdl2.joystick.SDL_NumJoysticks():
                raise GremlinError("No device with the provided ID exist")

            # The id used to open the device is not the same as the
            # system_id reported by SDL, hence we grab all devices and
            # store them using their system_id
            for i in range(sdl2.joystick.SDL_NumJoysticks()):
                joy = JoystickWrapper(i)
                JoystickProxy.joystick_devices[joy.windows_id()] = joy
            return JoystickProxy.joystick_devices[key]


class VJoyPlugin(object):

    """Plugin providing automatic access to the VJoyProxy object.

    For a function to use this plugin it requires one of its parameters
    to be named "vjoy".
    """

    vjoy = VJoyProxy()

    def __init__(self):
        self.keyword = "vjoy"

    def install(self, callback, signature):
        """Decorates the given callback function to provide access to
        the VJoyProxy object.

        Only if the signature contains the plugin's keyword is the
        decorator applied.

        :param callback the callback to decorate
        :param signature the signature of the original callback
        :return either the original callback or the newly decorated
            version
        """
        if self.keyword not in signature.parameters:
            return callback

        @functools.wraps(callback)
        def wrapper(*args, **kwargs):
            kwargs[self.keyword] = VJoyPlugin.vjoy
            callback(*args, **kwargs)

        return wrapper


class JoystickPlugin(object):

    """Plugin providing automatic access to the JoystickProxy object.

    For a function to use this plugin it requires one of its parameters
    to be named "joy".
    """

    joystick = JoystickProxy()

    def __init__(self):
        self.keyword = "joy"

    def install(self, callback, signature):
        """Decorates the given callback function to provide access
        to the JoystickProxy object.

        Only if the signature contains the plugin's keyword is the
        decorator applied.

        :param callback the callback to decorate
        :param signature the signature of the original callback
        :return either the original callback or the newly decorated
            version
        """
        if self.keyword not in signature.parameters:
            return callback

        @functools.wraps(callback)
        def wrapper(*args, **kwargs):
            kwargs[self.keyword] = JoystickPlugin.joystick
            callback(*args, **kwargs)

        return wrapper


@SingletonDecorator
class Keyboard(QtCore.QObject):

    """Provides access to the keyboard state."""

    def __init__(self):
        """Initialises a new object."""
        QtCore.QObject.__init__(self)
        self._keyboard_state = {}

    @QtCore.pyqtSlot(event_handler.Event)
    def keyboard_event(self, event):
        """Handles keyboard events and updates state.

        :param event the keyboard event to use to update state
        """
        key = macro.key_from_code(
            event.identifier[0],
            event.identifier[1]
        )
        self._keyboard_state[key] = event.is_pressed

    def is_pressed(self, key):
        """Returns whether or not the key is pressed.

        :param key the key to check
        :return True if the key is pressed, False otherwise
        """
        if isinstance(key, str):
            key = macro.key_from_name(key)
        elif isinstance(key, macro.Keys.Key):
            pass
        return self._keyboard_state.get(key, False)


class KeyboardPlugin(object):

    """Plugin providing automatic access to the Keyboard object.

    For a function to use this plugin it requires one of its parameters
    to be named "keyboard".
    """

    keyboard = Keyboard()

    def __init__(self):
        self.keyword = "keyboard"

    def install(self, callback, signature):
        """Decorates the given callback function to provide access to
        the Keyboard object.

        Only if the signature contains the plugin's keyword is the
        decorator applied.

        :param callback the callback to decorate
        :param signature the signature of the original callback
        :return either the original callback or the newly decorated
            version
        """
        if self.keyword not in signature.parameters:
            return callback

        @functools.wraps(callback)
        def wrapper(*args, **kwargs):
            kwargs[self.keyword] = KeyboardPlugin.keyboard
            callback(*args, **kwargs)

        return wrapper


class JoystickDecorator(object):

    """Creates customized decorators for physical joystick devices."""

    def __init__(self, name, device_id, mode="global"):
        """Creates a new instance with customized decorators.

        :param name the name of the device
        :param device_id the device id in the system
        :param mode the mode in which the decorated functions
            should be active
        """
        self.name = name
        self.mode = mode
        self.axis = functools.partial(
            axis, device_id=device_id, mode=mode
        )
        self.button = functools.partial(
            button, device_id=device_id, mode=mode
        )
        self.hat = functools.partial(
            hat, device_id=device_id, mode=mode
        )


def button(button_id, device_id, mode, always_execute=False):
    """Decorator for button callbacks.

    :param button_id the id of the button on the physical joystick
    :param device_id the id of input device
    :param mode the mode in which this callback is active
    :param always_execute if True the decorated function is executed
        even when the program is not listening to inputs
    """

    def wrap(callback):

        @functools.wraps(callback)
        def wrapper_fn(*args, **kwargs):
            callback(*args, **kwargs)

        hid, wid = extract_ids(device_id)
        event = event_handler.Event(
            event_type=event_handler.InputType.JoystickButton,
            hardware_id=hid,
            windows_id=wid,
            identifier=button_id
        )
        callback_registry.add(wrapper_fn, event, mode, always_execute)

        return wrapper_fn

    return wrap


def hat(hat_id, device_id, mode, always_execute=False):
    """Decorator for hat callbacks.

    :param hat_id the id of the button on the physical joystick
    :param device_id the id of input device
    :param mode the mode in which this callback is active
    :param always_execute if True the decorated function is executed
        even when the program is not listening to inputs
    """

    def wrap(callback):

        @functools.wraps(callback)
        def wrapper_fn(*args, **kwargs):
            callback(*args, **kwargs)

        hid, wid = extract_ids(device_id)
        event = event_handler.Event(
            event_type=event_handler.InputType.JoystickHat,
            hardware_id=hid,
            windows_id=wid,
            identifier=hat_id
        )
        callback_registry.add(wrapper_fn, event, mode, always_execute)

        return wrapper_fn

    return wrap


def axis(axis_id, device_id, mode, always_execute=False):
    """Decorator for axis callbacks.

    :param axis_id the id of the axis on the physical joystick
    :param device_id the id of input device
    :param mode the mode in which this callback is active
    :param always_execute if True the decorated function is executed
        even when the program is not listening to inputs
    """

    def wrap(callback):

        @functools.wraps(callback)
        def wrapper_fn(*args, **kwargs):
            callback(*args, **kwargs)

        hid, wid = extract_ids(device_id)
        event = event_handler.Event(
            event_type=event_handler.InputType.JoystickAxis,
            hardware_id=hid,
            windows_id=wid,
            identifier=axis_id
        )
        callback_registry.add(wrapper_fn, event, mode, always_execute)

        return wrapper_fn

    return wrap


def keyboard(key_name, mode="global", always_execute=False):
    """Decorator for keyboard key callbacks.

    :param key_name name of the key of this callback
    :param mode the mode in which this callback is active
    :param always_execute if True the decorated function is executed
        even when the program is not listening to inputs
    """

    def wrap(callback):

        @functools.wraps(callback)
        def wrapper_fn(*args, **kwargs):
            callback(*args, **kwargs)

        key = macro.key_from_name(key_name)
        event = event_handler.Event.from_key(key)
        callback_registry.add(wrapper_fn, event, mode, always_execute)

        return wrapper_fn

    return wrap


def squash(value, function):
    """Returns the appropriate function value when the function is
    squashed to [-1, 1].

    :param value the function value to compute
    :param function the function to be squashed
    :return function value at value after squashing
    """
    return (2 * function(value)) / abs(function(-1) - function(1))


def deadzone(value, low, low_center, high_center, high):
    """Returns the mapped value taking the provided deadzone into
    account.

    The following relationship between the limits has to hold.
    -1 <= low < low_center <= 0 <= high_center < high <= 1

    :param value the raw input value
    :param low low deadzone limit
    :param low_center lower center deadzone limit
    :param high_center upper center deadzone limit
    :param high high deadzone limit
    :return corrected value
    """
    if value >= 0:
        return min(1, max(0, (value - high_center) / abs(high - high_center)))
    else:
        return max(-1, min(0, (value - low_center) / abs(low - low_center)))