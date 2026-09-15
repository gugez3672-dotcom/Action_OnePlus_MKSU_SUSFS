#!/bin/bash
# Run the exact GKI target used by the OnePlus canoe perf base_kernel alias.
set -euo pipefail
phase="${1:?preflight or build}"
cd "$GITHUB_WORKSPACE/kernel_workspace/kernel_platform"
mkdir -p "$GITHUB_WORKSPACE/artifacts" "$GITHUB_WORKSPACE/bazel-cache"
export TEST_TMPDIR="$GITHUB_WORKSPACE/bazel-cache"
bazel=(tools/bazel "--output_user_root=$GITHUB_WORKSPACE/bazel-cache")
# These are the same bzlmod compatibility options used by the pinned
# OnePlus build_with_bazel.py, with no kernel configuration overrides.
opts=(
  --incompatible_sandbox_hermetic_tmp=false
  --noenable_workspace
  --override_module=rules_kotlin=%workspace%/build/kernel/kleaf/bzlmod/fake_modules/rules_kotlin
  --override_module=protobuf=%workspace%/build/kernel/kleaf/bzlmod/fake_modules/protobuf
  --override_module=rules_java=%workspace%/build/kernel/kleaf/bzlmod/fake_modules/rules_java
)
if [[ "$phase" == preflight ]]; then
  target=//common:kernel_aarch64_config
elif [[ "$phase" == build ]]; then
  target=//common:kernel_aarch64
else
  echo "Unknown build phase: $phase" >&2
  exit 2
fi
printf '%q ' "${bazel[@]}" build "${opts[@]}" "$target"
printf '\n'
"${bazel[@]}" build "${opts[@]}" "$target" 2>&1 | tee "$GITHUB_WORKSPACE/artifacts/$phase.log"
"${bazel[@]}" cquery "${opts[@]}" "$target" --output=files > "$GITHUB_WORKSPACE/artifacts/$phase.outputs.txt"
python3 "$GITHUB_WORKSPACE/scripts/collect_gki.py" "$phase"
