# LibreSDR Rev.5 Boot Modes & Configuration

## Hardware Overview

**LibreSDR Rev.5 (Z7020-AD9363)** is a Zynq-7020 based SDR with **NO boot mode jumpers**. 

### Critical Difference from Other Revisions

**Rev.5 has HARDWIRED boot configuration:**
- BOOT mode pins are **fixed to QSPI mode** (pulled to appropriate logic levels on PCB)
- **No JP1 jumper** - this was removed in Rev.5 design
- Boot source selection is controlled **entirely by U-Boot software**, not hardware jumpers
- The Zynq **always** attempts to boot from QSPI flash first

## How Rev.5 Boot Works

### Boot Sequence (Hardware Level)

1. **Power ON** → Zynq Boot ROM executes
2. Boot ROM reads **MODE pins** → hardwired to **QSPI mode** on Rev.5
3. Boot ROM loads **BOOT.bin** from QSPI flash offset 0x0 (mtd0)
4. **FSBL** (First Stage Boot Loader) runs from BOOT.bin:
   - Initializes DDR3 memory
   - Configures Zynq PS7 clocks and peripherals
   - Loads FPGA bitstream
   - Loads U-Boot
5. **U-Boot** takes control and decides what to boot next

### Boot Source Decision (Software Level)

U-Boot on Rev.5 checks boot sources in this order:
1. **SD card present?** → Try to boot from SD
2. **SD boot failed/absent?** → Fall back to QSPI mtd3
3. **Both failed?** → Drop to U-Boot prompt (no network on LibreSDR)

## Boot Modes on Rev.5

Since Rev.5 has **no hardware jumpers**, all boot modes are controlled by:
1. **What's in QSPI flash** (mtd0 MUST have valid BOOT.bin)
2. **SD card presence** (U-Boot auto-detects)
3. **U-Boot environment** (stored in mtd1, configures boot order)

### Mode 1: Hybrid Boot (QSPI FSBL + SD Linux) - **YOUR CURRENT CONFIGURATION**

**How it works**:
- QSPI mtd0: Contains BOOT.bin (FSBL + bitstream + U-Boot)
- SD card: Contains kernel, device tree, rootfs
- U-Boot: Detects SD card and boots from it

**Current State**:
```
✅ mtd0: BOOT.bin (2.7MB) - flashed successfully
✅ mtd3: libre.itb (14.5MB) - flashed but NOT USED
✅ SD card: BOOT.bin + devicetree.dtb present
🔄 Boot: QSPI mtd0 → SD card Linux (mtd3 ignored)
```

**Why this happens**:
U-Boot's default `bootcmd` checks SD card first. If found, it boots from SD and never checks mtd3.

**Boot command line shows**:
```bash
root=/dev/ram
# Ramdisk loaded from SD card, NOT from QSPI mtd3
```

### Mode 2: Pure QSPI Boot (Standalone) - **TARGET CONFIGURATION**

**How it works**:
- QSPI mtd0: Contains BOOT.bin
- QSPI mtd3: Contains FIT image (kernel + dtb + rootfs)
- SD card: **Not present or not bootable**
- U-Boot: Fails to find SD, falls back to mtd3

**What you flashed**:
```
✅ mtd0: 0x0-0x400000 (4MB) - BOOT.bin (2.7MB)
✅ mtd3: 0x500000-0x2000000 (27MB) - libre.itb (14.5MB)
```

**Why standalone QSPI boot FAILED when you removed SD card**:

The problem is **U-Boot environment configuration**. Your U-Boot's `bootcmd` is likely set to:
```
bootcmd=run $modeboot
modeboot=sdboot  # Or similar
```

When SD card is removed:
1. U-Boot tries to boot from SD → **fails**
2. U-Boot does NOT automatically fall back to mtd3
3. U-Boot either hangs or drops to prompt (no serial console = looks dead)
4. Device never boots Linux → **no network response**

**Solution** (covered in "Fixing Standalone QSPI Boot" section below)

## Switching Between Modes on Rev.5

**IMPORTANT**: Rev.5 has **NO JUMPERS**. All mode switching is done by:
1. Inserting/removing SD card
2. Modifying U-Boot environment in QSPI mtd1
3. Reprogramming QSPI flash

### Current → Standalone QSPI Boot (Your Goal)

**Prerequisites**:
- ✅ mtd0 has valid BOOT.bin (YOU HAVE THIS)
- ✅ mtd3 has valid FIT image (YOU HAVE THIS)
- ⚠️ U-Boot environment needs fixing (THIS IS THE PROBLEM)

**Steps**:

### QSPI Flash Chip
- **Type**: Spansion S25FL256S or similar
- **Size**: 32MB (0x0 - 0x2000000)
- **Speed**: Quad SPI, ~50MHz
- **Erase**: 64KB sectors (0x10000 bytes)

### Boot Sequence Timing
- **Zynq Boot ROM**: ~50ms to load FSBL from QSPI/SD
- **FSBL**: ~200ms to init DDR and load bitstream
- **U-Boot**: ~1 second to enumerate devices and load kernel
- **Linux**: ~5-10 seconds to userspace
- **Total QSPI boot**: ~7-12 seconds
- **Total SD boot**: ~10-15 seconds (slower SD card access)

---

## Troubleshooting

### Device Not Booting After Mode Change

**Symptoms**: No network, no serial output

**Recovery**:
1. Power off
2. Connect JTAG cable
3. Use openFPGALoader to load bitstream:
   ```bash
   openFPGALoader --cable ft4232 --fpga-part xc7z020clg400 ~/code/libresdr/firmware/build_sdimg/system_top.bit
   ```
4. Device should come online temporarily
5. SSH in and check QSPI contents
6. Reflash if needed

### Hybrid Mode Working But QSPI Standalone Fails

**Diagnosis**: U-Boot configuration issue

**Fix**:
1. Boot in hybrid mode
2. Dump U-Boot environment:
   ```bash
   ssh root@192.168.1.10 'fw_printenv > /tmp/uboot_env.txt'
   scp root@192.168.1.10:/tmp/uboot_env.txt .
   ```
3. Modify `bootcmd` to boot from mtd3
4. Write back:
   ```bash
   ssh root@192.168.1.10 'fw_setenv bootcmd "sf probe; sf read 0x2000000 0x500000 0x1400000; bootm 0x2000000"'
   ```
5. Reboot and test

### Serial Console Access

**Port**: `/dev/ttyUSB2` (on FT4232H JTAG cable)
**Settings**: 115200n8, no flow control

```bash
sudo minicom -D /dev/ttyUSB2 -b 115200
```

Watch U-Boot messages to see exactly what it's trying to boot.

---

## Summary

| Mode | JP1 | SD Card | QSPI mtd0 | QSPI mtd3 | Boot Source |
|------|-----|---------|-----------|-----------|-------------|
| **QSPI Standalone** | OPEN | Not needed | Required | Required | mtd0 → mtd3 |
| **SD Pure** | CLOSED | Required | Not used | Not used | SD → SD |
| **Hybrid (current)** | OPEN | Required | Required | Optional | mtd0 → SD |
| **JTAG Recovery** | Any | Any | Any | Any | JTAG cable |

**Your Goal**: Make QSPI standalone work so SD card is optional.

**Current Blocker**: U-Boot not loading from mtd3 when SD card removed, likely due to U-Boot environment or mtd3 format issue.
