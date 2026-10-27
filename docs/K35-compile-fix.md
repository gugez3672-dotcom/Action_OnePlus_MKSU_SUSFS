# K35 compiler failure and correction

K35 (`6a735e7`, Actions `40525562241`) passed the source/configuration preflight but failed actual stock-Clang compilation of `fs/proc/task_mmu.c`. No verified kernel package was produced.

The official 519 `SUSFS_IS_INODE_SUS_MAP(inode)` macro expands to a compound `&&` expression without surrounding parentheses. Three A67 rollup adaptations used `!MACRO(...)`; negation therefore bound to its first operand rather than the complete predicate. Clang rejected its composition with `||` under `-Wlogical-op-parentheses`.

All three call sites now use `!(MACRO(...))`. The original macro and warning policy are unchanged. The intended rule is: include anonymous VMAs and every file-backed VMA except one matching the complete SUS_MAP predicate; advance `last_vma_end` in every case.

Validation:

- Strict patch application against 33 original pinned source files, with no fuzz/rejects.
- 17 existing unit tests passed.
- 13 real source-regression mutations rejected, including the previous negation spelling; original bytes restored afterward.
- New host-Clang gate compiles the actual official macro, reproduces the old diagnostic, and checks all 32 combinations of file/inode/mapping/flag/process classification.
- 203 source hashes recorded and reverified.
- Full stock-Clang kernel build remains the final validation; no phone operation is implied.

`review/` at repository root preserves the initial Claude-reviewed snapshot. Current correction evidence is in `review/K35-compile-fix/`; each Actions build also exports its effective patches and source fingerprints.
