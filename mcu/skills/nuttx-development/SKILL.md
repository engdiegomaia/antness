---
name: nuttx-development
description: Apache NuttX RTOS development — POSIX API, Kconfig/defconfig workflow, board ports, character drivers, and NSH. Use when a nuttx/ + apps/ workspace or NuttX defconfig is present.
track: mcu
---

# Apache NuttX Development

## Orient first

NuttX is a POSIX-compliant RTOS: it looks like small Linux, and that is the point.
Two repositories, always moving together:

```
nuttx/        # the OS
apps/         # applications and libraries
```

```bash
cd nuttx
./tools/configure.sh -l <board>:<config>     # -l linux host, -m macOS, -c cygwin
make menuconfig                              # then: make savedefconfig
make -j$(nproc)
```

**Always run `make savedefconfig`** and commit `defconfig`, not `.config`. `.config` is
generated and huge; `defconfig` is the minimal delta and is what the project reviews.

## Configuration model

```
boards/<arch>/<chip>/<board>/configs/<config>/defconfig
boards/<arch>/<chip>/<board>/src/            # board-specific init, bringup
boards/<arch>/<chip>/<board>/include/board.h # clock config, pin definitions
arch/<arch>/src/<chip>/                      # chip drivers
drivers/                                     # common drivers
```

A board port is: `board.h` (clocks/pins) + `src/*_bringup.c` (device registration) +
`configs/*/defconfig`. Adding a peripheral means registering it in bringup and enabling
its Kconfig symbols.

## POSIX programming model

```c
int fd = open("/dev/sensor0", O_RDONLY);
if (fd < 0) { return -errno; }
ssize_t n = read(fd, &sample, sizeof(sample));
close(fd);

pthread_mutex_lock(&m);
pthread_cond_wait(&c, &m);

struct timespec ts;
clock_gettime(CLOCK_MONOTONIC, &ts);
```

Everything is a file. A driver exposes `open/close/read/write/ioctl/poll`. Prefer the
POSIX API over NuttX-internal functions in application code — it keeps the code
host-testable and portable.

## Character driver skeleton

```c
static const struct file_operations g_sensor_ops = {
  .open  = sensor_open,
  .close = sensor_close,
  .read  = sensor_read,
  .write = NULL,
  .ioctl = sensor_ioctl,
  .poll  = sensor_poll,
};

int sensor_register(FAR const char *devpath, FAR struct sensor_dev_s *priv)
{
  return register_driver(devpath, &g_sensor_ops, 0666, priv);
}
```

- `FAR` is required by some architectures' memory models — keep it where the codebase uses it.
- Return `-errno` values, never custom codes.
- `nxsem_wait_uninterruptible` inside drivers; plain `sem_wait` can return `-EINTR`.
- Implement `poll` if the device can be used with `select`/`poll` — many apps expect it.

## Applications

```
apps/examples/myapp/
├── Kconfig          # CONFIG_EXAMPLES_MYAPP
├── Make.defs
├── Makefile
└── myapp_main.c     # int main(int argc, char *argv[])
```
Registered as an NSH builtin via `PROGNAME`/`MAINSRC` in the Makefile. NSH is the shell:
disable it in production (`CONFIG_NSH_CONSOLE=n` or authenticate) — it is a full
command surface on the serial port.

## Memory and stacks

```
CONFIG_IDLETHREAD_STACKSIZE
CONFIG_DEFAULT_TASK_STACKSIZE
CONFIG_STACK_COLORATION=y      # enables stack usage reporting
```
`nsh> ps` shows per-task stack usage with coloration enabled. `CONFIG_DEBUG_MM` for heap
diagnostics. NuttX has a real heap — but the steady-state no-allocation rule still applies
to deterministic paths.

## Debug configuration

```
CONFIG_DEBUG_FEATURES=y
CONFIG_DEBUG_ERROR=y / WARN / INFO
CONFIG_DEBUG_ASSERTIONS=y
CONFIG_DEBUG_<SUBSYSTEM>=y     # per-subsystem, e.g. DEBUG_SPI, DEBUG_NET
```
Assertions on during development; they trap to a crash dump with a register context.

## Testing

- `sim` target: NuttX built as a Linux/macOS process — run the full OS and application
  logic on the host. Use it for everything that is not register-level.
- `make -j && ./nuttx` with the `sim:nsh` config gives a working shell on the host.
- `apps/testing/` contains ostest and friends — run them after kernel config changes.

## Common failure modes

| Symptom | Cause |
|---------|-------|
| Device node missing at runtime | not registered in `<board>_bringup.c`, or its Kconfig off |
| Hang at boot before NSH | clock config in `board.h`, or console UART misconfigured |
| `-EINTR` returned unexpectedly | used `sem_wait` instead of `nxsem_wait_uninterruptible` in a driver |
| Config change lost | edited `.config` instead of running `make savedefconfig` |
| Link error after enabling a feature | dependent Kconfig symbol not enabled; check `menuconfig` dependencies |

## Never

- Commit `.config`. Commit `defconfig` from `make savedefconfig`.
- Update `nuttx` without updating `apps` to the matching revision.
- Leave NSH enabled on a production serial port.
