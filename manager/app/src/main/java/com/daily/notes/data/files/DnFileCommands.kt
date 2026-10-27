package com.daily.notes.data.files

import android.content.Context

internal class DnFileCommands(context: Context) {
    private val operation = context.assets.open("dn-files/operate.sh").bufferedReader().use { it.readText() }
    private fun quote(value: String) = "'" + value.replace("'", "'\"'\"'") + "'"
    fun build(kind: String, source: String, destination: String, collision: String): String =
        "(set -- " + listOf(kind, source, destination, collision).joinToString(" ", transform = ::quote) + "\n" + operation + "\n)"
}
