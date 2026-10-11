#!/usr/bin/env python3
"""D72: fix ColorOS IME composing/Enter latency and Termux TerminalView font sizing.

TermuxView is final: preserve its native event/PTY machinery, use its supported
TerminalViewClient input mode, and set text size in actual screen pixels rather
than a raw unscaled integer. The IME fix should be validated on device.
"""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnPtyTerminal.kt")
s=p.read_text(encoding="utf-8")
def rep(a,b):
    global s
    n=s.count(a)
    if n!=1: raise SystemExit("D72 terminal anchor drift "+repr(a[:95])+" n="+str(n))
    s=s.replace(a,b,1)
rep(
    '''import androidx.compose.runtime.*
''',
    '''import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
'''
)
rep(
    '''    private var display: TerminalView? = null
''',
    '''    private var display: TerminalView? = null
    private var fontSp = 16
    private var fontPx = 0
'''
)
rep(
    '''        override fun shouldEnforceCharBasedInput(): Boolean = false
''',
    '''        // Visible-password character input disables delayed IME composition.
        // This prevents the first Return key from merely committing pending text
        // instead of delivering it to the PTY (notably some ColorOS keyboards).
        override fun shouldEnforceCharBasedInput(): Boolean = true
'''
)
rep(
    '''        view.setTextSize(15)
''',
    '''        fontPx = 0
        setFontSp(fontSp)
'''
)
rep(
    '''    fun detach() { display = null }
''',
    '''    fun detach() {
        display = null
        fontPx = 0
    }
    fun setFontSp(value: Int) {
        fontSp = value.coerceIn(12, 22)
        val view = display ?: return
        // Termux TerminalRenderer uses Paint.setTextSize(px) directly.
        // Passing "15" produced ~127 columns on this device and illegible text.
        val nextPx = (fontSp * view.resources.displayMetrics.scaledDensity)
            .toInt().coerceAtLeast(18)
        if (fontPx != nextPx) {
            fontPx = nextPx
            view.setTextSize(nextPx)
            view.updateSize() // propagates new PTY rows/columns to stty.
            view.invalidate()
        }
    }
'''
)
rep(
    '''    val ctx = LocalContext.current
    DisposableEffect(controller) { onDispose { controller.detach() } }
''',
    '''    val ctx = LocalContext.current
    var fontSizeSp by rememberSaveable { mutableIntStateOf(16) }
    DisposableEffect(controller) { onDispose { controller.detach() } }
'''
)
rep(
    '''            update = {},
''',
    '''            update = { controller.setFontSp(fontSizeSp) },
'''
)
rep(
    '''            TextButton(onClick = { controller.stop(); controller.ensure() }) {
                Text("重开")
            }
''',
    '''            TextButton(onClick = { if (fontSizeSp > 12) fontSizeSp-- }) {
                Text("A−")
            }
            TextButton(onClick = { if (fontSizeSp < 22) fontSizeSp++ }) {
                Text("A+")
            }
            TextButton(onClick = { controller.stop(); controller.ensure() }) {
                Text("重开")
            }
'''
)
assert 'shouldEnforceCharBasedInput(): Boolean = true' in s
assert 'fontSp * view.resources.displayMetrics.scaledDensity' in s
assert 'fontSizeSp by rememberSaveable' in s
assert 'view.setTextSize(nextPx)' in s
assert 'controller.send(code)' in s
assert 'DnPtyTerminalPanel' in s
p.write_text(s,encoding="utf-8")
print("D72: ColorOS char-based IME, 16sp responsive font with A-/A+ and PTY resize; no protocol changes")
