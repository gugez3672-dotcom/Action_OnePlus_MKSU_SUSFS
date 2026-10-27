package com.daily.notes.ui.component

import androidx.compose.runtime.Composable
import com.daily.notes.NativeApi

@Composable
fun KsuIsValid(
    content: @Composable () -> Unit
) {
    val isManager = NativeApi.isManager
    val ksuVersion = if (isManager) NativeApi.version else null

    if (ksuVersion != null) {
        content()
    }
}
