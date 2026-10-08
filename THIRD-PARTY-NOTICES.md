# Third-party inputs and notices

Four wheel archives were retained from the execution runtime: pip 25.1.1,
setuptools 78.1.1, Pygments 2.19.1, and latex2pydata 0.5.0. They were not
retrieved from PyPI during this study. `third_party/manifest.json` records their
local SHA-256 values and sizes, and `corpus/registry-comparison.json` records
that their whole-archive hashes differ from the hashes published for the same
filenames. Neither the cause of those differences nor uncompressed-payload
equivalence was established. The manuscript therefore calls them retained local
inputs, not verified publisher downloads.

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
