package com.daily.notes.data.susfs

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class OfficialFsConfigTest {
    private fun config() = OfficialFsConfig.defaults()
    private fun stat(path: String, mode: String) = JSONObject().put("path", path).put("spoof_type", mode)
    private fun reject(value: JSONObject) {
        assertThrows(IllegalArgumentException::class.java) { OfficialFsConfig.compile(value) }
    }

    @Test fun defaultHasNoUnsupportedLoggingCommand() {
        val (early, late) = OfficialFsConfig.compile(config())
        assertFalse(early.contains("enable_log"))
        assertTrue(early.contains("enable_avc_log_spoofing"))
        assertFalse(late.contains("add_sus_kstat"))
    }

    @Test fun capturePrecedesMetamoduleMountAndUpdateFollowsIt() {
        val c = config().put("sus_kstat", JSONArray().put(stat("/system/build.prop", "Normal"))
            .put(stat("/vendor/build.prop", "FullClone")))
        val (early, late) = OfficialFsConfig.compile(c)
        assertTrue(early.contains("'add_sus_kstat' '/system/build.prop'"))
        assertTrue(early.contains("'add_sus_kstat' '/vendor/build.prop'"))
        assertFalse(early.contains("update_sus_kstat"))
        assertTrue(late.contains("'update_sus_kstat' '/system/build.prop'"))
        assertTrue(late.contains("'update_sus_kstat_full_clone' '/vendor/build.prop'"))
        assertFalse(late.contains("'add_sus_kstat'"))
    }

    @Test fun dynamicRulesFollowMountsAndAreShellQuoted() {
        val dangerous = "/data/a'\$(touch /tmp/unwanted); echo bad"
        val c = config().put("sus_map", JSONArray().put(dangerous))
            .put("sus_path", JSONArray().put(JSONObject().put("path", "/system/test").put("is_loop", true)))
            .put("open_redirect", JSONArray().put(JSONObject().put("target_path", "/system/old")
                .put("redirected_path", "/data/new").put("uid_scheme", "UnmountedApp")))
        val (early, late) = OfficialFsConfig.compile(c)
        assertFalse(early.contains("add_sus_map"))
        assertTrue(late.contains("'add_sus_map' '/data/a'\"'\"'\$(touch /tmp/unwanted); echo bad'"))
        assertTrue(late.contains("'add_open_redirect' '/system/old' '/data/new' '3'"))
        assertTrue(late.contains("'add_sus_path_loop' '/system/test'"))
        assertTrue(late.contains("|| status=1"))
        assertTrue(late.endsWith("exit \"\$status\"\n"))
    }

    @Test fun disabledConfigDoesNotRunCommands() {
        val (early, late) = OfficialFsConfig.compile(config().put("enabled", false))
        assertTrue(early.endsWith("exit 0\n"))
        assertTrue(late.endsWith("exit 0\n"))
        assertFalse(early.contains("/fsctl"))
        assertFalse(late.contains("/fsctl"))
    }

    @Test fun rejectsUnsupportedSchemaAndFields() {
        reject(config().put("version", 1))
        reject(config().put("unknown", true))
        reject(config().put("logging", true))
    }

    @Test fun rejectsUnsafePathsAndUnknownUidScheme() {
        for (path in listOf("relative", "/bad\u0000path", "/" + "a".repeat(256))) {
            reject(config().put("sus_map", JSONArray().put(path)))
        }
        reject(config().put("open_redirect", JSONArray().put(JSONObject().put("target_path", "/a")
            .put("redirected_path", "/b").put("uid_scheme", "Unrecognized"))))
    }

    @Test fun rejectsInjectedPriorityPackage() {
        reject(config().put("priority_packages", "com.test.app;reboot"))
        val (_, late) = OfficialFsConfig.compile(config().put("priority_packages", "com.test.app,com.other.app"))
        assertTrue(late.contains("'set_priority_uid_filter' 'com.test.app,com.other.app'"))
    }

    @Test fun staticStatisticsCannotInjectArguments() {
        val entry = stat("/system/file", "Statically").put("statically", JSONObject().put("ino", "1; reboot"))
        reject(config().put("sus_kstat", JSONArray().put(entry)))
    }
}
