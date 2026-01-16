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

### Current Boot Configuration (Hybrid Mode)

```
Hardware Boot Path:
  Power ON → Zynq Boot ROM → QSPI mtd0 (BOOT.bin) → U-Boot

U-Boot Decision Tree:
  U-Boot → Check SD card → Found! → Boot from SD card
                        → mtd3 ignored even though it's programmed

Result:
  ✅ BOOT.bin from QSPI mtd0
  ✅ Linux kernel/rootfs from SD card
  ❌ mtd3 not used (wasted 14.5MB)
```

**Proof**:
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
