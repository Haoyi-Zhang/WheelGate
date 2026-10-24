# Exact external inputs and observation scope

## A documented original-package operation

[latex2pydata 0.5.0](https://pypi.org/project/latex2pydata/0.5.0/) documents
`load(pathlib.Path)` and loading Python literals from caller-provided files.
The retained original wheel is unchanged and its BSD-3-Clause notice remains
under `evidence/publisher-wheels/`. All seven Python modules were read before
execution. There are no third-party dependencies, startup hooks or native modules
in that wheel. This replay does not execute upstream build/test scripts.

The input is the unchanged [upstream dictionary test data](https://github.com/gpoore/latex2pydata/blob/ceee4aa242b1f2f42063b5abcd75a7bc36530bf3/latex/test/toplevel_dict_test_pass.json),
whose string-valued JSON dictionary is also valid Python literal syntax.
The upstream `latex/test/README.md` identifies these JSON files as expected test
data; we use the file directly, not a new LaTeX build or a claim that upstream's
complete test suite ran. Its SHA-256 is
`5caf7af779906e28787bcb47b45640f4981bc1c5ed9011370f178bbbc67214d3`.
This small test-data excerpt retains its source attribution; WheelGate's MIT
license does not relicense upstream materials or extend the Python package's BSD
notice to the separate LaTeX source tree.

`results/external-input-qualified/` retains an ordinary installed test, the
undeclared-input gate receipt, and the declared-input receipt. All use the same
original wheel, exact file bytes and expected dictionary. The ordinary baseline
has a neutral directory, isolated interpreter and target RECORD ownership check.
It passes. The gate also obtains the correct value but reports INVALID because
the input file is external. One explicit declaration changes the context
decision to PASS, without modifying the package or semantic oracle. Its receipt
labels the file `declared-external-input` and binds both before/after hashes.

This is a release-qualification rehearsal of a documented public API, using
independently maintained code and input data. The release recipe and policy
choice are ours. It is not an independently observed hidden-dependency incident,
publisher regression, maintainer repair or adoption claim.

## Declaration and actual adaptation work

The four-line script adapter constructs a `Path`, calls the public API and checks
the expected dictionary. It is identical in both gate contracts and the ordinary
test. The extra configuration is one `external_inputs` list entry with exactly
three scalar fields, not a new oracle, dependency profile or package patch:

```json
{
  "external_inputs": [{
    "path": "/absolute/execution-host/path/to/reviewed-data.json",
    "sha256": "5caf7af779906e28787bcb47b45640f4981bc1c5ed9011370f178bbbc67214d3",
    "evidence": "Documented caller-supplied input for load(Path), with pinned upstream locator"
  }]
}
```

On Windows use an absolute Windows path. The example above is the declaration
field of an operation, not a complete standalone contract. The replay builds the
complete contracts and binds paths on the execution host. Do not execute a
retained absolute-path contract unchanged on another host; regenerate it.
Artifact identity, module anchors, environment inventory, process checks and
the oracle are reused. An ordinary installed test can implement the same exact
file policy and make the same decision. No engineer-hour or general maintenance
benefit estimate is inferred from this one adaptation.

Offline receipt verification is separate from a new execution. Both retained
rehearsals were executed with the listed driver and worker sources on Windows,
using the same original wheel, input bytes and assertion. Their contract paths
and script text are literal execution-host data when read on Linux. The public
CLI receipt is a separate executed check of the declared contract.
`tests/test_external_replay_record.py` checks the retained
contract/receipt/summary bindings using the original canonical JSON encoding
(sorted keys, compact separators, UTF-8, finite numbers), without resolving or
rewriting paths. This checks document integrity, not authenticity, current file
availability or Linux execution. The runtime `canonical_contract_digest` still
requires full current-host validation, including native absolute input paths.
A fresh replay must use new host-bound contracts and a new output directory.

The five receipts marked `python-runtime-path-normalized-copy` under
`results/external-input-qualified/` and `results/external-input-replay/` use
`<PYTHON_RUNTIME>` for the recorded Python root, consistently in standard-library
origins and their serialized output. They are display representations, not
byte-exact captures or new executions. Relative suffixes, external-input paths,
identities, classifications, measurements and decisions are unchanged; the alias
does not authorize a runtime path or recompute a classification.

No wildcard, directory, generated-code or other-distribution grant is added.
All declared files must exist and match before the operation, or it returns
INVALID without running. Identity is checked again afterward. Mutation invalidates
an otherwise successful result; a semantic failure stays FAIL with a context
warning. The observation assumes trusted stable test files: before/after hashes
do not identify every byte actually consumed or prevent a hostile intervening race.
Missing optional package prerequisites remain the separate BLOCKED mechanism.

## Mechanism support matrix

| Consumer mechanism | Meaning of the receipt | Adapter/review action |
|---|---|---|
| New filesystem-backed Python imports | New `sys.modules` concrete origins attributed | Already-loaded or transient removed modules are outside this delta; review before relying on them |
| Python read-like non-code opens | Attempted paths attributed, including failed opens | Not a byte-consumption trace; write-only and code suffixes excluded |
| Stable external config or generated data | Exact path and matching pre/post digest explicitly admitted | Generate before observation; do not grant a whole directory |
| Legitimate plugins | Selected distributions declared as exact profile prerequisites | Unselected/discovered plugins require profile review or a dedicated adapter |
| Native reads, mmap, inherited descriptors, unrelated child I/O | Generic PASS makes no claim about these accesses | Add tracing/adapter or withhold the broader qualification |
| POSIX Python console launcher | Recorded launcher executed in the observed Python child | Native subprocess trees need separate observation |
| Windows native launcher | Recorded wrapper checked, registered Python entry point invoked | Native wrapper bytes are not executed by that adapter; test them separately |
| Dynamic generated code / data during operation | No general generator or directory authorization | Add an operation-specific adapter; generic INVALID is not a package defect |

## Repeat the actual comparison offline

From the artifact root, with a fresh output directory:

```sh
python scripts/external_input_replay.py --input results/external-input-qualified/upstream-data.json --output results/external-input-new
python -m unittest discover -s tests -p test_external_inputs.py -v
```

The first command verifies the original wheel and upstream input identities,
then installs only that reviewed local wheel into three temporary environments,
without an index or dependency resolution. Omitting `--input` acquires the pinned
data URL before the same verification. Outputs retain actual execution paths;
new runs bind their own path-dependent canonical contract hashes. Timing fields
are receipts, not a new benchmark or an addition to the old 6/45/24 denominators.
