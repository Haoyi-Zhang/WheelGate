# WheelGate artifact

WheelGate qualifies a trusted local Python wheel against reviewed consumer
operations. It binds the operation to the wheel identity and support profile,
installs the artifact in a fresh environment, checks static ownership, and
records newly loaded Python modules and read-capable non-code file opens attempted during execution.
A successful operation is accepted only when those concrete origins belong to
the target distribution, declared prerequisite distributions, or the standard
library. Stable caller-supplied non-code files can additionally be declared by
exact path, SHA-256 and evidence. This does not admit external code or directories.

## External data and supported observation scope

`docs/EXTERNAL-INPUTS.md` gives the original-wheel release rehearsal, exact
declaration format, ordinary-test comparison and supported-mechanism matrix.
The original latex2pydata 0.5.0 file-loading API on upstream test data produces
ordinary PASS, default-gate INVALID, then declared-input PASS with the same
four-line consumer adapter and assertion. This is not a publisher bug, a field
incident or maintainer adoption. The canonical retained record is
`results/external-input-qualified/summary.json`; the initial separately
executed acquisition run remains under `results/external-input-replay/`.

## Implementation

The workflow figure is generated directly with Matplotlib and embedded fonts:
`python plots/draw_workflow.py --output-dir ../paper/figures`.
Install `requirements-figures.txt` for figure regeneration. In the full bundle,
`paper/build.py` regenerates the workflow before compiling.
Rendering occurs in the isolated build tree after engine preflight. A renderer
or compiler failure preserves the delivered manuscript and workflow figure.

### Release-job placement

Keep the ordinary installed-wheel tests as the semantic baseline. After a build,
pass the exact produced wheel and reviewed contract to the public command:

```sh
python -m wheelgate /path/to/produced.whl /path/to/contract.json --output /path/to/new-receipt.json
```

When called from a tox/cibuildwheel job, the controller creates its own fresh
installation; it does not reuse that job's already-installed subject environment.
This additional setup is not included in the retained post-setup medians
(0.64 seconds for one operation and 1.95 seconds for three). This is integration
guidance, not evidence of maintainer adoption, an executed tox comparison, or a
new independently discovered third-party context defect.

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
This isolates the package-selection mechanism. A separate original-wheel
extension retains django-xml 4.0.0/4.0.1 and latex2pydata 0.5.0 in
`evidence/publisher-wheels/inputs/`. Ordinary installed checks and the existing
controller stages both reject the affected django wheel, accept the repaired
wheel, and accept the documented latex2pydata parser operation.

The django runs use CPython 3.12.14 on Windows AMD64 with seven explicitly pinned
prerequisites. The receipts in `results/publisher-wheel-replay/` distinguish
completed short-work-path controller observations from the convenience
wrapper's earlier path-length setup blocks. Three further observations in
`results/publisher-public-cli/` execute the unchanged public command with a
short temporary root and verified local prerequisites: django-xml 4.0.0 fails,
4.0.1 passes, and latex2pydata 0.5.0 passes. All three have ready setup/profile
checks and no observed module/file ownership violations. Native-library internals remain outside
the Python-level footprint. These three inputs are separate from the retained
6/45/24-observation studies.

The source inventory records exact publisher locators, sizes and identities.
The three subject archives retain their BSD notices. Prerequisite binaries are
download inputs, not vendored files; their license and resource notices are
recorded alongside the selected profile.

The selected results were run on Windows 11, CPython 3.12.14, and an Intel Core i7-12700KF. The gate adapts Windows console launchers by invoking their registered Python entry point; the route baseline runs the actual installed executable. File observations include failed read-capable opens, not only consumed bytes.

## Commands

Run source commands from this artifact directory with Python 3.11 or newer.
Qualification also requires that interpreter's `venv` and `pip`; the runtime
has no third-party Python dependency. Comparison and rendering commands have
the separate host requirements documented below.

The `/tmp/...` virtual-environment example uses POSIX paths. On Windows choose
a fresh short root such as `D:/wg-env`, use its `Scripts/python.exe` and
`Scripts/wheelgate.exe`, and use PowerShell continuation syntax rather than
the shell backslashes. For the selected publisher profile, use the short-TEMP
helper under **Original publisher inputs**, which supplies TEMP/TMP/TMPDIR to
the child without changing the controller.

Run the source suite:

```sh
python -m unittest discover -s tests -v
```

Install the current software wheel and qualify the healthy fixture:

```sh
python -m venv /tmp/wg-env
/tmp/wg-env/bin/python -m pip install --no-index --no-deps \
  dist/wheelgate-1.1.0-py3-none-any.whl
/tmp/wg-env/bin/wheelgate \
  inputs/fixture-direct/wg_fixture-0.1.0-py3-none-any.whl \
  contracts/fixture.json --output /tmp/wg-report.json
```

The same command with `inputs/fixture-rebuilt/` must return a nonzero status
because the promised resource is absent.

`dist/` is the installation entry for the current source, including exact
external-data declarations. Its manifest binds all runtime modules and records
17 external-input regressions after each of direct-wheel and sdist-derived
installation. The two distribution files share the software version in
`wheelgate/__init__.py`; this is package metadata, not a manuscript revision.
To build and verify both routes again, choose fresh output and raw-log paths:

```sh
python scripts/build_distribution.py --output /tmp/wheelgate-dist --log-dir /tmp/wheelgate-build-logs
```

The software packages under `results/` are frozen inputs of their adjacent
installation studies. They do not include the later external-input extension
and are not the current installation entry. Their recorded outcomes and source
payloads are retained, not reassigned to the new build.

### Smoke fixture

`contracts/fixture.json` defines five author-specified synthetic obligations for
`wg-fixture` 0.1.0, not a historical defect or an independently maintained oracle:

- import `wg_fixture`;
- call `wg_fixture:consumer`, expecting the string `hello`;
- read `wg_fixture/template.json`, expecting JSON `{"schema": 1, "message": "hello"}`;
- run the `wg-fixture` console command, expecting stdout `hello\n`;
- load and invoke `demo` in the `wheelgate.fixture_plugins` entry-point group,
  expecting the string `hello`.

Both retained fixture wheels contain the same `wg_fixture/__init__.py` and
entry-point declarations: `wg-fixture = wg_fixture:main` and
`demo = wg_fixture:consumer`. The consumer reads `template.json` and returns its
`message`; the console function prints that value. The healthy direct wheel
contains the promised JSON resource. The rebuilt missing-resource wheel omits
it, so importing the module alone can succeed while the resource-dependent
obligations fail. These members can be inspected without importing either wheel.
Each evidence pointer uses `archive.whl!member`: the path before `!` is a
retained file relative to this artifact directory, and the remainder identifies
the ZIP member. The five pointers identify the healthy wheel's module source,
JSON resource, and entry-point declarations rather than a missing README.

### Retained-study commands

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

The three CWC wrappers (`cwc_baseline.py`, `route_matrix.py`, and
`historical_replay.py`) treat exit 0 as `PASS`, exit 1 as content `REJECT`, and
exit 2 (invalid invocation) as `CALLERROR`. Launch failure (127) or timeout is
`BLOCKED`; other unexpected exits are `INVALID`. `CALLERROR` is a comparison-tool
call outcome, not a WheelGate qualification status or a content rejection.
Raw argv, streams, return code and the
timeout flag remain in the receipt. The standalone CWC wrapper exits 2 for a
call error, blocked or invalid call, 1 for content rejection, and 0 for acceptance. Its
no-build stub regressions run with:

```sh
python -B -m unittest discover -s tests -p test_cwc_wrappers.py -v
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
requalification and self-package records write POSIX separators. The selected
route study retains its execution-time generator at
`results/routes/provenance/route_matrix.py`; updated wrapper error handling does
not rewrite that source or the selected records.
The historical replay likewise retains its exact execution-time generator at
`scripts/provenance/historical_replay.py`, read only for its source binding, not
as a runnable entry point. The audit checks that retained hash without attributing
the historical run to the updated wrapper.

`scripts/reproduce.py` reruns the context and historical studies, route
requalification, and software installation study in a fresh copy. Its
`--full-route` option also regenerates the route matrix. It does not rerun the
additional current self-package comparison or write a separate
portability record. Run `scripts/packaging_flow.py` and
`scripts/requalify_routes.py --output <fresh-path>` explicitly for those current
validations. `scripts/audit.py` checks the retained study set, not these separate
additional outputs.

## Retained portability and self-package validation

The source suite includes seven offline original-input binding tests and three
artifact-only public-entry helper tests; the test runner reports its executed
and skipped counts. The retained installation study records 140 tests, and the
separate self-package comparison executed 193 tests per route.
`results/current/packaging-flow/comparison.json` records an earlier
direct/sdist-derived build, 193 installed tests on each route,
unchanged CWC default/reference checks, and ordinary/gate operations with the
same import, canonical-name, and version-command expectations. All pass on both
routes. Despite the directory name, this record predates the external-input
extension and does not validate the modules in `dist/`. This is positive self-package validation, not an external maintainer
deployment or additional defect-recall result.
`results/current/portability/route-requalification.json` records ten
source-bound Windows runs over the same two route-wheel contents: five pass
and five produce the expected missing-resource failure. The original study
records retain their own input and test-suite bindings.

To repeat the self-package comparison in a host with CWC dependencies installed:

```sh
python scripts/packaging_flow.py --output /tmp/wg-self-flow/comparison.json
```

For a fresh positive self-package comparison, exit 0 and `COMPLETE` require
ordinary, gate, and both CWC checks to pass on both routes. Execution finishing
is recorded separately as `execution_completed`; it does not imply success.
`FAIL` (including CWC `REJECT`) exits 1; `BLOCKED` or `INVALID` exits 2.
For mixed outcomes, the summary priority is `INVALID`, `BLOCKED`, then `FAIL`;
`unexpected_results` retains every non-passing route/method/status, and the
original processes and gate details remain in `runs`. The small wrapper
regressions can run without building or installing anything:

```sh
python -B -m unittest discover -s tests -p test_packaging_flow.py -v
```

The optional `--comparison-wheel-dir` instead reads pinned pure-Python dependency
wheels through zipimport without installing them or running startup hooks. The
record identifies the dependency versions and inputs actually used. Component
and owned-file tests cover cross-host path syntax on Windows; native Linux
execution remains unverified.

## Original publisher inputs

The selected django profile uses CPython 3.12 on Windows AMD64. From `artifact/`,
the following PowerShell commands download its seven pinned prerequisites
without installation, dependency resolution or source builds. Existing files
are preserved. A mismatch stops acquisition before qualification:

```powershell
$root = (Resolve-Path -LiteralPath 'evidence/publisher-wheels').Path
$pins = (Get-Content -LiteralPath (Join-Path $root 'source-inventory.json') -Raw |
  ConvertFrom-Json).inputs | Where-Object { $_.input_kind -eq 'publisher-download' }
if (@($pins).Count -ne 7) { throw 'Expected seven prerequisite inputs' }
foreach ($pin in $pins) {
  $path = [IO.Path]::GetFullPath((Join-Path $root $pin.download_destination))
  $url = [Uri]$pin.publisher_url
  if ([IO.Path]::GetDirectoryName($path) -ne (Join-Path $root 'inputs') -or
      $url.Scheme -ne 'https' -or $url.Host -ne 'files.pythonhosted.org' -or
      $url.UserInfo) { throw 'Invalid publisher destination' }
  if (Test-Path -LiteralPath $path) { throw "Already exists: $path" }
  Invoke-WebRequest -Uri $url.AbsoluteUri -OutFile $path
  if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne
      $pin.sha256 -or (Get-Item -LiteralPath $path).Length -ne $pin.bytes) {
    throw 'Publisher input mismatch'
  }
}
```

Pass each verified prerequisite using the existing `--dependency` option and
select `--profile replay-cp312-win-amd64` for the django contracts. Run from a
short working and temporary path on Windows. The documented latex2pydata call
has no prerequisite and uses the base profile:

```sh
python -m wheelgate \
  evidence/publisher-wheels/inputs/latex2pydata-0.5.0-py3-none-any.whl \
  contracts/publisher-latex2pydata-0.5.0.json --output /tmp/latex-receipt.json
python -B -m unittest discover -s tests -p test_publisher_inputs.py -v
```

After obtaining the seven prerequisites at their recorded destinations, the
three-input public-entry replay can be repeated on the selected Windows/Python
profile without modifying the controller:

```powershell
python -B scripts/publisher_cli_replay.py --current-runtime --dependency-dir D:/wheel-inputs --execute --output-dir D:/wheel-cli-replay --temp-root D:/wheel-tmp
```

Both output paths must be fresh. The helper verifies the original inputs and
runtime bindings before installation and uses explicit local, no-index inputs.
`--current-runtime` explicitly binds a fresh run to the current implementation;
omitting it retains the original-source guard and rejects changed runtime bytes.
Historical publisher receipts are not relabelled as current observations.
`evidence/publisher-wheels/runtime-at-original-replay.json` preserves the exact
three changed historical modules consumed by the original binding tests; the
other four bound modules remain unchanged.
The three observations are not pooled with the retained 6/45/24-study counts
and supply no new timing estimate.

The offline tests inspect retained archive members, notices, runtime and
contract bindings, prerequisite observations and recorded outcomes. They do
not install a package or recollect the native runs. The seven dependency
versions describe the selected study profile rather than a deployment update
recommendation.

Installed-software testing stages these study fixtures beside the neutral test
suite, not inside either software wheel. Runtime-byte checks read unchanged
installed modules and the preserved original bytes for the three subsequently
modified modules; they validate historical source bindings, not an assertion
that the current policy was used in those runs.

## Render retained qualification times

Install `requirements-figures.txt`, then run
`python scripts/render_runtime.py --source plot_inputs/runtime-summary.dat --output-dir figures --font-root /path/to/texmf-dist/fonts`.
The three vector bars preserve the retained class aggregation: prerequisite
median, median of eight operation-class medians, and the three-operation
bundle median. They exclude environment creation and installation and remain
separate from the original-publisher-wheel study. The renderer executes no
package or timing study; five route checks run in the source artifact suite.
The five artifact-only checks are in `plot_tests/`, separate from the installed
software's API suite. CI and the fresh-copy replay run both source suites;
installed-wheel tests retain every software check without introducing an
artifact rendering dependency into the wheel. The replay host requires both
`requirements-comparison.txt` and `requirements-figures.txt`.

## Portable path notation

Published execution records use `<PYTHON_ROOT>`, `<NODE_ROOT>` and `<RUNTIME_ROOT>` for local tool installations, `<DEPENDENCIES_ROOT>` for local dependencies, and `<PROJECTS_ROOT>`, `<ARTIFACT_ROOT>`, `<SOURCE_ROOT>` and `<WORK_ROOT>` for the workspace, artifact checkout, source checkout and temporary work directory of the recorded run. These are path aliases, not literal directories or claims that historical temporary files are included in this bundle. Substitute the corresponding local roots when replaying a command. Recorded tool versions, source/input identities, measurements, outcomes and failures are unchanged. Current file inventories bind the portable published bytes; any `recorded_` identity denotes pre-normalization bytes.

The retained `results/publisher-public-cli/report.json` labels its three receipts
as `path-normalized-public-copy`: each `raw_receipt.sha256`/`bytes` pair identifies
the included current file, while its `recorded_sha256`/`recorded_bytes` pair preserves
the separately recorded execution-capture identity. Those original captures are
not bundled here. Fresh `scripts/publisher_cli_replay.py` output is instead an
`execution-capture`; it does not normalize child receipt paths and binds each
file with `raw_receipt_sha256` and `raw_receipt_bytes`. A retained execution-time
generator hash (including `execution_helper.sha256` or `script_sha256`) is not
an assertion that a subsequently updated generator still has those bytes.
