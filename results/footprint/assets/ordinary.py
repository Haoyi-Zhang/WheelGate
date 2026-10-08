import importlib.metadata as metadata
import json
import pathlib
import sys
import wg_footprint

operation, expected_helper = sys.argv[1:3]
origin = pathlib.Path(wg_footprint.__file__).resolve()
dist = metadata.distribution("wg-footprint")
owned = {pathlib.Path(dist.locate_file(item)).resolve() for item in dist.files or []}
assert origin in owned and origin.is_relative_to(pathlib.Path(sys.prefix).resolve())
if expected_helper != "none":
    try:
        observed = metadata.version("wg-helper")
    except metadata.PackageNotFoundError:
        observed = None
    if observed != expected_helper:
        print("ORDINARY_FOOTPRINT=" + json.dumps({"status":"BLOCKED", "observed":observed}))
        raise SystemExit(2)
value = getattr(wg_footprint, operation)()
assert value == "HELLO", value
print("ORDINARY_FOOTPRINT=" + json.dumps({"status":"PASS", "value":value, "origin":str(origin)}))
