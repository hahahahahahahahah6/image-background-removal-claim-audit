# Documentation claim auditor

An offline, deterministic, standard-library-only CLI that checks prose about
stripping the surroundings out of a still picture against static source evidence.
Requires Python 3.9 or newer. No network, telemetry, LLM, or file writes are used.

## Install and use

```sh
python3 -m pip install .
image-background-removal-claim-audit --version
image-background-removal-claim-audit audit . --json
python3 -m image_background_removal_claim_audit audit --ignore vendor/ .
image-background-removal-claim-audit audit . --ignore generated/ --fail-on medium --verbose
```

The repository defaults to the current directory. Each ignore option accepts
one literal relative path prefix and can be repeated. The scanner reads root
README prose and Markdown under docs. Triple backtick fences are excluded;
inline code counts as prose. Test fixture claims have reduced severity.
Python evidence is resolved within each individual module using import aliases.
Local function and class definitions shadow imports. Standard cache, version
control, and virtual environment directories are skipped. Invalid syntax
provides no evidence. The auditor never executes the inspected code.

Exit status is 0 when nothing meets the threshold, 2 for findings at or above
the threshold, and 1 for usage or IO errors. The default threshold is high;
medium also fails on test-only claims. JSON has an overall verdict and findings
with rule, severity, verdict, and message fields. Verbose decisions and scope
are printed to standard error.

```text
documented-image-background-removal-claim-false HIGH
documented-no-image-background-removal-claim-false HIGH
documented-image-background-removal-claim-false MEDIUM (test fixtures only)
```

## Differentiation

The following tool checks producing a mask for a still picture; this tool
checks stripping the surroundings out of it.

```text
segmentation-claim-audit
```

The following tool checks finding objects in a picture; this tool checks
separating them from the pixels behind them.

```text
object-detection-claim-audit
```

The following tool checks creating new images; this tool checks stripping the
surroundings from an existing one.

```text
image-generation-claim-audit
```

## Limitations

Static pattern matching is not semantic judgement. Matching uses exact,
case-insensitive substrings, not restatements, stemming, fuzzy matching, or
hyphen normalization. Denial spans are removed first. Longest-first matching
with span blanking makes each occurrence match once under its longest phrase.

The following call deliberately does not count, because softening pixels is
not removing them. Map and overlay modes are also excluded.

```text
Remover.process(..., type='blur')
```

A generic call on an unrelated object counts because the method name is shared:

```text
unrelated.remove_background(...)
```

Exact phrases can also describe audio cleanup, desktop tidying, or a school
craft activity. These examples still match, a known ambiguity:

```text
remove background noise from audio
remove backgrounds from your slides
image cutout worksheet
```

Bare imports, sessions alone, lone constructions, segmentation, detection,
manual chroma-key masking, cropping, resizing, conversion, and subprocess
commands provide no evidence. Instance pairs must occur in one module;
evidence is never assembled across modules. Static patterns cannot prove
runtime behavior or infer custom implementations. Shared generic names may
accept unrelated operations.

## Development

```sh
python3 -m unittest discover
python3 -m build
```

Licensed under MIT.
