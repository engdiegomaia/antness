---
name: android-aosp
description: Android/AOSP embedded development — repo manifests, Soong/Android.bp, HALs and HIDL/AIDL, SELinux policy, board configuration, and debugging with logcat/dumpsys. Use when Android.bp or device/<vendor>/ is present.
track: linux-embedded
---

# Android / AOSP on Embedded

## Orient first

```bash
cat .repo/manifest.xml                    # or .repo/manifests/*.xml — the pinned revisions
cat build/make/core/version_defaults.mk | grep PLATFORM_VERSION
ls device/<vendor>/<board>/
cat device/<vendor>/<board>/BoardConfig.mk
```

Know: Android version, kernel version, vendor BSP (NXP, Qualcomm, Rockchip),
Treble/GKI status, and whether the build is `user`, `userdebug`, or `eng`.
Those three build variants differ in root access, SELinux enforcement and debuggability —
never test a security property on `eng` and claim it holds on `user`.

## Build

```bash
repo init -u <url> -b <branch> -m <manifest.xml>    # pinned manifest
repo sync -j8 -c --no-tags

source build/envsetup.sh
lunch <product>-<release>-<variant>       # e.g. myboard-trunk_staging-userdebug
m -j$(nproc)

m <module>                                # single module
mma                                       # module + dependencies in the current dir
m installclean                            # between lunch targets — not a full clean
```

`repo sync` without a pinned manifest is not reproducible. Snapshot with
`repo manifest -r -o pinned.xml` for every release.

## Board configuration

```
device/<vendor>/<board>/
├── BoardConfig.mk          # partitions, kernel, architecture, AVB, SELinux dirs
├── <board>.mk              # PRODUCT_* : packages, properties, copy_files
├── AndroidProducts.mk      # lunch menu entries
├── device.mk
├── sepolicy/               # board-specific SELinux policy
├── init.<board>.rc         # init scripts
└── overlay/                # framework resource overrides
```

`BoardConfig.mk` controls partition sizes, AVB (verified boot), and the kernel. Changing
a partition size breaks OTA from older builds — treat it as a migration.

## Soong (Android.bp)

```
cc_binary {
    name: "myservice",
    srcs: ["main.cpp"],
    shared_libs: ["libbase", "liblog", "libbinder_ndk"],
    init_rc: ["myservice.rc"],
    vintf_fragments: ["myservice.xml"],
    vendor: true,                   // vendor partition, Treble-correct
}

cc_library_shared {
    name: "android.hardware.mysensor@1.0-impl",
    proprietary: true,
    relative_install_path: "hw",
}
```

Blueprint is declarative — no conditionals. Variability goes through `soong_config_*`
modules or product variables, not `ifeq`. Legacy `Android.mk` still works but new code
uses `Android.bp`.

## HALs and Treble

- New HALs are **AIDL**; HIDL is deprecated and frozen. Do not add HIDL interfaces.
- Vendor code lives on the vendor partition and may only use the VNDK/LLNDK. Linking
  a vendor module against a framework-only library fails the VNDK check — that check
  is protecting the Treble contract, do not bypass it.
- Every HAL service declares itself in a `vintf_fragment`; the device manifest and the
  framework compatibility matrix must agree or the build fails VTS.

## SELinux

```
# device/<vendor>/<board>/sepolicy/myservice.te
type myservice, domain;
type myservice_exec, exec_type, vendor_file_type, file_type;
init_daemon_domain(myservice)

allow myservice my_device:chr_file rw_file_perms;
```
```
# file_contexts
/vendor/bin/myservice    u:object_r:myservice_exec:s0
/dev/mysensor            u:object_r:my_device:s0
```

- Never set `permissive` on a domain to ship. Denials are collected with
  `dmesg | grep avc` or `logcat -b events`, then turned into explicit rules with
  `audit2allow` — **reviewed**, never pasted wholesale.
- `neverallow` violations are build failures for a reason. Work with them, not around them.

## Kernel

Modern AOSP uses GKI (Generic Kernel Image) + vendor modules. Board-specific drivers
are modules in `vendor_dlkm`, not patches to the core kernel. A patch to the GKI core
breaks the KMI and the CTS/VTS story.

## Debugging

```bash
adb logcat -b all -v threadtime
adb logcat *:E                          # errors only
adb shell dmesg -w
adb shell dumpsys <service>             # per-service state
adb shell service list
adb bugreport                           # full state capture for an issue
adb shell getprop | grep ro.build
adb shell am start -n pkg/.Activity
```
Native crashes produce a tombstone in `/data/tombstones/` — symbolize with
`development/scripts/stack` against the matching symbol build.

## Testing

```bash
atest <TestModule>                      # unit/instrumentation tests
run cts -m <CtsModule>                  # compatibility
run vts -m <VtsModule>                  # vendor interface — mandatory for Treble compliance
```
VTS failures on a HAL mean the vendor interface contract is broken; they are not
optional warnings.

## Common failure modes

| Symptom | Cause |
|---------|-------|
| Service never starts | SELinux denial (check `avc`), or missing `init_rc`/`vintf_fragment` |
| Build fails VNDK check | vendor module linking a framework-only library |
| Boot loop after a partition change | AVB/verity mismatch, or the partition table changed without reflashing all slots |
| OTA fails on older devices | partition size or AVB key changed between releases |
| HAL not found at runtime | missing `vintf_fragment` or manifest/matrix mismatch |
| Works on userdebug, fails on user | relied on root, a debug property, or permissive SELinux |
