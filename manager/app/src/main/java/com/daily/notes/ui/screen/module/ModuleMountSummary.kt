package com.daily.notes.ui.screen.module

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.daily.notes.R
import com.daily.notes.data.model.Module

/** Uses the explicitly loaded list only; never probes modules from home or cold launch. */
@Composable
internal fun ModuleMountSummary(modules: List<Module>) {
    var expanded by remember { mutableStateOf(false) }
    val metas = modules.filter { it.metamodule }
    val mountModules = modules.filter { !it.metamodule && it.needsMount }
    val enabledMetas = metas.count { it.enabled && !it.remove }
    val summary = stringResource(R.string.dn_mount_summary, enabledMetas, mountModules.size)
    Text(summary, modifier = Modifier.fillMaxWidth().clickable { expanded = true }.padding(16.dp))
    if (expanded) {
        val metaLabel = stringResource(R.string.dn_mount_meta)
        val mountLabel = stringResource(R.string.dn_mount_required)
        val otherLabel = stringResource(R.string.dn_mount_other)
        val enabled = stringResource(R.string.dn_mount_enabled)
        val disabled = stringResource(R.string.dn_mount_disabled)
        val pending = stringResource(R.string.dn_mount_pending)
        val removed = stringResource(R.string.dn_mount_removed)
        val rows = modules.joinToString("\n\n") { module ->
            val role = when {
                module.metamodule -> metaLabel
                module.needsMount -> mountLabel
                else -> otherLabel
            }
            val state = when {
                module.remove -> removed
                module.update -> pending
                module.enabled -> enabled
                else -> disabled
            }
            val identity = if (module.id == module.declaredId) module.id else "${module.id} (${module.declaredId})"
            "${module.name} [$identity]\n$role · $state"
        }
        AlertDialog(
            onDismissRequest = { expanded = false },
            title = { Text(stringResource(R.string.dn_mount_title)) },
            text = {
                Text(stringResource(R.string.dn_mount_explanation) + "\n\n" + rows,
                    modifier = Modifier.verticalScroll(rememberScrollState()))
            },
            confirmButton = { TextButton(onClick = { expanded = false }) { Text(stringResource(android.R.string.ok)) } },
        )
    }
}
