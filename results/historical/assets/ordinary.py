import importlib.metadata as metadata
import pathlib
import sys
import djxml.xmlmodels
origin = pathlib.Path(djxml.xmlmodels.__file__).resolve()
dist = metadata.distribution("django-xml")
owned = {pathlib.Path(dist.locate_file(item)).resolve() for item in dist.files or []}
assert origin in owned and origin.is_relative_to(pathlib.Path(sys.prefix).resolve())
assert djxml.xmlmodels.consumer() == "available"
print("DJANGO_XML_OPERATION=available")
