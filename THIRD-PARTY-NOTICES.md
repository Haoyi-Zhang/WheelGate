# Third-party inputs and notices

Four wheel archives are included as local inputs. The provenance recorded in
`third_party/manifest.json` identifies setuptools 78.1.1 as an official PyPI
download whose whole-archive SHA-256 matches the published wheel hash.
pip 25.1.1, Pygments 2.19.1, and latex2pydata 0.5.0 were retained from the
execution runtime, not retrieved from PyPI during this study. The manifest
records each archive's local SHA-256 and size; `corpus/registry-comparison.json`
records the setuptools match and the other three whole-archive hash mismatches.
Neither the cause of those three differences nor uncompressed-payload
equivalence was established. Those three archives remain retained local inputs,
not verified publisher downloads.

The archives retain their upstream licence files. `third_party/license-index.json`
identifies the licence members found inside each archive. Preserve those notices
when redistributing the research package, and do not upload the retained wheels
to a package index.

The bundled `IEEEtran.cls` and `IEEEtran.bst` retain their original copyright
and distribution notices. No font files are distributed. Paper references and
case records link to public primary material; the package does not claim rights
in those external publications or discussions.

## Source-executed comparison tools

`third_party/source/` retains unmodified check-wheel-contents 0.6.1,
wheel-filename 1.4.2, and check-manifest 0.50 source files with their MIT
licences. `third_party/source/manifest.json` records each retrieval URL, Git blob
SHA-1, local SHA-256, and byte count. Their host-side dependencies and the exact
versions used in the comparison are recorded in `requirements-comparison.txt`;
they are not bundled as substitute implementations.

The check-manifest study executes the tool's legacy source-archive comparison.
A separate attempt to use its modern `python -m build` path was BLOCKED because
the build frontend was unavailable; that attempt is retained rather than scored
as a tool miss.
