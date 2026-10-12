# Evidence scope

## Established by execution

- The retained installation study records 140 source tests plus six subtests passing; this is distinct from the current 191-test source suite.
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

## Additional current validation (not pooled with retained studies)

- Host-independent contract-path admission and bundle-reference normalization
  are tested using harmless owned fixtures; the current Windows suite has 191
  tests. This is not a native Linux test run.
- `results/packaging-flow/comparison.json` and its `self-check.json` record
  direct and sdist-derived builds of the supplied WheelGate package, 191 tests
  after each installation, and unchanged CWC default/reference checks. Ordinary
  and gate operations use the same three expectations and pass on both routes.
  Positive self-package validation adds no external maintainer deployment or
  comparative defect-recall advantage.
- `results/portability/route-requalification.json` requalifies the same two
  retained wheel contents five times each. New input/source bindings and fresh
  timings remain separate from the original 45 route observations and ten
  retained requalification observations.
