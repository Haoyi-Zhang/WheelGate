# Case and experiment protocol

## Case classification

A public report enters the register only when it identifies a packaging or
release-artifact concern and a consumer-relevant operation can be stated. A case
is **maintainer-linked** when a maintainer statement, fix commit, or release
action connects the report to a repair. It becomes an **artifact replay** only
when the original affected and fixed bytes are retrieved, hashed, installed,
and exercised. Reconstructing a public configuration change is recorded as a
**configuration replay**, not as execution of publisher artifacts.

Reports are excluded from defect counts when the supported operation, affected
version, fix, route, or lawful artifact is unresolved. Deliberate omissions and
missing optional prerequisites are controls rather than defects. Repeated runs
measure stability and are not counted as independent projects.

## Controlled studies

The route study freezes three package states before execution: undeclared data
(U), sdist-only exclusion (X), and repaired inclusion (R). Each is evaluated on
checkout, default editable, strict editable, direct-wheel, and sdist-derived
wheel paths. The context study freezes eight conditions spanning declared and
undeclared helpers, prerequisite version mismatch, current-directory and
unrecorded installed modules, and corresponding data origins. The ordinary
baseline and WheelGate use the same semantic oracle.

## Baseline policy

Comparison tools run unchanged. check-wheel-contents is evaluated with default
rules and with an explicitly justified source-package reference. check-manifest
is interpreted as a source-file-policy check; acceptance of an explicit sdist
exclusion is not called a tool defect. Unavailable tools are `BLOCKED`, never
scored as acceptance or rejection.

## Reporting

Each result retains artifact and contract hashes, commands, exits, timeouts,
installed origin evidence, status, and timing. Setup time is separated from
operation time. FAIL, BLOCKED, and INVALID remain distinct. Raw records are not
pooled with fresh validation replays.
