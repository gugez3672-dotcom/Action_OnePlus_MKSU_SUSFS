#!/usr/bin/env python3
"""D81: keep the live PTY prompt visible when Android IME appears.

The terminal view must receive IME-safe space, recalculate its PTY size,
and return to the live screen after keyboard resize. No synthetic keystrokes.
"""
from pathlib import Path

p = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnPtyTerminal.kt")
s = p.read_text(encoding="utf-8")

def rep(old: str, new: str):
    global s
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"D81 terminal IME anchor drift: {old[:120]!r}; count={n}")
    s = s.replace(old, new, 1)

rep(
    "import androidx.compose.ui.platform.LocalContext\n",
    "import androidx.compose.ui.platform.LocalContext\nimport androidx.compose.ui.platform.LocalDensity\n",
)
rep(
    "    fun setFontPixels(value: Int) {\n",
    """    // Termux TerminalView 0.118.0 exposes setTopRow(0) and onScreenUpdated().
    // Refresh the PTY dimensions after Compose reduces the visible area for IME.
    fun followImeViewport() {
        val view = display ?: return
        view.post {
            if (display === view) {
                view.updateSize()
                view.setTopRow(0)
                view.onScreenUpdated()
            }
        }
    }
    fun setFontPixels(value: Int) {
""",
)
rep(
    "    var fontPixels by rememberSaveable { mutableIntStateOf(28) }\n",
    """    var fontPixels by rememberSaveable { mutableIntStateOf(28) }
    // When ColorOS keyboard opens, the Compose viewport must exclude its insets.
    // The IME bottom is read reactively so terminal output follows animation.
    val imeBottomPx = WindowInsets.ime.getBottom(LocalDensity.current)
    LaunchedEffect(imeBottomPx) {
        if (imeBottomPx > 0) {
            withFrameNanos { } // wait for the resized AndroidView layout frame
            controller.followImeViewport()
        }
    }
""",
)
rep(
    "    Column(Modifier.fillMaxSize()) {\n",
    "    Column(Modifier.fillMaxSize().imePadding()) {\n",
)
assert "setTopRow(0)" in s
assert "WindowInsets.ime.getBottom(LocalDensity.current)" in s
assert "Column(Modifier.fillMaxSize().imePadding())" in s
assert "view.updateSize()" in s
assert "controller.followImeViewport()" in s
assert 'shouldEnforceCharBasedInput(): Boolean = true' in s
assert 'setFontPixels(fontPixels)' in s
p.write_text(s, encoding="utf-8")
print("D81: IME-aware PTY viewport resize and scroll-to-live-output, preserving terminal inputs")
