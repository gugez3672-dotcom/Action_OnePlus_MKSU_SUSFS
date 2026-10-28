package com.daily.notes.ui.component

import androidx.compose.runtime.Composable
import com.daily.notes.NativeApi

@Composable
fun RuntimeIsValid(
    content: @Composable () -> Unit
) {
    val isManager = NativeApi.isManager
    val runtimeVersion = if (isManager) NativeApi.version else null

    if (runtimeVersion != null) {
        content()
    }
}
