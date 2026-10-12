# WheelGate artifact

WheelGate qualifies a trusted local Python wheel against reviewed consumer
operations. It binds the operation to the wheel identity and support profile,
installs the artifact in a fresh environment, checks static ownership, and
records newly loaded Python modules and read-capable non-code file opens attempted during execution.
A successful operation is accepted only when those concrete origins belong to
the target distribution, declared prerequisite distributions, or the standard
library.

## Implementation

`wheelgate/runner.py` validates artifact identity, creates the isolated
installation, checks profile prerequisites, and coordinates operation workers.
`wheelgate/worker.py` implements import, call, resource, entry-point, console,
and reviewed-script operations. `wheelgate/footprint.py` maps module origins and
Python audit-hook read-capable opens to installed RECORD inventories. Runtime code uses
only the Python standard library.

Decisions are:

- `PASS`: the operation and oracle succeeded in the established context;
- `FAIL`: a delivery, operation, or oracle failure was observed after setup; attribution may still be unresolved and context warnings are retained;
- `BLOCKED`: a declared prerequisite or installation precondition was absent;
- `INVALID`: the observation could not establish the requested context.

The wheel is not a security sandbox. Contracts and subject packages are trusted
research or release-test inputs.

Both accepted contract schemas (1 and 2) reject unknown fields and assertions
that do not apply to the operation before installation. Import obligations do
not accept value assertions; entry-point arguments and value assertions require
`invoke: true`. The retained schema-1 smoke contract remains accepted unchanged.
Console-child timeouts are `INVALID`, with partial output retained in the
receipt; completed command failures and oracle mismatches remain `FAIL`.
Validation checks syntax, types, and operation applicability, not joint
satisfiability of accepted value assertions or arbitrary consumer scripts.
Resource paths must use explicit POSIX-relative file components on all hosts.
Drive/stream syntax, backslashes, empty components, and dot or parent components
are rejected. Commands must be basenames without either separator style or drive
syntax. The controller and standalone worker enforce the same admission rules;
path normalization never replaces installed-file ownership checks.
Controller `qualify` receipts include the canonical validated contract digest.
The retained route/context studies call `probe` and link artifacts to declared
fixture cases and execution records without that digest.

## Retained studies

| Record | Scope | Executed observations |
|---|---|---:|
| `results/historical/django-xml-replay.json` | Maintainer-linked package-selection replay | 6 |
| `results/routes/matrix.json` | Three packaging states across five delivery routes | 45 |
| `results/routes/requalification.json` | Current-controller replay of two unique route-wheel contents | 10 |
| `results/footprint/matrix.json` | Eight support/code/data context controls | 24 |
| `results/package/self-check.json` | Direct and sdist-derived installation of WheelGate itself | 2 routes |

The retained source-suite records contain 140 tests plus six subtests. Each installed WheelGate
route in `self-check.json` runs that recorded suite outside the checkout, verifies
module origin and version, and exercises healthy and missing-resource fixtures.
The direct and sdist-derived software wheels have equal package-payload hashes.

The django-xml record replays the exact public configuration change from
`packages=['djxml']` to discovery of `djxml*`. Both source trees expose the nested
module; the affected wheel omits it and fails, while the repaired wheel passes.
This establishes the documented mechanism, not byte-for-byte execution of the
unavailable publisher wheels.

The selected results were run on Windows 11, CPython 3.12.14, and an Intel Core i7-12700KF. The gate adapts Windows console launchers by invoking their registered Python entry point; the route baseline runs the actual installed executable. File observations include failed read-capable opens, not only consumed bytes.

## Commands

Run the source suite:

```sh
python -m unittest discover -s tests -v
```

Install the retained software wheel and qualify the healthy fixture:

```sh
python -m venv /tmp/wg-env
/tmp/wg-env/bin/python -m pip install --no-index --no-deps \
  results/package/self-check-assets/direct/wheelgate-1.0.0-py3-none-any.whl
/tmp/wg-env/bin/wheelgate \
  inputs/fixture-direct/wg_fixture-0.1.0-py3-none-any.whl \
  contracts/fixture.json --output /tmp/wg-report.json
```

The same command with `inputs/fixture-rebuilt/` must return a nonzero status
because the promised resource is absent.

Regenerate manuscript tables from the selected records and audit consistency:

```sh
python scripts/summarize.py
python scripts/audit.py --artifact-only
```

Fresh outputs must use a path that does not exist:

```sh
python scripts/footprint_matrix.py --output /tmp/footprint/matrix.json
python scripts/historical_replay.py --output /tmp/historical/replay.json
python scripts/requalify_routes.py --output /tmp/routes/requalification.json
python scripts/package_check.py --output /tmp/package/self-check.json
```

The complete route matrix additionally executes check-manifest 0.50 and
check-wheel-contents 0.6.1 from retained upstream sources:

```sh
python scripts/route_matrix.py --output /tmp/routes/matrix.json
```

`requirements-comparison.txt` records the host-side dependencies used by that
comparison. Subject environments do not inherit those packages.

## Layout

- `wheelgate/`: implementation
- `tests/`: regression tests
- `contracts/`, `inputs/`: retained smoke-test inputs
- `scripts/`: experiments, summarization, reproduction, and audit
- `results/`: selected raw records and lawful generated assets
- `corpus/`: case protocol/register and reference verification ledger
- `third_party/`: exact comparison-tool sources, licences, and offline build input

Absolute temporary paths inside raw receipts are observations of the executed
host. Replays create new paths and timings; they do not overwrite the retained
records.

Retained file references (not process arguments or temporary origins) may use
Windows or POSIX separators. `scripts/evidence_paths.py` resolves only relative
references inside the artifact or record directory; it rejects absolute paths,
drive syntax, traversal, and paths resolving outside that directory. New
requalification and self-package records write POSIX separators. The original
route generator is retained unchanged because its hash binds the selected study.

`scripts/reproduce.py` reruns the context and historical studies, route
requalification, and software installation study in a fresh copy. Its
`--full-route` option also regenerates the route matrix. It does not rerun the
additional current self-package comparison or write a separate
portability record. Run `scripts/packaging_flow.py` and
`scripts/requalify_routes.py --output <fresh-path>` explicitly for those current
validations. `scripts/audit.py` checks the retained study set, not these separate
additional outputs.

## Current portability and self-package validation

The current source suite contains 193 tests. The retained installation study
still records 140 tests; these are different revisions, not additional projects.
`results/current/packaging-flow/comparison.json` records the current
direct/sdist-derived build, 193 installed tests on each route,
unchanged CWC default/reference checks, and ordinary/gate operations with the
same import, canonical-name, and version-command expectations. All pass on both
routes. This is positive self-package validation, not an external maintainer
deployment or additional defect-recall result.
`results/current/portability/route-requalification.json` records ten
source-bound Windows runs over the same two route-wheel contents: five pass
and five produce the expected missing-resource failure. The original study
records retain their own input and test-suite bindings.

To repeat the self-package comparison in a host with CWC dependencies installed:

```sh
python scripts/packaging_flow.py --output /tmp/wg-self-flow/comparison.json
```

The optional `--comparison-wheel-dir` instead reads pinned pure-Python dependency
wheels through zipimport without installing them or running startup hooks. The
record identifies the dependency versions and inputs actually used. Component
and owned-file tests cover cross-host path syntax on Windows; native Linux
execution remains unverified.
