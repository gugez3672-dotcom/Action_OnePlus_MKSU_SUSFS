"""Execute the actual patched Rust listing function against disposable module trees."""
import json
import os
from pathlib import Path
import subprocess
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / '.inputs/BackendSource/userspace/ksud/src/module.rs'
    text = source.read_text('utf-8')
    start = text.index('fn list_module(')
    body = text[start:text.index('\npub fn list_modules()', start)]
    harness = r'''
#![allow(dead_code, unused_variables)]
use std::collections::HashMap;
use std::path::Path;
macro_rules! info { ($($arg:tt)*) => {}; }
macro_rules! warn { ($($arg:tt)*) => {}; }
mod defs {
    pub const DISABLE_FILE_NAME: &str = "disable";
    pub const UPDATE_FILE_NAME: &str = "update";
    pub const REMOVE_FILE_NAME: &str = "remove";
    pub const MODULE_WEB_DIR: &str = "webroot";
    pub const MODULE_ACTION_SH: &str = "action.sh";
}
mod module_config {
    use super::*;
    pub fn get_all_module_configs() -> Result<HashMap<String, HashMap<String, String>>, String> {
        Ok(HashMap::from([
            ("physical".into(), HashMap::from([("override.description".into(), "physical configuration".into())])),
            ("declared".into(), HashMap::from([("override.description".into(), "WRONG configuration".into())])),
        ]))
    }
    pub fn parse_bool_config(s: &str) -> bool { s == "true" }
}
mod preinit {
    use super::*;
    pub fn module_states() -> HashMap<String, String> {
        HashMap::from([("physical".into(), "ok".into()), ("declared".into(), "WRONG".into())])
    }
}
fn read_module_prop(path: &Path) -> Result<HashMap<String, String>, String> {
    Ok(std::fs::read_to_string(path.join("module.prop")).map_err(|e| e.to_string())?
        .lines().filter_map(|line| line.split_once('=')).map(|(k,v)| (k.into(),v.into())).collect())
}
fn resolve_module_icon_path(_: &mut HashMap<String, String>, _: &str, _: &Path) {}
__ACTUAL_FUNCTION__
fn main() {
    let root = std::env::args().nth(1).unwrap();
    let rows = list_module(&root);
    assert_eq!(rows.len(), 7);
    let by_dir: HashMap<_, _> = rows.iter().map(|m| (m["dir_id"].as_str(), m)).collect();
    let physical = by_dir["physical"];
    assert_eq!(physical["id"], "declared");
    assert_eq!(physical["dir_id"], "physical");
    assert_eq!(physical["preinit"], "ok");
    assert_eq!(physical["description"], "physical configuration");
    assert_eq!(physical["mount"], "true");
    assert_eq!(by_dir["empty"]["id"], "empty");
    assert_eq!(by_dir["missing"]["id"], "missing");
    assert_eq!(by_dir["plain"]["mount"], "false");
    assert_eq!(by_dir["skipped"]["mount"], "false");
    assert_eq!(by_dir["disabled"]["enabled"], "false");
    assert_eq!(by_dir["disabled"]["remove"], "true");
    assert_eq!(by_dir["quoted'folder"]["dir_id"], "quoted'folder");
    println!("Actual Rust module listing: 7 fixtures and 13 assertions passed");
}
'''.replace('__ACTUAL_FUNCTION__', body)
    out = ROOT / '.inputs/module-directory-test'
    out.mkdir(exist_ok=True)
    fixture = out / 'modules'
    cases = {'physical': 'id=declared\ndir_id=spoofed\n', 'empty': 'id=\n', 'missing': 'name=missing\n',
             'plain': 'id=plain\n', 'skipped': 'id=skipped\n', 'disabled': 'id=disabled\n',
             "quoted'folder": 'id=declared\n'}
    for directory, prop in cases.items():
        path = fixture / directory
        path.mkdir(parents=True, exist_ok=True)
        (path / 'module.prop').write_text(prop, encoding='utf-8')
    for directory in ('physical', 'skipped'):
        (fixture / directory / 'system').mkdir(exist_ok=True)
    (fixture / 'skipped/skip_mount').touch()
    for flag in ('disable', 'remove'):
        (fixture / 'disabled' / flag).touch()
    (fixture / 'not-a-module').mkdir(exist_ok=True)
    (out / 'main.rs').write_text(harness, encoding='utf-8')
    env = os.environ.copy()
    options = []
    if os.name == 'nt':
        env['RUSTUP_HOME'] = 'D:/CodexTools/rust/runtime'
        compiler = 'D:/CodexTools/rust/cargo/bin/rustc.exe'
        linker = next(Path('D:/CodexTools/llvm-mingw').glob('llvm-mingw-*/bin/x86_64-w64-mingw32-clang.exe'))
        options = ['-C', f'linker={linker}']
    else:
        compiler = shutil.which('rustc')
    executable = out / ('check.exe' if os.name == 'nt' else 'check')
    subprocess.run([compiler, '--edition=2024', *options,
                    str(out / 'main.rs'), '-o', str(executable)], env=env, check=True)
    subprocess.run([str(executable), str(fixture)], check=True)


if __name__ == '__main__':
    main()
