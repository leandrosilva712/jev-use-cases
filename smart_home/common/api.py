"""The smart-home API that both Jev and the LLM baseline call.

Plain typed functions, as in TypeSafe's function-calling cookbook: every
argument Jev can fill is a Literal (a closed set of options). An argument with
a default is optional; when the command doesn't mention it, the default stands.

The bodies only echo the call: the PoC scores which call is chosen, it doesn't
drive real devices.
"""

from __future__ import annotations

from typing import Literal, Optional

LightAction = Literal["on", "off", "brighter", "dimmer", "color"]
Room = Literal[
    "kitchen", "living room", "bedroom", "bathroom", "dining room", "hallway",
    "office", "den", "garage", "porch", "patio", "balcony", "garden", "all",
]
Color = Literal["red", "orange", "yellow", "green", "blue", "purple", "pink", "white"]
Drink = Literal["regular", "espresso", "cappuccino", "latte", "americano"]
PlugAction = Literal["on", "off"]
SpeakerAction = Literal["volume_up", "volume_down", "mute"]


def lights(
    action: LightAction,
    room: Optional[Room] = None,
    color: Optional[Color] = None,
) -> str:
    """Control the smart lights: switch them on or off, change brightness or colour."""
    return _echo("lights", action=action, room=room, color=color)


def vacuum(room: Optional[Room] = None) -> str:
    """Start the robot vacuum cleaner, optionally in one room."""
    return _echo("vacuum", room=room)


def coffee(drink: Drink = "regular") -> str:
    """Make a coffee with the coffee machine."""
    return _echo("coffee", drink=drink)


def plug(action: PlugAction) -> str:
    """Switch the smart plug (wemo socket) on or off."""
    return _echo("plug", action=action)


def speaker(action: SpeakerAction) -> str:
    """Change the speaker volume or mute it."""
    return _echo("speaker", action=action)


TOOLS = {fn.__name__: fn for fn in (lights, vacuum, coffee, plug, speaker)}

# Routing option for commands that need no function (questions, chit-chat...).
NO_CALL = "no_call"


def _echo(name: str, **arguments) -> str:
    shown = ", ".join(f'{k}="{v}"' for k, v in arguments.items() if v is not None)
    return f"{name}({shown})"
