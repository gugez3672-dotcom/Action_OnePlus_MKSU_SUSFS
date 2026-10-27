package com.daily.notes.data.terminal

/** Display numbers are reusable; session UUIDs remain the process identity. */
internal class DnSessionNumbers {
    private val assigned = linkedMapOf<String, Int>()
    private val released = mutableListOf<Int>()

    fun assign(id: String, preferred: Int? = null): Int {
        assigned[id]?.let { return it }
        val busy = assigned.values.toSet()
        val number = preferred?.takeIf { it > 0 && it !in busy }
            ?: released.lastOrNull { it !in busy }
            ?: generateSequence(1) { it + 1 }.first { it !in busy }
        released.removeAll { it == number }
        assigned[id] = number
        return number
    }

    fun release(id: String) {
        assigned.remove(id)?.let { number ->
            released.removeAll { it == number }
            released.add(number)
        }
    }

    fun retain(ids: Set<String>) {
        assigned.keys.filter { it !in ids }.forEach(::release)
    }

    companion object {
        private val digits = Regex("\\d+")
        fun fromLabel(label: String): Int? = digits.find(label)?.value?.toIntOrNull()
        fun labelWithNumber(label: String, number: Int): String =
            digits.replaceFirst(label, number.toString())
    }
}
