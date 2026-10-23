---
name: linux-edge-ai
description: On-device inference on embedded Linux — ONNX Runtime, TFLite delegates, NPU/GPU/VPU acceleration (i.MX8MP NPU, Ethos-U, Mali, Hailo), model conversion, benchmarking and deployment in containers.
track: linux-embedded
---

# Edge AI on Embedded Linux

## Feasibility first

```
Accelerator:      CPU (NEON) / GPU (Mali/Vivante via OpenCL/OpenVX) / NPU (i.MX8MP 2.3 TOPS,
                  Ethos-U, Hailo-8, Coral EdgeTPU) / VPU (video decode feeding inference)
Supported format: NPU-specific compiled model vs generic ONNX/TFLite
Quantization:     what the accelerator actually executes (usually int8 per-tensor)
Memory:           model + intermediate tensors + framebuffers, from a shared DDR budget
Latency budget:   ms per frame, and the frame rate the pipeline must sustain
Thermals:         sustained vs burst throughput — measure after 30 min, not 30 s
```

Peak TOPS numbers are marketing. The question is measured end-to-end latency on your
model, including preprocessing and memory copies.

## Runtime choice

| Runtime | Use when |
|---------|----------|
| ONNX Runtime | General purpose, many EPs (ACL, ArmNN, VSI NPU, TensorRT, OpenVINO) |
| TFLite + delegate | Mobile-style models; NNAPI/XNNPACK/VX/GPU delegates |
| NXP eIQ | i.MX family — wraps TFLite/ONNX/DeepViewRT with the Vivante NPU delegate |
| ArmNN / ACL | Arm CPU+GPU optimization on Cortex-A/Mali |
| Vendor SDK (Hailo, Coral, Rockchip RKNN) | Discrete accelerators — model must be compiled by their toolchain |
| PyTorch/ExecuTorch | When the deployment story is PyTorch-native |

On i.MX8M Plus specifically: the NPU executes **int8 quantized** models through the
VSI/VX delegate. A float model will run, on the CPU, and look like the NPU is broken.
Per-tensor quantization is the reliable path; per-channel support varies by driver
version.

## Conversion and quantization

```python
# TFLite full-integer quantization for an NPU
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = rep_gen          # real preprocessed samples
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.uint8           # match what the NPU wants
converter.inference_output_type = tf.uint8
```

```bash
# ONNX static quantization
python -m onnxruntime.quantization.preprocess --input m.onnx --output m-prep.onnx
# then quantize_static with a calibration data reader
```

Always report float vs quantized accuracy on the same held-out set. Always confirm
which operators actually landed on the accelerator:

```bash
# TFLite: enable delegate verbose logging; count ops delegated vs fallback
# ONNX Runtime: sess.get_providers() and the partitioning log
```
A model with 40 subgraph switches between NPU and CPU is slower than pure CPU.

## Pipeline, not just inference

Inference is usually not the bottleneck — copies are.

```
camera (V4L2) -> [DMABUF] -> ISP/resize (GPU or VPU) -> [DMABUF] -> inference -> post
```
- Use zero-copy DMABUF sharing between V4L2, GPU and the NPU where the platform supports
  it. A `memcpy` of every 1080p frame costs more than the model.
- GStreamer with hardware elements (`v4l2h264dec`, `imxvideoconvert_g2d`, `nnstreamer`)
  is the pragmatic path on i.MX.
- Preprocessing must match training **exactly**: resize algorithm, color space, channel
  order, normalization. A BGR/RGB swap is the most common accuracy bug.

## Deployment

- In containers (Torizon and similar): the container's userspace libraries must match
  the kernel's NPU/GPU driver version. Use the vendor base image
  (`torizon/*-imx8`, NXP eIQ images) rather than plain Debian plus pip wheels.
- Pass the accelerator device nodes explicitly (`/dev/galcore`, `/dev/dri/*`,
  vendor-specific nodes).
- Models are versioned artifacts, stored with the image, with their preprocessing spec.
- Field-updatable models are **signed and verified before load**.

## Benchmarking — the only numbers that count

```bash
# TFLite
benchmark_model --graph=model.tflite --num_threads=4 --use_nnapi=true --enable_op_profiling=true

# ONNX Runtime
onnxruntime_perf_test -e <ep> -r 100 model.onnx
```
Report: warm-up excluded, p50 and p95 latency, sustained throughput after thermal
soak, CPU utilization, memory RSS, and power if it matters. State the exact hardware,
BSP version and driver version — NPU performance changes significantly between driver
releases.

## Common failure modes

| Symptom | Cause |
|---------|-------|
| NPU "not used", everything on CPU | model is float, or ops unsupported — check the delegate log |
| First inference 10x slower | NPU warm-up / model compilation on first run; pre-warm at startup |
| Accuracy far below the training result | preprocessing mismatch, or wrong quantization params applied |
| Works standalone, slow in the app | frame copies and format conversions, not the model |
| Container cannot see the accelerator | device node not passed, or userspace/kernel driver version mismatch |
| Throughput drops after minutes | thermal throttling — measure sustained, report both |
