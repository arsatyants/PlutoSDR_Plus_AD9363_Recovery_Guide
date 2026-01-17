# LibreSDR Rev.5 Initial Crash - Root Cause Analysis

## Summary

**LibreSDR Rev.5 bricked during firmware update attempt due to partition size mismatch combined with wrong flash driver configuration.**

## Hardware vs Firmware Mismatch

### Actual Hardware
- **Board**: LibreSDR Rev.5
- **Flash chip**: Winbond w25q256 (32MB, JEDEC ID: 0xef4019)
- **Capacity**: 32 Megabytes (256 Megabits)

### Original Firmware Configuration
- **Device tree compatible**: `"n25q256a", "n25q512a"` (Micron chips)
- **Wrong driver**: Configured for 64MB Micron n25q512a
- **Chip mismatch**: Micron driver running on Winbond hardware
- **Result**: Unstable but barely functional

## The Crash Sequence

### Original Partition Layout
```
mtd0: 0x000000-0x100000 (1MB)    - qspi-fsbl-uboot
mtd1: 0x100000-0x120000 (128KB)  - qspi-uboot-env
mtd2: 0x120000-0x200000 (896KB)  - qspi-nvmfs
mtd3: 0x200000-0x2000000 (30MB)  - qspi-linux
```

### What Happened During Update

**Update attempt**: Tried to flash 2.7MB BOOT.bin to 1MB mtd0 partition

1. **Write started** at address 0x000000 (mtd0 start)
2. **Overflow at** 0x100000 (1MB boundary, mtd0 end)
3. **Write continued** into 0x100000-0x120000 (mtd1 - U-Boot environment)
4. **U-Boot environment corrupted/erased**
5. **Device rebooted**:
   - BOOT.bin: Partially written, corrupted
   - U-Boot env: Destroyed
   - FSBL: Unable to properly initialize
   - **Result**: BRICK - no boot, no network, no serial

### Why Standard Recovery Failed

**Serial console issues**:
- Console on /dev/ttyUSB2 @ 115200N8
- Hardware detected but no output
- FSBL likely crashed before UART initialization
- Boot ROM silent (no debug output)

**Network recovery impossible**:
- Device needs to boot to enable Ethernet
- FSBL/U-Boot corrupted → no boot → no network

**DFU mode inaccessible**:
- Requires U-Boot to be functional
- U-Boot never started due to corrupted BOOT.bin

## Contributing Factor: Wrong Flash Driver

### Why Micron Driver on Winbond Hardware Causes Problems

**Micron n25q512a driver expectations**:
- 64MB capacity (512 Megabits)
- Specific command set for Micron chips
- Different erase block sizes
- Micron-specific timing parameters
- Different 4-byte addressing implementation

**Winbond w25q256 actual behavior**:
- 32MB capacity (256 Megabits)
- Winbond-specific command set
- Different erase characteristics
- Requires Extended Address Register (EAR) or 4-byte mode for >16MB
- Wrong driver doesn't enable proper addressing mode

**Result**:
- Writes appeared successful but were unreliable
- Upper 16MB (>0x1000000) particularly unstable
- Flash operations had wrong timing
- Erase operations may have failed silently
- Made firmware updates dangerous

## Recovery Process (What Was Done)

### 1. JTAG Recovery
- Used OpenOCD + FT2232H adapter
- Loaded minimal FSBL via JTAG
- Manually initialized DDR
- Loaded U-Boot to RAM
- Gained emergency network access

### 2. Partition Table Fix
**Changed**: mtd0 from 1MB → 4MB to accommodate 2.7MB BOOT.bin

**Before**:
```dts
partition@qspi-fsbl-uboot {
    label = "qspi-fsbl-uboot";
    reg = <0x0 0x100000>; /* 1M - TOO SMALL */
};
```

**After**:
```dts
partition@qspi-fsbl-uboot {
    label = "qspi-fsbl-uboot";
    reg = <0x0 0x400000>; /* 4M - fits 2.7MB BOOT.bin */
};
```

### 3. Flash Driver Fix (Required but not yet applied to this file)

**Current state** (zynq-libre.dtsi line 96):
```dts
compatible = "n25q256a", "n25q512a", "jedec,spi-nor"; /* WRONG */
```

**Should be**:
```dts
compatible = "winbond,w25q256", "jedec,spi-nor"; /* CORRECT */
```

**Additional required properties**:
```dts
broken-flash-reset;
m25p,fast-read;
spi-nor,ddr-quad-read-dummy = <6>;
no-wp;
```

## The 16MB Addressing Problem

### Why mtd3 Data Doesn't Persist

**w25q256 Specifications**:
- Total capacity: 32MB (0x00000000 - 0x01FFFFFF)
- 3-byte addressing: Can only access 0-16MB (default after power-on)
- 4-byte addressing: Required for full 0-32MB access
- Extended Address Register (EAR): Alternative method

**Current Partition Layout**:
```
mtd0: 0x000000-0x400000 (0-4MB)       ← Below 16MB ✅
mtd1: 0x400000-0x420000 (4-4.125MB)   ← Below 16MB ✅  
mtd2: 0x420000-0x500000 (4.125-5MB)   ← Below 16MB ✅
────────────────── 16MB BOUNDARY (0x1000000) ──────────────────
mtd3: 0x500000-0x2000000 (5MB-32MB)   ← Crosses 16MB! ❌
```

**Test Results (Jan 16-17, 2026)**:
- ✅ mtd0 (0-4MB): Data persists after power cycle
- ✅ mtd1 (4-4.125MB): Test data persists after power cycle
- ❌ mtd3 (5-32MB): Data erases to 0xFF after power cycle

**Why this happens**:
1. FSBL (or U-Boot SPL) doesn't initialize 4-byte addressing
2. Writes to mtd3 appear successful (immediate verify passes)
3. Data written to addresses >16MB
4. Power cycle resets chip to default 3-byte mode
5. Previous writes to >16MB become inaccessible
6. Reading shows all 0xFF (erased state)

## Why Original Firmware Worked At All

Despite wrong driver configuration, device worked because:

1. **BOOT.bin < 1MB**: Old firmware had smaller BOOT.bin that fit in 1MB partition
2. **Below 16MB**: Most critical data (BOOT.bin, U-Boot env) in 0-5MB range
3. **3-byte addressing sufficient**: Lower addresses accessible with default mode
4. **Luck**: Winbond and Micron chips similar enough for basic operations
5. **No updates**: Once flashed, no one tried to update firmware

**It was stable but fundamentally broken.**

## Complete Fix Requirements

### 1. Linux Kernel Device Tree ✅ Applied
File: `linux/arch/arm/boot/dts/zynq-libre.dtsi`

**Status**: Partition sizes fixed, **compatible string still wrong in current file**

Should be:
```dts
&qspi {
    status = "okay";
    is-dual = <0>;
    num-cs = <1>;
    primary_flash: ps7-qspi@0 {
        #address-cells = <1>;
        #size-cells = <1>;
        spi-tx-bus-width = <1>;
        spi-rx-bus-width = <4>;
        compatible = "winbond,w25q256", "jedec,spi-nor";  /* MUST FIX */
        reg = <0x0>;
        spi-max-frequency = <50000000>;
        broken-flash-reset;
        m25p,fast-read;
        spi-nor,ddr-quad-read-dummy = <6>;
        no-wp;
        /* ... partitions ... */
    };
};
```

### 2. U-Boot Device Tree ✅ Applied
File: `u-boot-xlnx/arch/arm/dts/zynq-libre-sdr.dts`

Fixed to:
```dts
flash@0 {
    compatible = "winbond,w25q256", "jedec,spi-nor";
    /* ... */
};
```

### 3. FSBL Rebuild ❌ BLOCKED
**Status**: Need Vivado 2022.2 to generate proper FSBL

**Current workaround**: Using U-Boot SPL in BOOT_w25q256.bin
- ✅ Device boots
- ❌ QSPI not initialized properly
- ❌ mtd3 doesn't persist after power cycle

**Proper FSBL must**:
1. Initialize QSPI controller correctly
2. Detect w25q256 flash chip
3. Enable 4-byte addressing mode
4. Configure for 32MB access
5. Pass initialized state to U-Boot

## Lessons Learned

1. **Always verify hardware specs** before using firmware
2. **Check partition sizes** before flashing large files
3. **Device tree must match hardware** exactly
4. **Flash driver matters** even if chip "mostly works"
5. **JTAG access is critical** for recovery
6. **Test persistence** after any flash changes
7. **Addressing modes** are not automatic

## Current Status (Jan 17, 2026)

**Working**:
- ✅ Device functional via hybrid boot (QSPI BOOT.bin + SD card Linux)
- ✅ Network accessible at 192.168.1.10
- ✅ IIO/SDR functionality working (30.72 MSPS confirmed)
- ✅ U-Boot device tree fixed for w25q256
- ✅ Partition sizes fixed (mtd0: 4MB)

**Not Working**:
- ❌ Standalone QSPI boot (mtd3 doesn't persist)
- ❌ Linux device tree still has wrong compatible string
- ❌ Need proper FSBL from Vivado

**Blocked On**:
- Xilinx account registration to download Vivado 2022.2
- Need proper FSBL to initialize QSPI with 4-byte addressing

## Prevention for Future

### Before Updating Firmware

1. **Verify flash chip**:
   ```bash
   ssh root@192.168.1.10 "cat /sys/bus/spi/devices/spi1.0/jedec_id"
   # Should show: ef4019 (Winbond w25q256)
   ```

2. **Check partition sizes**:
   ```bash
   ssh root@192.168.1.10 "cat /proc/mtd"
   # Verify mtd0 is 0x400000 (4MB) minimum
   ```

3. **Verify BOOT.bin size**:
   ```bash
   ls -lh BOOT.bin
   # Must be < mtd0 partition size
   ```

4. **Test write before power cycle**:
   ```bash
   # Flash, verify, then power cycle and verify again
   ```

5. **Have JTAG recovery ready**:
   - OpenOCD configured
   - FT2232H adapter connected
   - Minimal FSBL.elf available

### Recommended Update Procedure

1. Backup current firmware from all mtd partitions
2. Verify hardware flash chip type
3. Confirm new firmware built for correct chip
4. Check partition sizes match
5. Test on SD card first (hybrid boot)
6. Only then flash to QSPI
7. Test immediately, don't power cycle until verified
8. Test persistence after power cycle

## References

- [RECOVERY.md](docs/PlutoSDR_Plus_AD9363_Recovery_Guide/RECOVERY.md) - Detailed recovery procedures
- [BOOT_MODES_REV5.md](BOOT_MODES_REV5.md) - Boot mode documentation
- Winbond W25Q256JV datasheet - Flash chip specifications
- Xilinx UG585 - Zynq-7000 Technical Reference Manual
