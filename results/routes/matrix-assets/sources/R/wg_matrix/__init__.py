from importlib.resources import files
import json
__version__ = "0.1.0"
def consumer():
    return json.loads(files(__package__).joinpath("template.json").read_text())["message"]
def main():
    print(consumer())
