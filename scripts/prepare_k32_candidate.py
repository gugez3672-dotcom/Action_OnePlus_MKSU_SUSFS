#!/usr/bin/env python3
"""K32 review-only derivative of the exact K30 build definition (route A).

Never builds, commits, flashes or starts a workflow. Writes review/ only.

Route A: keep the K30 SUSFS pin (8dce4337) and its audited post-2.3.0 backport.
The non-SELinux kernel code of cctv18 5f236a7b is identical to K30 after that
backport (proven by a tree diff). Its SELinux part replaces the
K30/upstream-#3877 dual-policy path and drops the #3873 global sidtab sync,
so it is not taken.

Every K30 branch-name condition becomes an explicit profile (PLK110_PROFILE=k32).
A K32 step never depends on the branch name and never skips silently.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

K30_BASE = "2fdd663bdae89179c1aad42dda72cb865f5bb92c"
K30_BRANCH = "k30-20261015-ksu-susfs-audit"
K32_BRANCH = "k32-review-only"
K30_WORKFLOW = ".github/workflows/Build-ReSukiSU-StockSched.yml"
REVIEW_TARGET = "review/Build-ReSukiSU-K32-CANDIDATE.yml"


def once(src: str, old: str, new: str, title: str) -> str:
    if src.count(old) != 1:
        raise RuntimeError(f"{title}: expected exactly one pre-image, found {src.count(old)}")
    return src.replace(old, new, 1)


def verify_k30_checkout(root: Path) -> None:
    head = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    if head != K30_BASE:
        raise RuntimeError(f"not the frozen K30 commit: {head}")
    dirty = subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain", "--", ".github", "scripts", "baselines"], text=True)
    if dirty.strip():
        raise RuntimeError("K30 build definition has local modifications:\n" + dirty)


def rewrite_workflow(wf: str, build_branch: str | None = None) -> str:
    if "Build PLK110 ReSukiSU + SUSFS" not in wf:
        raise RuntimeError("wrong workflow")
    title = "REVIEW-ONLY K32" if build_branch is None else "Build PLK110 K32"
    wf = once(wf, "name: Build PLK110 ReSukiSU + SUSFS (Stock Scheduler ABI)",
              f"name: {title} PLK110 ReSukiSU + SUSFS (Stock Scheduler ABI)".replace(
                  "Build PLK110 K32 PLK110", "Build PLK110 K32"), "workflow name")
    # Locate the trigger block only after the rename (offsets shift).
    if wf.count("\n  push:\n") != 1:
        raise RuntimeError("unexpected trigger layout")
    start = wf.index("\n  push:\n") + 1
    end = wf.index("permissions:", start)
    if build_branch is None:
        # Review-only: no push trigger at all.
        wf = wf[:start] + "\n" + wf[end:]
    else:
        # Build mode: only this K32 branch, only when the trigger file changes.
        wf = (wf[:start] + "  push:\n    branches:\n      - " + build_branch + "\n"
              "    paths:\n      - .github/plk110-resukisu-trigger\n\n" + wf[end:])
    wf = once(wf, "env:\n  DEVICE: PLK110\n",
              "env:\n  # Explicit build profile; never derived from the branch name.\n"
              "  PLK110_PROFILE: k32\n  DEVICE: PLK110\n", "profile env")

    # 1) step-level if: conditions -> unconditional (the profile is the workflow itself)
    for cond in (
        "        if: github.ref_name == 'resukisu-pguard-v2-ksu3877-experimental' || "
        "github.ref_name == 'resukisu-pguard-v2-selinux-hardening-boot-open' || "
        f"github.ref_name == '{K30_BRANCH}'\n",
        "        if: github.ref_name == 'resukisu-pguard-v2-selinux-hardening-boot-open' || "
        f"github.ref_name == '{K30_BRANCH}'\n",
        f"        if: github.ref_name == '{K30_BRANCH}'\n",
    ):
        wf = once(wf, cond, "", "step condition")
    # 2) shell conditions (Configure step and Record step)
    shell_old = ('if [ "$GITHUB_REF_NAME" = "resukisu-pguard-v2-selinux-hardening-boot-open" ] || '
                 f'[ "$GITHUB_REF_NAME" = "{K30_BRANCH}" ]; then')
    if wf.count(shell_old) != 2:
        raise RuntimeError(f"expected 2 shell branch conditions, found {wf.count(shell_old)}")
    wf = wf.replace(shell_old, 'if [ "$PLK110_PROFILE" = "k32" ]; then')
    # 3) Python condition inside the Configure step
    wf = once(wf,
              "if __import__('os').environ.get('GITHUB_REF_NAME') in "
              f"('resukisu-pguard-v2-selinux-hardening-boot-open', '{K30_BRANCH}'):",
              "if __import__('os').environ['PLK110_PROFILE'] == 'k32':",
              "python profile condition")

    # Environment drift (2026-10-24): storage.googleapis.com now serves repo
    # launcher v2.69, so the pinned SHA (unchanged) fails. Fetch the identical
    # pinned launcher from the official git-repo tag v2.68.1 (same bytes as
    # tags v2.65..v2.68.1 = 1211b57b...); the SHA256 check below is kept.
    wf = once(wf,
              "          curl --fail --location --retry 3             "
              "https://storage.googleapis.com/git-repo-downloads/repo             --output /tmp/repo\n",
              "          # Pinned launcher bytes from the official git-repo tag (googleapis now serves v2.69).\n"
              "          curl --fail --location --retry 3 \\\n"
              "            'https://gerrit.googlesource.com/git-repo/+/refs/tags/v2.68.1/repo?format=TEXT' \\\n"
              "            | base64 -d > /tmp/repo\n",
              "repo launcher source")

    # K32 kernel fixes after the K30 fixes, before the strict-manager/PGuard config.
    anchor = "      - name: Configure frozen kernel 11 baseline + Partition Guard v2\n"
    wf = once(wf, anchor,
              "      - name: K32 kernel fixes (#3871 sync scan, #3733, get_managers RCU, #3924)\n"
              "        run: |\n"
              "          set -euo pipefail\n"
              "          python3 -m py_compile scripts/apply_k32_kernel_fixes.py\n"
              "          python3 scripts/apply_k32_kernel_fixes.py\n"
              "          git -C kernel_workspace/kernel_platform/KernelSU diff --check\n"
              "          test -s artifacts/K32_KERNEL_FIXSET.txt\n\n" + anchor, "K32 fix step")
    # Static invariants only after strict manager + PGuard sources exist.
    anchor2 = "      - name: Publish exact A67 stock IKCONFIG\n"
    wf = once(wf, anchor2,
              "      - name: K32 static invariants (after strict manager + PGuard)\n"
              "        run: |\n"
              "          set -euo pipefail\n"
              "          python3 scripts/k32_verify_susfs.py\n"
              "          python3 scripts/k32_verify_kernel.py\n\n" + anchor2, "K32 verify step")
    wf = once(wf, "          cp scripts/apply_susfs_post230_fixes.py artifacts/\n",
              "          cp scripts/apply_susfs_post230_fixes.py artifacts/\n"
              "          cp scripts/apply_k32_kernel_fixes.py scripts/k32_verify_susfs.py "
              "scripts/k32_verify_kernel.py artifacts/\n", "record K32 scripts")

    # Fail-closed audit of the result.
    head = wf[:wf.index("permissions:")]
    expect = "on:\n  workflow_dispatch:\n"
    if build_branch is not None:
        expect += ("  push:\n    branches:\n      - " + build_branch +
                   "\n    paths:\n      - .github/plk110-resukisu-trigger\n")
    if expect not in head or head.count("branches:") != (0 if build_branch is None else 1):
        raise RuntimeError("trigger block malformed:\n" + head)
    leftover = [l for l in wf.splitlines() if K30_BRANCH in l or
                ("GITHUB_REF_NAME" in l) or ("github.ref_name ==" in l)]
    if leftover:
        raise RuntimeError("branch-name gating left:\n" + "\n".join(leftover))
    if "SUSFS4OKI_COMMIT: 8dce4337bcd15807c5449bbeff6e02a967138db0" not in wf:
        raise RuntimeError("route A keeps the audited K30 SUSFS pin")
    for must in ("python3 scripts/apply_susfs_post230_fixes.py",
                 "python3 scripts/port_ksu_3877_selinux_hide.py",
                 "python3 scripts/apply_plk110_selinux_correctness.py",
                 "python3 scripts/apply_k30_upstream_fixes.py",
                 "python3 scripts/apply_k32_kernel_fixes.py"):
        if wf.count(must) != 1:
            raise RuntimeError(f"required patch step missing or duplicated: {must}")
    order = [wf.index(s) for s in ("apply_k30_upstream_fixes.py\n", "apply_k32_kernel_fixes.py\n",
                                   "prepare_resukisu_config.py\n", "k32_verify_kernel.py\n")]
    if order != sorted(order):
        raise RuntimeError("K32 step order wrong")
    return wf


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--k30", type=Path, required=True)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--build-branch", help="write a build workflow in place (push trigger for this branch only)")
    a = cli.parse_args()
    verify_k30_checkout(a.k30)
    wf = rewrite_workflow((a.k30 / K30_WORKFLOW).read_text(encoding="utf-8"), a.build_branch)
    if a.build_branch:
        (a.output / K30_WORKFLOW).write_text(wf, encoding="utf-8", newline="\n")
        print(K30_WORKFLOW)
        return
    (a.output / "review").mkdir(parents=True, exist_ok=True)
    (a.output / REVIEW_TARGET).write_text(wf, encoding="utf-8", newline="\n")
    (a.output / "review/SOURCE_PROVENANCE.txt").write_text(
        f"K30_commit={K30_BASE} (verified with git rev-parse)\n"
        "SUSFS=cctv18 8dce4337 + audited post-2.3.0 fixset (route A)\n"
        "NOT COMPILED / NOT COMMITTED / NOT FLASHED\n", encoding="utf-8", newline="\n")
    print(REVIEW_TARGET)


if __name__ == "__main__":
    main()
