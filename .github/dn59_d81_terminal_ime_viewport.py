#!/usr/bin/env python3
"""D81/D82: keep live PTY prompt visible, without double-reserving IME height.

The activity already adjusts its viewport for IME; avoid Compose imePadding().
Refresh the PTY size and follow the live cursor on keyboard resize.
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
    // Watch IME animation only to refresh the live cursor. The activity already
    // resizes the available viewport; do not subtract IME insets twice.
    val imeBottomPx = WindowInsets.ime.getBottom(LocalDensity.current)
    LaunchedEffect(imeBottomPx) {
        if (imeBottomPx > 0) {
            withFrameNanos { } // wait for the resized AndroidView layout frame
            controller.followImeViewport()
        }
    }
""",
)
# D82: the host activity already resizes its Compose viewport for the IME.
# The D81 imePadding() shrinks it a second time and leaves a large empty strip
# between the extra-key row and the on-screen keyboard. Use the resized bounds
# directly; TerminalView.onSizeChanged updates PTY dimensions automatically.
assert "setTopRow(0)" in s
assert "WindowInsets.ime.getBottom(LocalDensity.current)" in s
assert "Column(Modifier.fillMaxSize())" in s
assert "Column(Modifier.fillMaxSize().imePadding())" not in s
assert "view.updateSize()" in s
assert "controller.followImeViewport()" in s
assert 'shouldEnforceCharBasedInput(): Boolean = true' in s
assert 'setFontPixels(fontPixels)' in s
p.write_text(s, encoding="utf-8")
print("D82: remove double IME padding, retain PTY resize and live cursor follow")
