# Python packaging and deployment for embedded targets

## Select an environment model

- Use a target-native package from the system distribution when it is maintained, compatible with the product release, and integrates with its security/update policy.
- Use a virtual environment when the application needs an isolated Python dependency set and the product image can provide a compatible interpreter. A `venv` isolates Python packages; it does not isolate the kernel, C library, or CPU ABI.
- Use a container only when the target kernel, runtime, storage, and operational model justify it. Containers share the host kernel and do not make incompatible binaries portable.
- Conda can manage complex scientific environments, but weigh its footprint and operational overhead against target constraints.

## Make builds reproducible

1. Pin the Python interpreter and dependency resolution inputs. Keep a human-maintained dependency declaration and a lock or fully resolved set appropriate to the chosen packaging tool.
2. Build in a controlled environment with the target architecture and compatible C library. Dependencies containing native extensions must be compiled for the target ABI or obtained as compatible wheels.
3. Build an installable artifact when useful, and test installation into a clean target-like environment. Avoid depending on an untracked working directory or developer machine state.
4. Record package versions and hashes in release metadata. Preserve the exact source revision and build environment used for each shipped artifact.
5. Install through the product's image or update mechanism. Avoid ad hoc `pip install` on deployed devices because it bypasses image reproducibility, rollback, and package ownership.

## Compatibility and maintenance

Python packaging tooling changes over time. Older projects may rely on `distutils` or `setup.py` invocation patterns; `distutils` was removed from the Python standard library in Python 3.12. Use current Python packaging guidance for build metadata and tools, and verify the selected workflow against the project's Python version. `pip`, `setuptools`, and `venv` serve different roles; do not assume an isolated environment also supplies a compiler or system development headers.

## Failure checks

- “No matching distribution found”: check interpreter tags, CPU architecture, libc, Python ABI, and configured package index.
- Import errors at runtime: compare the installed dependency set with the build lock and inspect `sys.path` and native library resolution.
- Native extension load failure: inspect ELF architecture and linked libraries; cross-compile against the target sysroot.
- Environment fills flash: measure installed footprint and caches; remove build-only tools from the final image.

Sources: *Mastering Embedded Linux Development*, 4th ed., ch 15 (Python packaging, pip, requirements, virtual environments and Conda).
