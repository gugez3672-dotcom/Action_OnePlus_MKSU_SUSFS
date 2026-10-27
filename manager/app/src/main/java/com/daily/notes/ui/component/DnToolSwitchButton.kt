package com.daily.notes.ui.component

import androidx.compose.foundation.layout.size
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.dp
import com.daily.notes.R

internal enum class DnToolSwitchTarget { Files, Terminal }

/** Both toolbar destinations share the same icon scale, padding and hit area. */
@Composable
internal fun DnToolSwitchButton(
    target: DnToolSwitchTarget,
    contentDescription: String,
    onClick: () -> Unit,
    tint: Color = MaterialTheme.colorScheme.onBackground,
) {
    val drawable = when (target) {
        DnToolSwitchTarget.Files -> R.drawable.dn_switch_files
        DnToolSwitchTarget.Terminal -> R.drawable.dn_switch_terminal
    }
    IconButton(onClick = onClick, modifier = Modifier.size(40.dp)) {
        Icon(
            painter = painterResource(drawable),
            contentDescription = contentDescription,
            modifier = Modifier.size(24.dp),
            tint = tint,
        )
    }
}
