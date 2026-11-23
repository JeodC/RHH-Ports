import os
import time
from threading import Lock
from typing import Any, Dict, Optional

import sdl2


class Input:
    _instance: Optional["Input"] = None

    _key_mapping = {
        sdl2.SDL_CONTROLLER_BUTTON_A: "A",
        sdl2.SDL_CONTROLLER_BUTTON_B: "B",
        sdl2.SDL_CONTROLLER_BUTTON_X: "X",
        sdl2.SDL_CONTROLLER_BUTTON_Y: "Y",
        sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: "L1",
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: "R1",
        sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK: "L3",
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK: "R3",
        sdl2.SDL_CONTROLLER_BUTTON_BACK: "SELECT",
        sdl2.SDL_CONTROLLER_BUTTON_START: "START",
        sdl2.SDL_CONTROLLER_BUTTON_GUIDE: "MENUF",
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP: "DY-",
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN: "DY+",
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT: "DX-",
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT: "DX+",
    }

    _axis_mapping = {
        sdl2.SDL_CONTROLLER_AXIS_LEFTX: "DX",
        sdl2.SDL_CONTROLLER_AXIS_LEFTY: "DY",
        sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT: "L2",
        sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT: "R2",
    }

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(Input, cls).__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self._input_lock = Lock()

        self._keys_pressed: set[str] = set()
        self._frame_pressed: set[str] = set()
        self._next_repeat: Dict[str, float] = {}  # held keys

        # Key repeat settings
        self._initial_delay = 0.35
        self._repeat_interval = 0.07

        # Enable controller events
        self._load_controller_mappings()
        sdl2.SDL_GameControllerEventState(sdl2.SDL_ENABLE)
        sdl2.SDL_JoystickEventState(sdl2.SDL_ENABLE)

        # Open controllers
        self.controllers: list[Any] = []

        num_controllers = sdl2.SDL_NumJoysticks()
        print(f"Found {num_controllers} controller(s)")

        for i in range(num_controllers):
            if sdl2.SDL_IsGameController(i):
                controller = sdl2.SDL_GameControllerOpen(i)
                if controller:
                    name = sdl2.SDL_GameControllerName(controller).decode("utf-8")
                    self.controllers.append(controller)
                    print(f"Found game controller {i}: {name}")
            else:
                print(f"Joystick {i} is not a recognized game controller")

        if not self.controllers:
            print("No game controllers found.")
            raise RuntimeError("No game controllers found.")

    def controller_mapping(self) -> str:
        """SDL mapping string in use by the first opened controller"""
        mapping = sdl2.SDL_GameControllerMapping(self.controllers[0])
        return mapping.decode("utf-8", "replace") if mapping else ""

    def _load_controller_mappings(self) -> None:
        """Load controller mappings from environment variable or fallback file."""
        config_path = sdl2.SDL_getenv(b"SDL_GAMECONTROLLERCONFIG")
        if config_path:
            config_str = config_path.decode("utf-8")

            # SDL has already read an inline mapping
            if "," in config_str and not config_str.endswith((".txt", ".cfg")):
                return
            if os.path.exists(config_str):
                result = sdl2.SDL_GameControllerAddMappingsFromFile(config_str.encode("utf-8"))
                if result == -1:
                    print(f"Warning: Could not load file {config_str}: {sdl2.SDL_GetError().decode()}")
                else:
                    print(f"Loaded {result} controller mappings from file {config_str}")
            else:
                print(f"Warning: Controller config file {config_str} not found")
        else:
            print("No controller mappings loaded - using SDL defaults")

    def _add_key_pressed(self, key_name: str) -> None:
        """Add a key to the pressed set"""
        with self._input_lock:
            # A stick past the deadzone sends an event per movement
            if key_name in self._next_repeat:
                return
            self._keys_pressed.add(key_name)
            self._next_repeat[key_name] = time.time() + self._initial_delay

    def _remove_key_held(self, key_name: str) -> None:
        """Remove a key from the pressed set"""
        with self._input_lock:
            self._next_repeat.pop(key_name, None)

    def check_event(self, event=None) -> bool:
        """Check for input events, update key states, and return whether one was processed."""
        if event:
            # Controller button press
            if event.type == sdl2.SDL_CONTROLLERBUTTONDOWN:
                button = event.cbutton.button
                if button in self._key_mapping:
                    key_name = self._key_mapping[button]
                    self._add_key_pressed(key_name)
                    return True

            # Controller button release
            elif event.type == sdl2.SDL_CONTROLLERBUTTONUP:
                button = event.cbutton.button

                # Clear the key if it was pressed
                if button in self._key_mapping:
                    key_name = self._key_mapping[button]
                    self._remove_key_held(key_name)

            # Controller axis motion
            elif event.type == sdl2.SDL_CONTROLLERAXISMOTION:
                axis = event.caxis.axis
                value = event.caxis.value

                if axis in self._axis_mapping:
                    key_name = self._axis_mapping[axis]

                    # Past deadzone: register a direction press
                    if abs(value) > 10000:
                        dir, opposite = ("+", "-") if value > 0 else ("-", "+")
                        self._remove_key_held(f"{key_name}{opposite}")
                        self._add_key_pressed(f"{key_name}{dir}")
                        return True

                    # Reset when axis returns to center
                    elif abs(value) < 5000:
                        self._remove_key_held(f"{key_name}+")
                        self._remove_key_held(f"{key_name}-")

        return False

    def key(self, key_name: str, repeat: bool = False) -> bool:
        """Check if a key is pressed. With repeat, a held key counts again at the repeat interval."""
        with self._input_lock:
            is_pressed = key_name in self._frame_pressed
            self._frame_pressed.discard(key_name)

            if repeat and not is_pressed and time.time() >= self._next_repeat.get(key_name, float("inf")):
                self._next_repeat[key_name] = time.time() + self._repeat_interval
                is_pressed = True

            return is_pressed

    def handle_navigation(self, selected_position: int, items_per_page: int, total_items: int) -> int:
        """Handle navigation based on pressed keys"""
        last = total_items - 1
        if self.key("DY+", repeat=True):  # DOWN
            return 0 if selected_position >= last else selected_position + 1
        if self.key("DY-", repeat=True):  # UP
            return last if selected_position <= 0 else selected_position - 1
        for key_name, step in (
            ("DX+", items_per_page),
            ("DX-", -items_per_page),
            ("R1", items_per_page),
            ("L1", -items_per_page),
            ("R2+", 100),
            ("L2+", -100),
        ):
            if self.key(key_name, repeat=True):
                return max(0, min(selected_position + step, last))

        return selected_position

    def begin_frame(self) -> None:
        """Take the keys pressed since the last frame"""
        with self._input_lock:
            self._frame_pressed, self._keys_pressed = self._keys_pressed, set()

    def cleanup(self) -> None:
        """Clean up SDL resources"""
        with self._input_lock:
            for controller in self.controllers:
                sdl2.SDL_GameControllerClose(controller)

            self.controllers = []
            self._keys_pressed = set()
            self._frame_pressed = set()
            self._next_repeat = {}
