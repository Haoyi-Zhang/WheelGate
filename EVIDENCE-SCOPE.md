# Evidence scope

## Established by execution

- The retained installation study records 140 source tests plus six subtests passing. Fresh source and artifact-only test runs report their own executed and skipped counts rather than inheriting this retained total.
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

## Original inputs and study boundaries

- The selected original-wheel checks execute documented imports in django-xml
  4.0.0 and 4.0.1, and the documented parser call in latex2pydata 0.5.0.
  Ordinary and controller results are FAIL/PASS/PASS, respectively.
- Maintainer deployment, interviews, user studies, private industrial data,
  cross-platform matrices and ecosystem prevalence are outside the executed studies.
  The selected lxml prerequisite is present; its native internals are not traced.
- tox, nox, and Twine are discussed according to their documented purposes but
  are not scored as misses in the historical replay.

The raw records distinguish `FAIL`, `BLOCKED`, and `INVALID`; none of these is
silently converted into an upstream defect count.

## Additional current validation (not pooled with retained studies)

- Host-independent contract-path admission and bundle-reference normalization
  are tested using harmless owned fixtures. The earlier Windows source-suite
  record contains 200 tests; later artifact-only helper tests do not retroactively
  extend that execution. This is not a native Linux test run.
- `results/current/packaging-flow/comparison.json` and its `self-check.json` record
  direct and sdist-derived builds of the supplied WheelGate package, 193 tests
  after each installation, and unchanged CWC default/reference checks. Ordinary
  and gate operations use the same three expectations and pass on both routes.
  Positive self-package validation adds no external maintainer deployment or
  comparative defect-recall advantage.
- `results/current/portability/route-requalification.json` requalifies the same two
  retained wheel contents five times each. New input/source bindings and fresh
  timings remain separate from the original 45 route observations and ten
  retained requalification observations.

The original publisher inputs and categorical receipts in
`results/publisher-wheel-replay/` form a separate extension. The selected
CPython 3.12/Windows profile uses seven exact prerequisite downloads, whose
binaries are obtained from the recorded publishers. Completed django gate
observations use short paths and existing controller stages; convenience
wrapper setup blocks are preserved separately. Seven offline tests check the
subject archives, notices, source/contract bindings and receipt consistency.
