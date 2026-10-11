#!/usr/bin/env python3
"""D73 targeted fix: use raw Termux renderer pixels (not scaledDensity*sp)
and pin A-/A+ font controls so they cannot disappear offscreen."""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/DnPtyTerminal.kt")
s=p.read_text(encoding="utf-8")
def rep(a,b):
    global s
    n=s.count(a)
    if n!=1: raise SystemExit(f"D73 source drift: {a[:100]!r}, count={n}")
    s=s.replace(a,b,1)
rep("    private var fontSp = 16\n", "    private var fontTargetPx = 28\n")
rep("        setFontSp(fontSp)\n", "        setFontPixels(fontTargetPx)\n")
rep('''    fun setFontSp(value: Int) {
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
''',
'''    fun setFontPixels(value: Int) {
        fontTargetPx = value.coerceIn(20, 36)
        val view = display ?: return
        // Termux TerminalRenderer calls Paint.setTextSize(px) directly.
        // No Android dp/sp density multiplication belongs here.
        // On this test device 15px gave 127 columns and ~56px gave 34.
        // 28px targets roughly 68 columns and readable character size.
        if (fontPx != fontTargetPx) {
            fontPx = fontTargetPx
            view.setTextSize(fontPx)
            view.updateSize()
            view.invalidate()
        }
    }
''')
rep('''    var fontSizeSp by rememberSaveable { mutableIntStateOf(16) }
''','''    var fontPixels by rememberSaveable { mutableIntStateOf(28) }
''')
rep('''            update = { controller.setFontSp(fontSizeSp) },
''','''            update = { controller.setFontPixels(fontPixels) },
''')
rep('''            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())
                .padding(vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            val extra = listOf(''',
'''            modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            // Left side scrolls; font controls on the right remain visible.
            Row(
                modifier = Modifier.weight(1f).horizontalScroll(rememberScrollState()),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                val extra = listOf(''')
rep('''            extra.forEach { (label, code) ->
                TextButton(onClick = { controller.send(code) }) { Text(label) }
            }
            TextButton(onClick = { if (fontSizeSp > 12) fontSizeSp-- }) {
                Text("A−")
            }
            TextButton(onClick = { if (fontSizeSp < 22) fontSizeSp++ }) {
                Text("A+")
            }
            TextButton(onClick = { controller.stop(); controller.ensure() }) {
                Text("重开")
            }
''',
'''                extra.forEach { (label, code) ->
                    TextButton(onClick = { controller.send(code) }) { Text(label) }
                }
                TextButton(onClick = { controller.stop(); controller.ensure() }) {
                    Text("重开")
                }
            }
            TextButton(onClick = { if (fontPixels > 20) fontPixels -= 2 },
                contentPadding = PaddingValues(horizontal = 7.dp)) {
                Text("A−")
            }
            TextButton(onClick = { if (fontPixels < 36) fontPixels += 2 },
                contentPadding = PaddingValues(horizontal = 7.dp)) {
                Text("A+")
            }
''')
assert 'scaledDensity' not in s
assert 'fontTargetPx = 28' in s
assert 'fontPixels by rememberSaveable' in s
assert 'setFontPixels(fontPixels)' in s
assert 'Modifier.weight(1f).horizontalScroll' in s
assert 'shouldEnforceCharBasedInput(): Boolean = true' in s
assert 'controller.send(code)' in s
p.write_text(s,encoding="utf-8")
print("D73: 28px Termux font, 20-36px A-/A+ pinned, keep D72 IME and PTY unchanged")
