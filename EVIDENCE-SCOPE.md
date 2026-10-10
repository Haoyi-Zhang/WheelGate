# Evidence scope

## Established by execution

- The retained installation study records 140 source tests plus six subtests passing; this is distinct from the later 167-test source suite.
- WheelGate installs and passes the same test suite from both its direct wheel
  and a wheel rebuilt from its sdist.
- A 45-observation route matrix distinguishes checkout, default editable,
  strict editable, direct-wheel, and sdist-derived-wheel behavior.
- A 24-observation context study separates correct output supplied by declared
  artifacts from correct output supplied by undeclared distributions,
  current-directory modules/data, or unrecorded site-packages files.
- A maintainer-linked django-xml configuration replay reproduces the public
  package-selection mechanism and its repair in three repeated wheel runs.
- Default check-wheel-contents, reference-tree check-wheel-contents, and
  check-manifest are executed without weakening their intended scopes.

## Not represented as executed evidence

- The original django-xml 4.0.0 and 4.0.1 publisher wheel bytes were unavailable.
- No maintainer deployment, interview, user study, private industrial data,
  cross-platform matrix, native-extension case, or ecosystem prevalence estimate
  is claimed.
- tox, nox, and Twine are discussed according to their documented purposes but
  are not scored as misses in the historical replay.

The raw records distinguish `FAIL`, `BLOCKED`, and `INVALID`; none of these is
silently converted into an upstream defect count.
