---
name: mcu-edge-ai
description: On-MCU machine learning — TensorFlow Lite Micro, CMSIS-NN, NXP eIQ, ESP-DL, Ethos-U. Quantization, arena sizing, operator support, and on-target latency measurement.
track: mcu
---

# Edge AI on MCUs (TinyML)

## Feasibility first

Before writing any integration code, answer:

```
Model size (quantized, int8):     ? KB  -> must fit flash alongside firmware
Tensor arena:                     ? KB  -> must fit SRAM, this is usually the blocker
Inference latency budget:         ? ms
Inference rate:                   ? Hz  -> duty cycle and power
Accelerator:                      none / CMSIS-NN / Ethos-U55 / ESP32-S3 vector / eIQ Neutron
Supported quantization:           int8 per-tensor / per-channel / int16 activations
```

If the arena does not fit SRAM, the answer is a smaller model or a different
architecture — not a workaround.

## Runtime choice

| Runtime | Use with | Notes |
|---------|----------|-------|
| TFLite Micro (LiteRT for Microcontrollers) | Any Cortex-M, RISC-V | The default; static interpreter, no OS needed |
| TFLM + CMSIS-NN | Cortex-M4/M7/M33/M55 | 2–5x speedup on conv/fc, enable the kernel port |
| Ethos-U (Vela compiler) | M55/M85 + U55/U65 | Model must be compiled by Vela; unsupported ops fall back to CPU |
| NXP eIQ | i.MX RT, MCX | Wraps TFLM + Glow + Neutron NPU; use the eIQ Toolkit for conversion |
| ESP-DL / TFLM | ESP32-S3 | S3 vector instructions; ESP-DL for face/person detection models |
| microTVM / Glow AOT | Various | Ahead-of-time compiled, no interpreter overhead, larger build complexity |

## Quantization pipeline

```python
converter = tf.lite.TFLiteConverter.from_saved_model(path)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = rep_data_gen      # MANDATORY: 100-500 real samples
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type  = tf.int8            # full integer, no float at the edges
converter.inference_output_type = tf.int8
tflite_model = converter.convert()
```

Rules:
- The representative dataset must come from the **real sensor**, with the **exact
  preprocessing the device will apply**. A mismatch here is the number-one cause of
  "works in Python, garbage on device".
- Always report float vs int8 accuracy on the same held-out set. A drop >2% needs
  investigation (per-channel quantization, QAT, or a different layer).
- Verify the converted model's input/output scale and zero-point, and apply them in
  the C code exactly.

## Integration

```c
#include "tensorflow/lite/micro/micro_interpreter.h"

/* Arena: static, never malloc. Size by measurement, not by guess. */
alignas(16) static uint8_t tensor_arena[TENSOR_ARENA_SIZE];

static tflite::MicroMutableOpResolver<6> resolver;   /* only the ops the model uses */
resolver.AddConv2D();
resolver.AddDepthwiseConv2D();
resolver.AddFullyConnected();
resolver.AddSoftmax();
resolver.AddReshape();
resolver.AddQuantize();

static tflite::MicroInterpreter interpreter(model, resolver, tensor_arena, sizeof(tensor_arena));
if (interpreter.AllocateTensors() != kTfLiteOk) { /* arena too small — handle */ }

MicroPrintf("arena used: %u", interpreter.arena_used_bytes());   /* size from THIS */
```

- `MicroMutableOpResolver<N>` with the exact op list, never `AllOpsResolver` — it pulls
  every kernel into flash.
- Size the arena from `arena_used_bytes()` on target plus ~10% headroom, then make it
  static and check it at build time.
- Input tensor is filled with quantized values: `q = round(x / scale) + zero_point`,
  clamped to int8 range.

## Placement and scheduling

- Inference must not run in an ISR and must not block a control loop. Run it in a
  dedicated low-priority task, or time-slice it if the RTOS deadline requires.
- On XIP parts (i.MX RT, ESP32), model weights in flash are read through the cache —
  a flash write during inference stalls it. Serialize NVS/OTA writes against inference.
- Weights in external PSRAM: measure, the latency penalty can be 5–10x.

## Measuring on target

```c
uint32_t t0 = DWT->CYCCNT;              /* enable DWT first */
interpreter.Invoke();
uint32_t cycles = DWT->CYCCNT - t0;     /* / SystemCoreClock -> seconds */
```
Report: cycles, ms at the actual clock, arena high-water, flash cost of the model plus
the runtime, and average current per inference if the device is battery-powered.

Never report host-measured or estimated latency as an on-device result.

## Model lifecycle

- The model is a versioned artifact stored with the firmware image, with its
  preprocessing spec (sample rate, window, normalization) recorded alongside.
- If the model is field-updatable, it is **signed and verified** before load — an
  unverified model file is arbitrary data feeding an interpreter.
- Accuracy regression test runs in CI against a fixed test vector set, comparing
  on-device (or simulator) outputs to the golden float outputs within a tolerance.

## Common failure modes

| Symptom | Cause |
|---------|-------|
| `AllocateTensors` fails | arena too small; or an unsupported op needs a fallback buffer |
| Output is constant regardless of input | input quantization params not applied, or wrong tensor index |
| Accuracy far below the Python model | preprocessing mismatch; representative dataset wrong |
| Inference 10x slower than expected | CMSIS-NN kernels not linked; ops falling back to reference kernels |
| Works standalone, crashes in the app | arena aliasing another static buffer, or stack overflow in the inference task |
| Hard fault inside a kernel | unaligned arena — `alignas(16)` required |
