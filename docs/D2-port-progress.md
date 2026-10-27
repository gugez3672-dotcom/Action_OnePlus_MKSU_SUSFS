# D2 migration work in progress

This branch is an integration checkpoint, not a distributable manager.

- Official manager base: KernelSU `75e179d378d7aaa0de8946358a3384444c3e36b0`.
- DN feature input: final D1.1.1/36111 APK `06b764651d8c14af8f79fe2fd00327023faa6d51119b2742241e6d2ba0083eb3`.
- Frozen input evidence and verification limits: `D111-inputs.json`.
- Imported official management pages and JNI/UAPI, migrated namespace, runtime components and AIDL identity.
- Ported final DN dual-pane files, PTY/ATE sessions, terminal lifecycle, file operations, APK staging and runtime assets.
- Ported D111 heartbeat helpers and read/toggle error separation; added settings title user switch and two-second traffic clearing.
- Remaining: all-user authorization and batch controls; hidden module list; full SUSFS configuration against official 519 tool; fresh official backend build; complete static identity audit; final packaging and local signing.

The integration workflow compiles code only. It cannot produce a release APK, use a signing credential, install an app, or touch a phone.

Windows native AIDL dependency parsing and protoc do not handle the project's Chinese path consistently. AIDL and protobuf generated correctly in separate checks, but the full local Gradle check remains unpassed. Linux CI is the authoritative integration check. No system settings or aliases were introduced.
