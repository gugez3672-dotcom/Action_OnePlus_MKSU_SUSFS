#!/usr/bin/env python3
"""DN45: terminal integrated input/output canvas, Enter-to-send and bounded lazy lines.

This is a terminal UI improvement; existing pipes are NOT advertised as PTY.
"""
from pathlib import Path
p=Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/ToolsPage.kt")
s=p.read_text()
def swap(old,new):
    global s
    if s.count(old)!=1: raise SystemExit("DN45 source drift "+old[:95]+" count "+str(s.count(old)))
    s=s.replace(old,new,1)

swap('import androidx.compose.foundation.lazy.LazyColumn\n',
'''import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
''')
swap('import androidx.compose.ui.text.font.FontFamily\n',
'''import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.ImeAction
''')
swap('''    var terminalInput by rememberSaveable { mutableStateOf("") }
''',
'''    var terminalInput by rememberSaveable { mutableStateOf("") }
    val terminalScroll = rememberLazyListState()
    var followOutput by remember { mutableStateOf(true) }
    val outputLines = remember(terminalOutput) { terminalOutput.lineSequence().toList() }
    LaunchedEffect(terminalOutput, followOutput, tab) {
        if (tab == 1 && followOutput && outputLines.isNotEmpty()) {
            terminalScroll.scrollToItem(outputLines.lastIndex)
        }
    }
''')
start=s.index('''                Surface(
                    modifier = Modifier.fillMaxWidth().weight(1f).padding(top = 8.dp),
                    color = MaterialTheme.colorScheme.surfaceContainerLowest,''')
end=s.index('''            }
        }
    }

    if (showActions) {''',start)
replacement=r'''                Surface(
                    modifier = Modifier.fillMaxWidth().weight(1f).padding(horizontal = 5.dp, vertical = 4.dp),
                    color = Color(0xFF1F2429),
                    shape = MaterialTheme.shapes.small,
                ) {
                    Column(Modifier.fillMaxSize().padding(9.dp)) {
                        LazyColumn(
                            state = terminalScroll,
                            modifier = Modifier.weight(1f).fillMaxWidth(),
                        ) {
                            items(outputLines) { line ->
                                Text(
                                    text = line.ifEmpty { " " },
                                    fontFamily = FontFamily.Monospace,
                                    fontSize = androidx.compose.ui.unit.TextUnit.Unspecified,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = Color(0xFFE2E8E7),
                                    softWrap = true,
                                )
                            }
                        }
                        HorizontalDivider(color = Color(0xFF556066))
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 5.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text("# ", color = Color(0xFF99CFAB), fontFamily = FontFamily.Monospace)
                            BasicTextField(
                                value = terminalInput,
                                onValueChange = { terminalInput = it },
                                modifier = Modifier.weight(1f),
                                singleLine = true,
                                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                                keyboardActions = KeyboardActions(onSend = { sendTerminalLine() }),
                                textStyle = MaterialTheme.typography.bodyMedium.copy(
                                    fontFamily = FontFamily.Monospace,
                                    color = Color.White,
                                ),
                                cursorBrush = androidx.compose.ui.graphics.SolidColor(Color.White),
                                decorationBox = { inner ->
                                    Box {
                                        if (terminalInput.isEmpty()) {
                                            Text("输入命令后按回车", color = Color(0xFF99A2A9),
                                                style = MaterialTheme.typography.bodySmall)
                                        }
                                        inner()
                                    }
                                },
                            )
                        }
                    }
                }
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 5.dp, vertical = 2.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    TextButton(onClick = { session.sendRaw("\t") }, enabled = session.isAlive) {
                        Text("Tab")
                    }
                    TextButton(onClick = { followOutput = !followOutput }) {
                        Text(if (followOutput) "跟随输出 ✓" else "跟随输出")
                    }
                    TextButton(onClick = {
                        session.sendRaw("\u0003")
                    }, enabled = session.isAlive) {
                        Text("Ctrl+C")
                    }
                    TextButton(onClick = { tab = 0 }) { Text("文件") }
                }
'''
s=s[:start]+replacement+s[end:]
p.write_text(s)
assert 'KeyboardActions(onSend = { sendTerminalLine() })' in s
assert 'BasicTextField(' in s
assert 'LazyColumn(' in s and 'state = terminalScroll' in s
assert 'followOutput' in s
assert 'RootInteractiveSession(' in s
assert 'fun launchDetached' in s or 'fun runScriptDetached' in s or 'DETACHED_LIVE' in s
assert 'DnDualFiles(' in s
print("DN45 integrated terminal canvas with IME Send, lazy output lines and follow toggle.")
