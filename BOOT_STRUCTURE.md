# BOOT.bin Internal Structure - Verification Guide

## File Information
- **Path**: `build_sdimg/BOOT.bin`
- **Size**: 2,739,904 bytes (2.7 MB on disk, 689 KB actual content)
- **Format**: Xilinx Zynq Boot Image (bootgen format)
- **Build**: Jan 18, 2026 20:38

---

## Internal Component Layout

```
┌───────────────────────────────────────────────────────────┐
│ Offset: 0x0 (0) - Boot Header & Metadata (1,472 bytes)   │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  Boot ROM reads this header first                        │
│  Contains partition table pointers                       │
│                                                           │
└───────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────┐
│ Offset: 0x5C0 (1,472) - FSBL PARTITION                   │
├───────────────────────────────────────────────────────────┤
│  Size: 0x6002 (24,578 bytes) = 24 KB                     │
│  Load: On-Chip Memory (OCM) at 0x0                       │
│  Exec: 0x0                                                │
│                                                           │
│  Role: First Stage Boot Loader                           │
│  - Initialize DDR3 memory (1GB @ 750 MHz)                │
│  - Configure Zynq PS7 clocks (CPU, DDR, peripherals)     │
│  - Load and program FPGA bitstream                       │
│  - Load U-Boot into DDR                                  │
└───────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────┐
│ Offset: 0x65D0 (25,808) - BITSTREAM PARTITION            │
├───────────────────────────────────────────────────────────┤
│  Size: 0x8C950 (575,824 bytes) = 562 KB                  │
│  File: system_top.bit                                     │
│                                                           │
│  Role: FPGA Configuration                                │
│  - Zynq PL (Programmable Logic) fabric                   │
│  - AD9361 LVDS interface (2T2R mode)                     │
│  - AXI interconnect for IIO control                      │
│  - DMA engines for high-speed sample streaming          │
│                                                           │
│  **CRITICAL**: Without this, AD9361 is inaccessible!     │
└───────────────────────────────────────────────────────────┘
                            ↓
┌───────────────────────────────────────────────────────────┐
│ Offset: 0x92F20 (601,888) - U-BOOT PARTITION             │
├───────────────────────────────────────────────────────────┤
│  Size: 0x19751 (104,273 bytes) = 101 KB                  │
│  Load: DDR at 0x04000000 (64 MB offset)                  │
│  Exec: 0x04000000                                         │
│                                                           │
│  Role: Secondary Bootloader                              │
│  - Read uEnv.txt from SD/QSPI                            │
│  - Load Linux kernel (uImage)                            │
│  - Load device tree (devicetree.dtb)                     │
│  - Load rootfs (uramdisk.image.gz)                       │
│  - Boot Linux kernel                                     │
└───────────────────────────────────────────────────────────┘
                            ↓
        Total Content: 0xAC671 (706,161 bytes)
        File padded to: 2,739,904 bytes (2.7 MB)
```

---

## Verification Commands After QSPI Flash

### ⚠️ IMPORTANT: Run these commands AFTER flashing BOOT.bin to /dev/mtd0

### 1. Verify File Size Match
```bash
# On LibreSDR device via SSH
ssh root@192.168.1.10

# Check that MTD partition is large enough
cat /proc/mtd
# Expected: mtd0: 00400000 (4MB) - OK for 2.7MB file
# Old (broken): mtd0: 00100000 (1MB) - TOO SMALL!

# Calculate actual content size (exclude padding)
ls -l /tmp/BOOT.bin  # Should show 2739904 bytes
```

### 2. Verify FSBL at 0x5C0
```bash
# Read 32 bytes from FSBL start position
dd if=/dev/mtd0 bs=1 skip=1472 count=32 2>/dev/null | xxd -p

# Expected: ARM executable code (non-zero values)
# Example: ffffffff00000000ffffffff00000000...
```

### 3. Verify Bitstream at 0x65D0 ⭐ MOST CRITICAL
```bash
# Read bitstream header
dd if=/dev/mtd0 bs=1 skip=25808 count=64 2>/dev/null | xxd -g 1

# Expected: Xilinx bitstream sync pattern
# Look for characteristic patterns in first 64 bytes
# Example: 081184e5 0c2184e5 1c3294e5 203284e5...
```

### 4. Verify U-Boot at 0x92F20
```bash
# Search for U-Boot version strings
dd if=/dev/mtd0 bs=1 skip=601888 count=102400 2>/dev/null | strings | grep -i "u-boot"

# Expected output examples:
# U-Boot 2022.01 (or similar version)
# U-Boot SPL
# u-boot,dm-pre-reloc
```

### 5. Compare MD5 (Limited Reliability)
```bash
# Calculate MD5 of source file
md5sum /tmp/BOOT.bin

# Calculate MD5 of flashed data
# NOTE: MTD may have ECC bytes, so this might differ!
dd if=/dev/mtd0 bs=1 count=2739904 2>/dev/null | md5sum

# If different: Not necessarily an error (ECC/OOB data)
# Better test: Try to boot!
```

### 6. Ultimate Verification: Boot Test
```bash
# Power cycle device (remove SD card!)
# Check for:
# 1. Ethernet LED under RJ45 port (SUCCESS)
# 2. NOT the 10M/pps LED (FAILURE)
# 3. Network reachable: ping 192.168.1.10
# 4. AD9361 present: ssh root@192.168.1.10 'iio_info | grep ad9361'
```

---

## SAVED POSITIONS FOR POST-FLASH VERIFICATION

**These offsets are REMEMBERED for Phase 3 verification:**

| Component | Offset (Hex) | Offset (Dec) | Size (Bytes) | Size (KB) |
|-----------|--------------|--------------|--------------|-----------|
| Header    | 0x000        | 0            | 1,472        | 1.4       |
| FSBL      | 0x5C0        | 1,472        | 24,578       | 24        |
| Bitstream | 0x65D0       | 25,808       | 575,824      | 562       |
| U-Boot    | 0x92F20      | 601,888      | 104,273      | 101       |
| **TOTAL** | -            | -            | **706,161**  | **689**   |

**File Size on Disk**: 2,739,904 bytes (2.7 MB) - includes padding

---

## Why These Positions Matter

### FSBL Position (0x5C0)
- Zynq Boot ROM jumps here after reading header
- If corrupted → "Unrecoverable bootrom error"
- Must be executable ARM code

### Bitstream Position (0x65D0) ⚠️ CRITICAL
- **THIS IS WHY 510KB boot.bin FAILED!**
- Without bitstream: FPGA stays unconfigured
- Without FPGA: No AD9361, no Ethernet MAC, no peripherals
- Device appears "dead" - only LED blinks

### U-Boot Position (0x92F20)
- Loaded by FSBL after FPGA configuration
- Reads partition table from device tree
- Loads libre.frm from mtd3 (offset depends on DT)

---

## Common Issues & Solutions

### Issue: Device won't boot after QSPI flash
**Check**:
1. Is mtd0 large enough? (Need 4MB, not 1MB)
   ```bash
   cat /proc/mtd | grep mtd0
   ```
2. Was BOOT.bin fully written?
   ```bash
   ls -l /tmp/BOOT.bin  # Should be 2739904
   dd if=/dev/mtd0 bs=1 count=100 2>/dev/null | xxd  # Should not be all 0xFF
   ```

### Issue: Ethernet not working after boot
**Cause**: Bitstream missing or corrupted
**Check**:
```bash
dd if=/dev/mtd0 bs=1 skip=25808 count=64 2>/dev/null | xxd
# Should show bitstream data, not 0xFF
```

### Issue: MD5 mismatch between file and MTD
**Expected**: This is NORMAL with NAND/QSPI flash!
- Flash has ECC (Error Correction Code) bytes
- OOB (Out Of Band) data not included in reads
- **Solution**: Test by booting, not by MD5

---

## Next Phase: QSPI Flash Procedure

After SD card boot confirms 4MB partition layout:

```bash
# Phase 3: Flash QSPI
ssh root@192.168.1.10

# Erase old 1MB partition
flash_erase /dev/mtd0 0 0

# Download BOOT.bin (2.7MB)
cd /tmp
wget http://192.168.1.1:8000/../build_sdimg/BOOT.bin

# Flash to mtd0
dd if=/tmp/BOOT.bin of=/dev/mtd0 bs=64k
sync

# Run verification commands above
# Then flash libre.frm to mtd3
# Then test boot without SD card
```

---

**Document Created**: 2026-01-18
**Firmware Version**: plutosdr-fw v0.38 (libre target)
**Partition Layout**: 4MB boot (mtd0: 0x0-0x400000)
