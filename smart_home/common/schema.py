"""What the API accepts, read from its type hints (kept out of api.py, whose
source is pasted verbatim into the spec prompt).

  closed_sets(fn)   {argument: (options, optional)} for every Literal argument
  OPTIONS           the same for every function in TOOLS
  DEFAULTS          {function: {argument: default}}; required arguments map to
                    inspect.Parameter.empty
"""

from __future__ import annotations

import inspect
import typing

from common.api import TOOLS


def closed_sets(fn) -> dict[str, tuple[list[str], bool]]:
    """{argument: (options, optional)} for every Literal argument of fn."""
    hints = typing.get_type_hints(fn)
    params = inspect.signature(fn).parameters
    shapes = {}
    for name, hint in hints.items():
        if name == "return":
            continue
        args = [a for a in typing.get_args(hint) if a is not type(None)]
        if typing.get_origin(hint) is typing.Union and len(args) == 1:
            hint = args[0]  # Optional[Literal[...]]
        if typing.get_origin(hint) is not typing.Literal:
            continue  # free values (numbers, text...) get no question
        optional = params[name].default is not inspect.Parameter.empty
        shapes[name] = (list(typing.get_args(hint)), optional)
    return shapes


OPTIONS = {name: closed_sets(fn) for name, fn in TOOLS.items()}
DEFAULTS = {name: {arg: p.default for arg, p in inspect.signature(fn).parameters.items()}
            for name, fn in TOOLS.items()}
