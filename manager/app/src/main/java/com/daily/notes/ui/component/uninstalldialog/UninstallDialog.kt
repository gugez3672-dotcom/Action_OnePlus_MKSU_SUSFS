package com.daily.notes.ui.component.uninstalldialog

import androidx.compose.runtime.Composable
import com.daily.notes.ui.LocalUiMode
import com.daily.notes.ui.UiMode

@Composable
fun UninstallDialog(
    show: Boolean,
    onDismissRequest: () -> Unit
) {
    when (LocalUiMode.current) {
        UiMode.Miuix -> UninstallDialogMiuix(show, onDismissRequest)
        UiMode.Material -> UninstallDialogMaterial(show, onDismissRequest)
    }
}
