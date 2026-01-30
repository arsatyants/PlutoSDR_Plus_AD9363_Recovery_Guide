# LibreSDR Rev.5 Boot Modes - Complete Guide

## Critical Information for Rev.5

**LibreSDR Rev.5 (Z7020-AD9363) has NO boot mode jumpers (JP1) - this is different from earlier revisions.**

### Hardware Configuration

- **Board**: LibreSDR Rev.5
- **SoC**: Zynq-7020 (xc7z020clg400)
- **RF**: AD9363 (1R1T)
- **BOOT Mode**: Hardwired to QSPI (MODE pins pulled on PCB)
- **No jumpers**: JP1 does not exist on Rev.5

### Boot Mode Selection

Boot source is controlled by **SOFTWARE ONLY**:
1. Zynq Boot ROM always reads from QSPI flash first (hardwired)
2. U-Boot environment determines whether to use SD card or QSPI mtd3
3. No hardware jumpers to change boot source

---

## Understanding Your Current State

### What You Successfully Did

1. ✅ Recovered device from complete brick via JTAG
2. ✅ Fixed device tree (mtd0: 1MB → 4MB for 2.7MB BOOT.bin)
3. ✅ Built complete firmware
4. ✅ Flashed mtd0 with BOOT.bin (2.7MB)
5. ✅ Flashed mtd3 with libre.itb (14.5MB)
6. ✅ Device boots in hybrid mode (QSPI + SD)

### Current Boot Configuration (Hybrid Mode) - **Jan 17, 2026 Status**

**IMPORTANT**: Device is currently using **hybrid boot** configuration:

```
Hardware Boot Path:
  Power ON → Zynq Boot ROM → QSPI mtd0 (BOOT.bin) → U-Boot

U-Boot Decision Tree:
  U-Boot → Check SD card → Found! → Boot from SD card
                        → mtd3 ignored even though it's programmed

Result:
  ✅ BOOT.bin from QSPI mtd0 (BOOT_w25q256.bin - 4.0MB with U-Boot SPL)
  ✅ Linux kernel/rootfs from SD card (/dev/mmcblk0p1)
  ❌ mtd3 not used (contains libre.itb but not accessed)
```

**Current BOOT.bin in mtd0**:
- File: `plutosdr-fw_0.38_libre/build/boot_rebuild/BOOT_w25q256.bin`
- Size: 4.0MB
- Generated: Jan 17, 2026 04:06
- MD5: `ed04f7e7e4a1e622a8d54abb3fd02848`
- Components:
  - **Bootloader**: U-Boot SPL (72KB from `u-boot-xlnx/spl/boot.bin`)
  - **Bitstream**: `system_top.bit` (2.2MB - FPGA configuration)
  - **U-Boot**: `u-boot` (3.0MB - with w25q256 device tree fix)
- Created with: `bootgen -arch zynq -image boot_spl.bif`
- **Limitation**: U-Boot SPL does NOT initialize QSPI, proper FSBL from Vivado required

**SD Card Contents** (what U-Boot actually loads):
- **uImage**: 5.4-5.8MB (Linux kernel from SD)
- **uramdisk.image.gz**: 7.4MB (root filesystem ramdisk from SD)
- **devicetree.dtb**: 22KB (device tree from SD)
- **uEnv.txt**: U-Boot environment configuration

**QSPI mtd3 Status**:
- Contains: libre.itb (15MB FIT image with kernel+dtb+rootfs)
- **NOT USED**: U-Boot loads from SD card instead
- Erases after power cycle (w25q256 4-byte addressing not initialized by SPL)

**To achieve standalone QSPI boot**: Need Vivado to rebuild BOOT.bin with proper FSBL that initializes QSPI correctly.

---

## Understanding w25q256 Flash Chip and 16MB Addressing Boundary

### Why w25q256 is 32MB but has 16MB addressing limitation

The w25q256 is a **32MB chip** (256 Megabits = 32 Megabytes), not 16MB:

**Chip Specifications:**
- **Total capacity**: 32MB (0x00000000 - 0x01FFFFFF)
- **Full address range**: 0 to 33,554,432 bytes

**Addressing Modes:**
- **3-byte addressing mode** (default after power-on): Can only access 0-16MB (2^24 = 16,777,216 bytes)
- **4-byte addressing mode**: Required to access full 0-32MB range (2^25 bytes)
- **Extended Address Register (EAR)**: Alternative method to access upper 16MB

### Why Correct Device Tree Driver Matters

**w25q256 driver (CORRECT)**:
- Understands chip requires 4-byte addressing for >16MB
- Automatically enables 4-byte mode or uses EAR
- Properly initializes flash controller

**n25q512a driver (WRONG - 64MB Micron chip)**:
- Different command set and initialization sequence
- Doesn't enable 4-byte addressing for w25q256
- Leaves chip in default 3-byte mode
- Upper 16MB remains inaccessible

### MTD Partitions vs Addressing Modes

```
Partition Layout on 32MB w25q256:

mtd0: 0x000000-0x400000 (0-4MB)       ← 3-byte addressing works ✅
mtd1: 0x400000-0x420000 (4-4.125MB)   ← 3-byte addressing works ✅  
mtd2: 0x420000-0x500000 (4.125-5MB)   ← 3-byte addressing works ✅
                                        ────── 16MB BOUNDARY ──────
mtd3: 0x500000-0x2000000 (5MB-32MB)   ← Crosses 16MB! Requires 4-byte mode ❌
```

### Test Results Confirm the Issue

**Persistence Tests (Jan 16-17, 2026)**:
- ✅ **mtd0 (0-4MB)**: Data persists after power cycle
- ✅ **mtd1 (4-4.125MB)**: Test data "TEST_DATA_12345" persists after power cycle
- ❌ **mtd3 (5-32MB)**: Data erases to 0xFF after power cycle

**Why mtd3 fails**:
1. Writes to mtd3 appear successful (verify passes immediately)
2. Data actually written to addresses >16MB
3. Chip not in 4-byte addressing mode (FSBL didn't initialize it)
4. Power cycle resets chip to default 3-byte mode
5. Previous writes to >16MB addresses effectively "disappear"
6. Reading back shows all 0xFF (erased state)

**Proof flash hardware works**: mtd0 and mtd1 persist correctly, proving the Winbond w25q256 chip itself is functional.

### Solution

**Proper FSBL from Vivado** must:
1. Initialize QSPI controller
2. Detect w25q256 flash chip
3. Enable 4-byte addressing mode OR configure EAR
4. Pass initialized state to U-Boot
5. U-Boot maintains 4-byte mode for Linux

**Current limitation**: U-Boot SPL (used in BOOT_w25q256.bin) does NOT perform this initialization.

---

### Proof Device Currently Using Hybrid Boot
```bash
$ ssh root@192.168.1.10 'cat /proc/mtd'
mtd0: 00400000  "qspi-fsbl-uboot"    ← Your BOOT.bin here
mtd1: 00020000  "qspi-uboot-env"     ← U-Boot configuration  
mtd2: 000e0000  "qspi-nvmfs"
mtd3: 01b00000  "qspi-linux"         ← Your libre.itb here (not booting from it)

$ ssh root@192.168.1.10 'cat /proc/cmdline'
console=ttyPS0,115200n8 root=/dev/ram rw earlyprintk
                        ↑ Ramdisk from SD card, not from mtd3
```

---

## Boot Modes Explained

### Mode 1: Hybrid Boot (YOUR CURRENT MODE)

**Configuration**:
- QSPI mtd0: BOOT.bin (FSBL + bitstream + U-Boot)
- QSPI mtd3: libre.itb (programmed but not used)
- SD card: Present with Linux files
- U-Boot env: Prefers SD card

**Boot Flow**:
```
Power ON
  ↓
Zynq Boot ROM
  ↓
Load BOOT.bin from QSPI mtd0
  ↓
FSBL runs (init DDR, clocks)
  ↓
FSBL loads FPGA bitstream
  ↓
FSBL starts U-Boot
  ↓
U-Boot checks SD card → FOUND
  ↓
U-Boot loads kernel from SD card
  ↓
Linux boots with SD ramdisk
```

**Advantages**:
- ✅ Works reliably right now
- ✅ Easy to update Linux (just copy files to SD)
- ✅ FPGA bitstream safe in QSPI (won't corrupt)

**Disadvantages**:
- ❌ SD card required
- ❌ QSPI mtd3 space wasted

---

### Mode 2: Standalone QSPI Boot (YOUR GOAL)

**Configuration**:
- QSPI mtd0: BOOT.bin ✅ (you have this)
- QSPI mtd3: libre.itb ✅ (you have this)
- SD card: Removed or not bootable
- U-Boot env: Falls back to mtd3 when SD absent

**Boot Flow**:
```
Power ON
  ↓
Zynq Boot ROM
  ↓
Load BOOT.bin from QSPI mtd0
  ↓
FSBL runs
  ↓
FSBL loads bitstream
  ↓
FSBL starts U-Boot
  ↓
U-Boot checks SD card → NOT FOUND
  ↓
U-Boot falls back to mtd3
  ↓
U-Boot loads FIT image from mtd3
  ↓
Linux boots with QSPI ramdisk
```

**Advantages**:
- ✅ No SD card needed
- ✅ Faster boot (no SD enumeration)
- ✅ More reliable (no SD corruption)
- ✅ Portable (just power + Ethernet)

**Disadvantages**:
- ❌ Harder to update (need network or JTAG)
- ❌ Limited space (27MB for everything)

**WHY IT DIDN'T WORK** when you removed SD card:
- U-Boot `bootcmd` is set to boot from SD with no fallback
- When SD missing, U-Boot hangs or drops to prompt
- No network initialized → device appears dead

---

### Mode 3: JTAG Recovery (Emergency)

**When to Use**:
- QSPI completely erased or corrupted
- Wrong bitstream flashed (device won't boot)
- Bricked device with no other access

**Tools**:
- FT4232H JTAG cable
- openFPGALoader
- Vivado/Vitis (for advanced recovery)

**See**: [RECOVERY.md](RECOVERY.md) for full JTAG procedures

---

## Switching to Standalone QSPI Boot

### Step 1: Check U-Boot Environment

Boot in hybrid mode (with SD card) and inspect U-Boot configuration:

```bash
# Check current boot command
ssh root@192.168.1.10 'fw_printenv | grep -i boot'
```

Example output you might see:
```
bootcmd=run $modeboot
modeboot=sdboot          ← This is the problem!
sdboot=echo SD boot...
```

### Step 2: Fix U-Boot Environment

Add QSPI fallback to boot command:

```bash
ssh root@192.168.1.10

# Add fallback logic
fw_setenv bootcmd 'if mmc rescan; then echo SD boot...; run mmcboot; else echo QSPI boot...; run qspiboot; fi'

# Define qspiboot command
fw_setenv qspiboot 'sf probe 0; sf read 0x2000000 0x500000 0x1400000; bootm 0x2000000'

# Define mmcboot if not present  
fw_setenv mmcboot 'fatload mmc 0 0x2000000 uImage; fatload mmc 0 0x2080000 devicetree.dtb; fatload mmc 0 0x4000000 uramdisk.image.gz; bootm 0x2000000 0x4000000 0x2080000'

# Verify changes
fw_printenv
```

### Step 3: Test Without Removing SD Card

Make SD card non-bootable temporarily:

```bash
ssh root@192.168.1.10
mount /dev/mmcblk0p1 /mnt
mv /mnt/BOOT.bin /mnt/BOOT.bin.bak
mv /mnt/uImage /mnt/uImage.bak 2>/dev/null || true
umount /mnt
reboot
```

Wait 30 seconds, then check if device responds:
```bash
ping -c 5 192.168.1.10
```

- **If ping works**: ✅ QSPI boot successful!
- **If ping fails**: ❌ U-Boot still can't boot from mtd3

### Step 4A: If Successful - Remove SD Card

```bash
# Restore SD card files first (for safety)
ssh root@192.168.1.10
mount /dev/mmcblk0p1 /mnt
mv /mnt/BOOT.bin.bak /mnt/BOOT.bin
mv /mnt/uImage.bak /mnt/uImage 2>/dev/null || true
sync
umount /mnt
poweroff
```

Wait 10 seconds, physically remove SD card, power on. Device should boot from QSPI.

### Step 4B: If Failed - Debug via Serial Console

Connect serial console to see what U-Boot is doing:

```bash
sudo minicom -D /dev/ttyUSB2 -b 115200
```

Power cycle device and watch boot messages. Look for:
- "SF: Detected..." (QSPI flash detection)
- "Loading from..." (boot source)
- Any error messages

Common errors:
- `sf probe failed` - QSPI not accessible
- `invalid image` - mtd3 FIT image format wrong
- `bootm failed` - Device tree mismatch

---

## QSPI Flash Layout (Rev.5)

```
Address Range          Size    MTD  Purpose                 Your Status
────────────────────────────────────────────────────────────────────────
0x00000000-0x003FFFFF  4MB     mtd0 BOOT.bin               ✅ 2.7MB flashed
0x00400000-0x0041FFFF  128KB   mtd1 U-Boot environment     ⚠️  Needs fixing
0x00420000-0x004FFFFF  896KB   mtd2 NVMFS (settings)       ⬜ Empty
0x00500000-0x01FFFFFF  27MB    mtd3 FIT image (libre.itb)  ✅ 14.5MB flashed
```

---

## Verifying QSPI Contents

### Check mtd0 (BOOT.bin)

```bash
ssh root@192.168.1.10 'dd if=/dev/mtd0 bs=512 count=10 2>/dev/null | strings | grep -E "U-Boot|FSBL|Xilinx"'
```

Should show U-Boot version strings.

### Check mtd3 (FIT image)

```bash
ssh root@192.168.1.10 'dd if=/dev/mtd3 bs=512 count=1 2>/dev/null | file -'
```

Should show: `u-boot legacy uImage, zynq_image.ub, Linux/ARM`

### Compare QSPI vs SD Card

```bash
# MD5 of QSPI mtd0
ssh root@192.168.1.10 'md5sum /dev/mtd0'

# MD5 of SD card BOOT.bin
ssh root@192.168.1.10 'mount /dev/mmcblk0p1 /mnt && md5sum /mnt/BOOT.bin && umount /mnt'
```

If different: SD card BOOT.bin is outdated or different version.

---

## Troubleshooting

### Device Doesn't Respond After Removing SD Card

**Symptom**: No ping, no network, appears dead

**Cause**: U-Boot can't boot from mtd3

**Recovery**:
1. Insert SD card back
2. Power cycle  
3. Device should boot in hybrid mode again
4. Re-examine U-Boot environment
5. Check serial console output

### U-Boot Environment Commands Not Working

**Error**: `fw_printenv: command not found`

**Solution**: Install U-Boot tools on the device:
```bash
ssh root@192.168.1.10 'which fw_printenv || echo "Tool missing - need to add to buildroot"'
```

If missing, you'll need to rebuild firmware with `BR2_PACKAGE_UBOOT_TOOLS=y` in buildroot config.

**Workaround**: Access U-Boot environment via serial console:
```bash
# In U-Boot prompt (via serial):
printenv
setenv bootcmd 'if mmc rescan; then run mmcboot; else run qspiboot; fi'
saveenv
```

### mtd3 FIT Image Not Booting

**Symptoms**: U-Boot finds mtd3 but bootm fails

**Possible causes**:
1. FIT image format incorrect
2. Device tree incompatible  
3. Kernel too large for load address
4. Memory overlap

**Debug**:
```bash
# Check FIT image structure
ssh root@192.168.1.10 'dumpimage -l /dev/mtd3'
```

Should show kernel, device tree, and ramdisk components.

---

## Summary

| Aspect | Rev.5 Behavior |
|--------|----------------|
| **Hardware boot mode** | Always QSPI (hardwired MODE pins) |
| **JP1 jumper** | Does not exist on Rev.5 |
| **Boot source decision** | Controlled by U-Boot software only |
| **Your current mode** | Hybrid (QSPI FSBL + SD Linux) |
| **Your goal** | Standalone QSPI (mtd0 + mtd3) |
| **Blocker** | U-Boot environment prefers SD with no fallback |
| **Solution** | Modify `bootcmd` in mtd1 to add QSPI fallback |

**Next Step**: Try the U-Boot environment fix in "Step 2" above.

If that doesn't work, we'll need to debug via serial console to see exactly what U-Boot is doing.
