from pathlib import Path
import xml.etree.ElementTree as ET

ANDROID_NS = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID_NS)
ET.register_namespace("tools", "http://schemas.android.com/tools")

# 1) Custom visible APK revision; ReSukiSU core remains 35154.
gradle = Path("source/manager/app/build.gradle.kts")
text = gradle.read_text()
needle = 'versionName = managerVersionName'
if text.count(needle) != 1:
    raise SystemExit("unexpected versionName assignment")
gradle.write_text(text.replace(needle, 'versionName = "v4.2.0-rc2-DN23"', 1))

# 2) Desktop launcher: expose only MAIN/LAUNCHER on main + alternate alias.
manifest = Path("source/manager/app/src/main/AndroidManifest.xml")
tree = ET.parse(manifest)
root = tree.getroot()
app = root.find("application")
if app is None:
    raise SystemExit("manifest application node missing")

def aname(node):
    return node.get(f"{{{ANDROID_NS}}}name")

def restore_launcher_filter(node):
    for filt in list(node.findall("intent-filter")):
        node.remove(filt)
    filt = ET.SubElement(node, "intent-filter")
    action = ET.SubElement(filt, "action")
    action.set(f"{{{ANDROID_NS}}}name", "android.intent.action.MAIN")
    category = ET.SubElement(filt, "category")
    category.set(f"{{{ANDROID_NS}}}name", "android.intent.category.LAUNCHER")

main = next((x for x in app.findall("activity") if aname(x) == ".ui.MainActivity"), None)
alias = next((x for x in app.findall("activity-alias") if aname(x) == ".ui.MainActivityAlias"), None)
if main is None or alias is None:
    raise SystemExit("launcher components missing")
main.set(f"{{{ANDROID_NS}}}exported", "true")
main.set(f"{{{ANDROID_NS}}}enabled", "true")
alias.set(f"{{{ANDROID_NS}}}exported", "true")
alias.set(f"{{{ANDROID_NS}}}enabled", "false")
restore_launcher_filter(main)
restore_launcher_filter(alias)
tree.write(manifest, encoding="utf-8", xml_declaration=True)

# 3) Restore alternate-icon setting and fix component class names after applicationId rewrite.
settings_repo = Path("source/manager/app/src/main/java/com/resukisu/resukisu/data/settings/SettingsPlatformRepository.kt")
text = settings_repo.read_text()
text = text.replace(
    '            useAltIcon = false,\n',
    '            useAltIcon = settings.getBoolean("use_alt_icon", false),\n',
    1,
)
text = text.replace(
    '            is PlatformSetting.AlternateIcon ->\n'
    '                settings.putBoolean("use_alt_icon", false)\n',
    '            is PlatformSetting.AlternateIcon -> {\n'
    '                settings.putBoolean("use_alt_icon", setting.enabled)\n'
    '                toggleLauncherIcon(setting.enabled)\n'
    '            }\n',
    1,
)
if "private fun toggleLauncherIcon" not in text:
    marker = "    private fun loadModuleUpdatePreference(): Boolean {"
    fn = '''    private fun toggleLauncherIcon(useAlt: Boolean) {
        val packageName = application.packageName
        val main = ComponentName(packageName, "com.resukisu.resukisu.ui.MainActivity")
        val alias = ComponentName(packageName, "com.resukisu.resukisu.ui.MainActivityAlias")
        application.packageManager.setComponentEnabledSetting(
            if (useAlt) alias else main,
            PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
            PackageManager.DONT_KILL_APP,
        )
        application.packageManager.setComponentEnabledSetting(
            if (useAlt) main else alias,
            PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
            PackageManager.DONT_KILL_APP,
        )
    }

'''
    if marker not in text:
        raise SystemExit("toggle insertion marker missing")
    text = text.replace(marker, fn + marker, 1)
settings_repo.write_text(text)

# Restore alternate-icon UI item removed by the previous hidden-manager patch.
theme = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/themeSettings/ThemeSettings.kt")
text = theme.read_text()
if "Icons.TwoTone.Android" not in text:
    import_anchor = "import androidx.compose.material.icons.twotone.Animation\n"
    if import_anchor not in text:
        raise SystemExit("theme icon import anchor missing")
    text = text.replace(import_anchor, import_anchor + "import androidx.compose.material.icons.twotone.Android\n", 1)

if "icon_switch_title" not in text:
    anchor = "        item {\n            // 显示更多模块信息"
    icon_item = '''        item {
            // 图标切换
            SettingsSwitchWidget(
                icon = Icons.TwoTone.Android,
                title = stringResource(R.string.icon_switch_title),
                description = stringResource(R.string.icon_switch_summary),
                checked = settingsUiState.useAltIcon,
                onCheckedChange = { enabled ->
                    settingsViewModel.dispatch(SettingsUiAction.SetAlternateIcon(enabled))
                }
            )
        }

'''
    if anchor not in text:
        raise SystemExit("alternate-icon UI insertion anchor missing")
    text = text.replace(anchor, icon_item + anchor, 1)
theme.write_text(text)

# 4) Distinguish the same package across Android users in the authorization list.
superuser = Path("source/manager/app/src/main/java/com/resukisu/resukisu/ui/screen/main/SuperUserPage.kt")
text = superuser.read_text()
if "val userId = appGroup.uid / 100000" not in text:
    text = text.replace(
        "    val mainApp = appGroup.mainApp\n",
        "    val mainApp = appGroup.mainApp\n    val userId = appGroup.uid / 100000\n",
        1,
    )
if 'label = "用户 $userId"' not in text:
    anchor = '                if (appGroup.allowSu) {\n'
    badge = '''                LabelText(
                    label = "用户 $userId",
                    containerColor = MaterialTheme.colorScheme.secondaryContainer,
                )
'''
    if anchor not in text:
        raise SystemExit("user badge insertion anchor missing")
    text = text.replace(anchor, badge + anchor, 1)
superuser.write_text(text)

# 5) Restore the upstream alternate icon assets. The hidden patch overwrote them.
# They are recovered directly from the pinned source commit by the workflow in a later step.

# Assertions.
assert 'versionName = "v4.2.0-rc2-DN23"' in gradle.read_text()
assert 'android.intent.category.LAUNCHER' in manifest.read_text()
assert 'toggleLauncherIcon(setting.enabled)' in settings_repo.read_text()
assert 'com.resukisu.resukisu.ui.MainActivity"' in settings_repo.read_text()
assert "icon_switch_title" in theme.read_text()
assert 'label = "用户 $userId"' in superuser.read_text()
