This repository was created from the
[antness](https://github.com/micron-iot/antness) template.

## 1. Scaffold

Clone and run the setup script. It writes the project `AGENTS.md`, trims the track you
are not using, installs the git hook, and generates the agent-harness configs.

```bash
git clone <this repo> && cd <this repo>
./scripts/init-project.sh
```

Non-interactive:

```bash
./scripts/init-project.sh --non-interactive \
  --name my-project --stack yocto --board "Verdin iMX8MP"
```

Stacks: `zephyr` `esp-idf` `freertos` `stm32` `nuttx` `yocto` `torizon` `buildroot` `kernel` `android`

## 2. Fill in the hardware context

Open `AGENTS.md` and complete the **Project context** section: part number, silicon
revision, memory map, console, recovery path, and the real build command.

This is the step that matters. Agents fail in embedded work mostly because they are
missing hardware context, not because they reason badly.

## 3. Track upstream

```bash
git remote add upstream https://github.com/micron-iot/antness.git
./scripts/update-from-upstream.sh     # later, to pull environment improvements
```

## 4. Close this issue

Then delete `.github/workflows/template-bootstrap.yml` and `.github/TEMPLATE_SETUP.md`
if they are still present.
