package com.daily.notes.data.repository

import com.daily.notes.data.model.Module
import com.daily.notes.data.model.ModuleUpdateInfo

interface ModuleRepository {
    suspend fun getModules(): Result<List<Module>>
    suspend fun checkUpdate(module: Module): Result<ModuleUpdateInfo>
}
