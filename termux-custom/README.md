# Aurel Terminal custom Termux build

This branch contains an isolated build pipeline for a custom-package Termux build.

## Build target

- Android application id: `io.aurel.terminal`
- Display name: `Aurel Terminal`
- ABI: `arm64-v8a`
- Termux package variant: `apt-android-7`
- Custom prefix: `/data/data/io.aurel.terminal/files/usr`

The Java namespaces remain `com.termux.*`. Upstream explicitly recommends not renaming
those namespaces because doing so breaks internal components and Termux packages.

## Bundled tools

The bootstrap is built from source for the custom prefix and additionally includes:

- OpenSSH
- curl
- wget
- git
- jq
- tmux

The normal bootstrap already includes bash, coreutils, procps, nano, lsof, net-tools,
unzip and other base utilities.

## Package repository limitation

Official Termux repositories publish packages for the `com.termux` prefix. Those
packages must not be mixed with this custom-prefix build. The workflow therefore
builds the bootstrap from source and bundles the common tools above.

## Signing

The first build uses the upstream public debug/test signing key. It is convenient
for personal testing but is not a private production signing identity.

## Scope

This build changes the app's legitimate Android package namespace and matching
runtime prefix. It does not hook, tamper with, or bypass security checks in other
applications.
