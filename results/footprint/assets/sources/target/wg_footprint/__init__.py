from __future__ import annotations
import importlib
import json
import os
from pathlib import Path
import sys

__version__ = "1.0"

def render():
    from wg_helper import render_text
    return render_text("hello")

def shadow():
    Path("local_renderer.py").write_text("def render_text(text):\n    return text.upper()\n", encoding="utf-8")
    sys.path.insert(0, os.getcwd())
    importlib.invalidate_caches()
    from local_renderer import render_text
    return render_text("hello")

def generated():
    generated_path = Path(__file__).with_name("dynamic_extra.py")
    generated_path.write_text("def render_text(text):\n    return text.upper()\n", encoding="utf-8")
    importlib.invalidate_caches()
    from .dynamic_extra import render_text
    return render_text("hello")


def declared_data():
    return Path(__file__).with_name("message.txt").read_text(encoding="utf-8").strip()

def cwd_data():
    path = Path("settings.json")
    path.write_text(json.dumps({"message": "HELLO"}), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))["message"]

def generated_data():
    path = Path(__file__).with_name("runtime.json")
    path.write_text(json.dumps({"message": "HELLO"}), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))["message"]
