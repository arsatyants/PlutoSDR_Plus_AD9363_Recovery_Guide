# LibreSDR Recovery Guide

## Overview

This guide covers recovery procedures for LibreSDR (ZynqSDR) devices that fail to boot after unsuccessful firmware flashing, corrupted QSPI flash, or other boot failures. The LibreSDR is based on Zynq 7020 SoC and typically ships with empty QSPI flash, designed to boot from SD card.

## Boot Order & Architecture

LibreSDR boot priority:
1. **QSPI Flash** (if valid BOOT.bin exists at offset 0x0)
2. **SD Card** (FAT32 formatted, contains BOOT.bin)
3. **JTAG** (for emergency recovery and development)

**Key Components:**
- Zynq 7020 SoC (750 MHz CPU / 525 MHz DDR @ stock, overclockable to 1100/750 MHz)
- 1GB DDR3 RAM
- QSPI flash for boot storage
- microSD card slot
- JTAG debug interface (FT4232H quad UART/FIFO):
  - `/dev/ttyUSB0`, `/dev/ttyUSB3-5` - JTAG/UART ports (detected by openFPGALoader as `ft4232`)
  - **CRITICAL**: Use `-c ft4232` cable type with openFPGALoader (NOT `ft2232`)
- Serial consoles:
  - `/dev/ttyACM0` - **CDC ACM USB serial console** (appears when Linux boots, 115200N8)
  - This is the primary console for debugging - use `sudo cat /dev/ttyACM0` or `sudo minicom -D /dev/ttyACM0 -b 115200`

## Prerequisites

### Required Tools
```bash
sudo apt install openFPGALoader picocom
```

### Build Artifacts Needed
You need the files from `plutosdr-fw_0.38_libre/build_sdimg/`:
- `BOOT.bin` - Complete boot image (FSBL + bitstream + U-Boot)
- `uImage` - Linux kernel
- `devicetree.dtb` - Device tree blob
- `uramdisk.image.gz` - Root filesystem
- `uEnv.txt` - U-Boot environment

If you don't have these, rebuild firmware first:
```bash
git clone --branch v0.38 --recursive https://github.com/analogdevicesinc/plutosdr-fw.git plutosdr-fw_0.38_libre
./apply.sh
cd plutosdr-fw_0.38_libre
export VIVADO_SETTINGS=/opt/Xilinx/Vivado/2022.2/settings64.sh
export TARGET=libre
make
make sdimg
```

## Recovery Method 1: SD Card Boot + Manual QSPI Flash

This is the **safest** recovery method. LibreSDR ships with empty QSPI and boots from SD card, but **does not automatically flash QSPI** like PlutoSDR does. You must manually flash QSPI after SD card boot.

### Step 1: Prepare SD Card

1. **Format SD card as FAT32:**
```bash
# Find your SD card device (usually /dev/sdX, where X is a letter)
lsblk

# Format as FAT32 (WARNING: This erases all data on the card!)
sudo mkfs.vfat -F 32 /dev/sdX1
```

2. **Mount and copy boot files:**
```bash
# Mount SD card
sudo mount /dev/sdX1 /mnt

# Copy all boot files from build_sdimg
cd ~/code/libresdr/firmware/build_sdimg
sudo cp -v BOOT.bin uImage devicetree.dtb uramdisk.image.gz uEnv.txt /mnt/

# Ensure all data is written
sync

# Unmount
sudo umount /mnt
```

3. **Boot from SD card:**
   - Power off LibreSDR completely (disconnect USB)
   - Insert prepared SD card
   - Reconnect USB power
   - Wait 60-90 seconds for first boot

4. **Verify boot via serial console:**
```bash
# Primary console - use this for real-time debugging
sudo cat /dev/ttyACM0
# Or with minicom for interactive terminal
sudo minicom -D /dev/ttyACM0 -b 115200
```

Expected boot messages:
```
Xilinx First Stage Boot Loader 
Release 2022.2   Nov 17 2023-20:38:10
...
U-Boot 2022.01-... (libre)
...
Starting kernel ...
Linux version 6.1.0-... (oe-user@oe-host) (arm-linux-gnueabihf-gcc)
```

**Important:** `/dev/ttyACM0` only appears after Linux kernel starts the USB gadget driver. If you don't see it, the device is stuck in U-Boot or earlier.

5. **Test network connectivity:**
```bash
# Gigabit Ethernet (default configuration)
ping 192.168.1.10

# SSH access (password: analog)
ssh root@192.168.1.10

# Test IIO device
iio_info -u ip:192.168.1.10
```

### Step 2: Manually Flash QSPI from Running System

**Important:** LibreSDR does NOT automatically copy firmware to QSPI like PlutoSDR. You must manually flash it.

#### Option A: Flash via Network (Recommended)

```bash
# On your host PC, copy BOOT.bin to running LibreSDR
cd ~/code/libresdr/firmware/build_sdimg
scp BOOT.bin root@192.168.1.10:/tmp/
# Password: analog

# SSH into LibreSDR
ssh root@192.168.1.10

# Flash BOOT.bin to QSPI
cd /tmp
flashcp -v BOOT.bin /dev/mtd0

# Verify flash
md5sum BOOT.bin
nanddump -f /tmp/mtd0_dump /dev/mtd0 -l $(stat -c%s BOOT.bin)
md5sum /tmp/mtd0_dump
# MD5 sums should match

# Reboot without SD card
reboot
```

#### Option B: Flash via Serial Console + SD Card

If network isn't working, use serial console:

```bash
# Connect serial console
sudo picocom -b 115200 /dev/ttyUSB2

# Login (root/analog)
# Copy BOOT.bin from SD card to RAM
mount /dev/mmcblk0p1 /mnt
cp /mnt/BOOT.bin /tmp/

# Flash to QSPI
flashcp -v /tmp/BOOT.bin /dev/mtd0

# Verify
md5sum /tmp/BOOT.bin /dev/mtd0
# Should show same hash

# Reboot
reboot
```

#### Option C: Flash via U-Boot Console (No Linux Required)

If Linux won't boot but U-Boot works:

```bash
# Connect serial console
sudo picocom -b 115200 /dev/ttyUSB2

# Interrupt U-Boot (press any key during countdown)
# In U-Boot prompt:

# Load BOOT.bin from SD card to RAM
fatload mmc 0 0x10000000 BOOT.bin

# Probe SPI flash
sf probe

# Erase QSPI (first 3MB is enough for BOOT.bin)
sf erase 0 0x300000

# Write from RAM to QSPI
sf write 0x10000000 0 ${filesize}

# Reset to boot from QSPI
reset
```

### Step 3: Verify QSPI Boot (SD Card Removed)

```bash
# Power off LibreSDR
# Remove SD card
# Power on

# Wait 60 seconds for boot
# Test network
ping 192.168.1.10

# Verify it's booting from QSPI (not SD)
ssh root@192.168.1.10
dmesg | grep -i "spi"
# Should show QSPI flash device detected

# Check MTD partitions
cat /proc/mtd
# dev:    size   erasesize  name
# mtd0: 00c00000 00001000 "qspi-fsbl-uboot"
# mtd1: 00040000 00001000 "qspi-uboot-env"
# ...
```

## Recovery Method 2: JTAG Recovery with openFPGALoader

Use this method if SD card boot fails or you need to erase corrupted QSPI flash.

### Verify JTAG Connection

```bash
sudo openFPGALoader --detect -d /dev/ttyUSB1
```

Expected output:
```
Jtag frequency : requested 6.00MHz   -> real 6.00MHz  
index 0:
    idcode   0x4ba00477
    type     ARM cortex A9
    irlength 4
index 1:
    idcode 0x3727093
    manufacturer xilinx
    family zynq
    model  xc7z020
    irlength 6
```

If detection fails:
- Check USB cable connections
- Try different USB port
- Verify `/dev/ttyUSB0` and `/dev/ttyUSB1` exist
- Check for hardware damage

### Erase Corrupted QSPI Flash

**Important:** This erases all boot code from flash. Device will only boot from SD card afterward.

```bash
sudo openFPGALoader -d /dev/ttyUSB1 --bulk-erase
```

This takes 30-60 seconds. After erasing, proceed with SD card boot (Method 1) or JTAG flash (below).

### Flash BOOT.bin to QSPI via JTAG

```bash
cd ~/code/libresdr/firmware/build_sdimg

# Flash complete boot image to QSPI
sudo openFPGALoader -d /dev/ttyUSB1 --write-flash BOOT.bin
```

**What's happening:**
- Writes ~2.8MB BOOT.bin to QSPI flash at offset 0x0
- Contains FSBL (First Stage Boot Loader), FPGA bitstream, and U-Boot
- Takes 5-10 minutes - **DO NOT INTERRUPT OR POWER OFF**

Expected output:
```
write 2821660 bytes at 0x00000000
[==================================================] 100.00%
Done
```

**After successful flash:**
1. Power cycle device (disconnect/reconnect USB)
2. Remove SD card (if inserted)
3. Wait 60 seconds for boot
4. Verify via serial console or network (`ping 192.168.1.10`)

### Troubleshooting JTAG Flash

If `openFPGALoader` fails:

**Explicit cable specification:**
```bash
sudo openFPGALoader -c ft2232 -d /dev/ttyUSB1 --write-flash BOOT.bin
```

**Reduce JTAG frequency for stability:**
```bash
sudo openFPGALoader -d /dev/ttyUSB1 --freq 1M --write-flash BOOT.bin
```

**Two-stage flash (erase then write):**
```bash
sudo openFPGALoader -d /dev/ttyUSB1 --bulk-erase
sudo openFPGALoader -d /dev/ttyUSB1 --write-flash BOOT.bin
```

**Verify flash contents:**
```bash
# Dump first 8MB of QSPI to file
sudo openFPGALoader -d /dev/ttyUSB1 --dump-flash 0x0 0x800000 dump.bin

# Check file size matches BOOT.bin
ls -lh dump.bin ~/code/libresdr/firmware/build_sdimg/BOOT.bin
```

## Recovery Method 3: Xilinx XSCT (Advanced)

Use this if openFPGALoader is unavailable or fails repeatedly. Requires Xilinx Vitis 2022.2.

### Launch XSCT Interactive Shell

```bash
source /opt/Xilinx/Vitis/2022.2/settings64.sh
xsct
```

### XSCT Commands for Recovery

```tcl
# Connect to JTAG chain
connect

# Target ARM core 0
targets -set -filter {name =~ "ARM*#0"}

# System reset
rst -system

# Re-target after reset
targets -set -filter {name =~ "ARM*#0"}

# Load FPGA bitstream
fpga ~/code/libresdr/firmware/build_sdimg/system_top.bit

# Load and run FSBL
source ~/code/libresdr/firmware/build_sdimg/fsbl.elf
con
after 5000
stop

# Load and run U-Boot
dow ~/code/libresdr/firmware/build_sdimg/u-boot.elf
con

# Exit XSCT (U-Boot continues running)
exit
```

### Flash QSPI from U-Boot Console

After running XSCT commands above, U-Boot should be running. Connect serial console:

```bash
sudo picocom -b 115200 /dev/ttyUSB2
```

In U-Boot prompt, manually flash QSPI:

```bash
# Load BOOT.bin via TFTP or SD card
# Example with SD card:
fatload mmc 0 0x10000000 BOOT.bin
sf probe
sf erase 0 0x300000
sf write 0x10000000 0 ${filesize}

# Reset to boot from QSPI
reset
```

## Recovery Method 4: Hardware Boot Mode Pins

If JTAG doesn't work and device won't respond, force boot mode via hardware pins.

### Zynq Boot Mode Selection

Locate **MODE[2:0]** pins on the board (refer to `zynqsdr_rev5.pdf` schematic). Boot modes:

| MODE[2:0] | Boot Source    |
|-----------|----------------|
| 000       | JTAG           |
| 001       | Quad SPI       |
| 101       | SD Card        |

**Force JTAG boot mode:**
1. Power off device
2. Short MODE pins to set `000` (usually pull-down resistors near BOOT_MODE header)
3. Power on
4. Attempt JTAG recovery (Method 2)
5. Restore original jumpers after recovery

**Note:** Most LibreSDR boards are pre-configured for Quad SPI (001) or SD Card (101) boot. Changing mode pins requires soldering or jumper modification.

## Post-Recovery Verification

### Serial Console Check

```bash
sudo picocom -b 115200 /dev/ttyUSB2
```

Successful boot shows:
```
Xilinx First Stage Boot Loader (FSBL)
Release 2022.2   Nov 17 2023-20:38:10

U-Boot 2022.01 (libre)
zynq-uboot> 

Starting kernel ...
[    0.000000] Booting Linux on physical CPU 0x0
[    0.000000] Linux version 6.1.0-...
...
Welcome to Buildroot
libre login: root
Password: analog
```

### Network Connectivity Test

```bash
# Ping default IP
ping 192.168.1.10

# SSH login (password: analog)
ssh root@192.168.1.10

# Check CPU/DDR clock speeds
ssh root@192.168.1.10 "cat /proc/cpuinfo | grep BogoMIPS"
# Stock: ~1500 (750 MHz CPU)
# Overclocked 1100 MHz: ~2200
```

### IIO Device Verification

```bash
# List IIO devices
iio_info -u ip:192.168.1.10

# Should show:
# - ad9361-phy (transceiver)
# - cf-ad9361-lpc (DMA engine)

# Test sample rate configuration
iio_attr -u ip:192.168.1.10 -c ad9361-phy voltage0 sampling_frequency
# Stock: up to 20000000 (20 MSPS)
# Overclocked: up to 27500000 (27.5 MSPS)
```

### Test with SDR Software

**iio-oscilloscope (GUI):**
```bash
sudo apt install libiio-utils iio-oscilloscope
osc ip:192.168.1.10
```

**SDR++ (recommended for high sample rates):**

For rates >20 MSPS, modify SDR++ source before building:

1. Increase buffer size:
```cpp
// source_modules/plutosdr_source/src/main.cpp:236
#define PLUTOSDR_BUFFER_SIZE 1000000  // Change from default 256000
```

2. Remove 20 MSPS limit:
```cpp
// source_modules/plutosdr_source/src/main.cpp:46
#define MAX_SAMPLE_RATE 61440000  // Change from 20000000
```

3. Rebuild SDR++:
```bash
cd sdrplusplus
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
```

## Overclocking After Recovery

If you recovered with stock firmware (750 MHz CPU / 525 MHz DDR) but want **27.5 MSPS performance**, rebuild with overclock:

### Overclock Build Process

```bash
cd ~/code/libresdr/plutosdr-fw_0.38_libre
export VIVADO_SETTINGS=/opt/Xilinx/Vivado/2022.2/settings64.sh
export TARGET=libre

# Overclock to 1100 MHz CPU, 750 MHz DDR
OVERCLOCK_CPU_MULT=44 OVERCLOCK_DDR_MULT=30 make overclock

# Clean old SD image
rm -rf build_sdimg

# Rebuild SD card image with overclocked BOOT.bin
make sdimg
```

### Adjust DDR Timing for 750 MHz

Edit `hdl/projects/libre/system_bd.tcl` before running `make sdimg`:

```tcl
# Change DDR timing parameters for 750 MHz (from default 525 MHz):
PCW_UIPARAM_DDR_CL {9}           # Was 7
PCW_UIPARAM_DDR_CWL {7}          # Was 5
PCW_UIPARAM_DDR_T_RCD {9}        # Was 7
PCW_UIPARAM_DDR_T_RP {9}         # Was 7
```

**Then rebuild:**
```bash
cd hdl
make clean
cd ../plutosdr-fw_0.38_libre
make
make sdimg
```

Flash overclocked firmware using any recovery method above (SD card + manual QSPI flash or JTAG).

### Verify Overclock Success

```bash
ssh root@192.168.1.10

# Check CPU frequency
cat /proc/cpuinfo | grep BogoMIPS
# Should show ~2200 (1100 MHz)

# Check DDR frequency (read from SLCR registers)
devmem 0xF8000120 32
# Should show 0x1C00001E for 750 MHz DDR (MULT=30)

# Test sustained sample rate with iio_readdev
iio_readdev -u ip:192.168.1.10 -b 1000000 -s 275000000 cf-ad9361-lpc > /dev/null
# Should sustain 27.5 MSPS without buffer overflows
```

## Common Failure Scenarios & Solutions

### Symptom: Device Boots from SD but Not from QSPI After Removal

**You described this exact scenario:** Works with SD card, but after removing SD card and rebooting, `iio_info` can't find device.

**Root cause:** LibreSDR does NOT automatically flash QSPI like PlutoSDR. You must manually flash after SD boot.

**Solution:**
1. Boot from SD card (Method 1, Step 1)
2. Manually flash QSPI using `flashcp` (Method 1, Step 2, Option A or B)
3. Verify QSPI boot without SD card (Method 1, Step 3)

**Quick fix if you have network access:**
```bash
# Boot with SD card inserted
ping 192.168.1.10  # Verify it's up

# Flash QSPI
cd ~/code/libresdr/firmware/build_sdimg
scp BOOT.bin root@192.168.1.10:/tmp/
ssh root@192.168.1.10 "flashcp -v /tmp/BOOT.bin /dev/mtd0"

# Power cycle without SD card
# Should now boot from QSPI
```

### Symptom: No Boot Activity (No LEDs, No Serial Output)

**Possible causes:**
- Power supply insufficient (needs 5V 2A+ via USB)
- Hardware damage
- Corrupted QSPI and no SD card

**Solution:**
1. Try different USB power source (2A+ charger or powered hub)
2. Verify JTAG detection: `sudo openFPGALoader --detect -d /dev/ttyUSB1`
3. If JTAG works: Erase QSPI + SD card boot (Method 2 + Method 1)
4. If JTAG fails: Check hardware (power rails, JTAG connections)

### Symptom: Boots to U-Boot but Kernel Hangs

**Serial console shows:**
```
U-Boot 2022.01 (libre)
...
Loading kernel from FIT Image at 10000000 ...
```
Then stops.

**Possible causes:**
- Corrupted kernel image (`uImage`)
- Wrong device tree (`devicetree.dtb`)
- DDR timing issues (overclocked without adjusted timing)

**Solution:**
1. Rebuild firmware from clean state:
```bash
cd ~/code/libresdr/plutosdr-fw_0.38_libre
make clean
export TARGET=libre
make
make sdimg
```
2. Flash new `build_sdimg/` files to SD card
3. If still fails, check DDR timing in `hdl/projects/libre/system_bd.tcl`

### Symptom: Network Not Reachable (192.168.1.10 Timeout)

**Possible causes:**
- Ethernet cable not connected to gigabit switch/router
- IP conflict on 192.168.1.x subnet
- Ethernet PHY not initializing

**Solution:**
1. Connect via serial console: `sudo picocom -b 115200 /dev/ttyUSB2`
2. Check Ethernet status:
```bash
ifconfig eth0
# Should show UP and 192.168.1.10
ip link show eth0
# Should show "state UP"
```
3. Try USB gadget network instead (automatically creates 192.168.2.1)
4. Change IP via serial console:
```bash
ifconfig eth0 192.168.1.20 netmask 255.255.255.0
```

### Symptom: IIO Device Shows but Sample Rate Limited

**`iio_info` works but max sample rate stuck at ~11 MSPS.**

**Possible causes:**
- Old firmware (not this LibreSDR optimized version)
- CPU/DDR not overclocked
- Network bandwidth limitation

**Solution:**
1. Verify you're running LibreSDR firmware:
```bash
ssh root@192.168.1.10
cat /etc/os-release
# Should show "libre" in the name
```
2. Check CPU clock:
```bash
cat /proc/cpuinfo | grep BogoMIPS
# <1600 = stock (20 MSPS max)
# >2000 = overclocked (27.5 MSPS capable)
```
3. Test with large buffer size in SDR software (1M+ samples)
4. Use dedicated gigabit Ethernet connection (not shared with other traffic)

### Symptom: Random Crashes or Corruption at High Sample Rates

**Device works at 20 MSPS but crashes/corrupts at 27.5 MSPS.**

**Possible causes:**
- Insufficient DDR timing margin (overclock too aggressive)
- Thermal throttling (SoC overheating)
- Power supply instability

**Solution:**
1. Reduce overclock:
```bash
# Try 1050 MHz CPU / 700 MHz DDR (more conservative)
OVERCLOCK_CPU_MULT=42 OVERCLOCK_DDR_MULT=28 make overclock
```
2. Add heatsink to Zynq chip
3. Increase DDR timing slack in `system_bd.tcl`:
```tcl
PCW_UIPARAM_DDR_CL {10}   # Was 9, more slack
PCW_UIPARAM_DDR_CWL {8}   # Was 7
```
4. Use 2A+ power supply with short USB cable

## Emergency Patch Regeneration

If you modified the firmware but lost track of changes, regenerate patches from your working `plutosdr-fw_0.38_libre/` directory:

```bash
cd ~/code/libresdr
./collect.sh
```

This creates updated patches in `patches/` directory. Verify with `git diff` before committing.

## Advanced Case Study: QSPI U-Boot Environment Override Issue

### Symptom: Device Boots to U-Boot Mass Storage But Won't Load Linux from SD Card

**Complex scenario observed:**
- SD card has verified correct boot files (BOOT.bin, uImage, devicetree.dtb, uramdisk.image.gz, uEnv.txt)
- Device boots and loads FSBL + U-Boot from SD card successfully
- USB network responds to ping (192.168.2.1)
- IIO device detected via USB
- **BUT:** No `/dev/ttyUSB*` serial ports (FTDI not initialized)
- **BUT:** SSH times out (Linux kernel never loads)
- Device shows only mass storage interface (30MB PlutoSDR virtual drive)

### Root Cause: QSPI U-Boot Environment Variables Override SD Boot

**What's happening:**

1. **Boot sequence:**
   - Zynq BROM checks QSPI → finds corrupted/partial firmware
   - Falls back to SD card
   - Loads FSBL from SD card ✓
   - Loads FPGA bitstream from SD card ✓
   - Loads U-Boot from SD card ✓

2. **U-Boot initialization:**
   - U-Boot reads environment from **QSPI flash** first (not SD card!)
   - QSPI environment has: `modeboot=qspiboot`
   - U-Boot executes: `bootcmd=run $modeboot` → runs `qspiboot`
   - `qspiboot` tries to load kernel from QSPI (corrupted)
   - Fails → drops to mass storage/DFU mode

3. **Why uEnv.txt from SD card doesn't help:**
   - U-Boot only reads `uEnv.txt` if `preboot` script explicitly loads it
   - QSPI environment variables take precedence over SD card files
   - The `bootcmd` is already set by QSPI before SD card is checked

### Diagnostic Evidence

**Confirming this issue:**
```bash
# Device boots but Linux doesn't start
$ lsusb | grep 0456:b673
Bus 003 Device 059: ID 0456:b673 Analog Devices, Inc. LibIIO

$ ls /dev/ttyUSB*
ls: cannot access '/dev/ttyUSB*': No such file or directory

$ iio_info -S
Available contexts:
    0: 0456:b673 (Analog Devices Inc. PlutoSDR), serial= [usb:3.59.5]

$ ping 192.168.2.1
64 bytes from 192.168.2.1: icmp_seq=1 ttl=64 time=0.362 ms  # U-Boot network works

$ ssh root@192.168.2.1
ssh: connect to host 192.168.2.1 port 22: Connection timed out  # No Linux running

$ lsblk | grep sd
sdb  8:16  1  30M  0 disk  # Only mass storage, not full Linux
└─sdb1  8:17  1  30M  0 part /media/arsatyants/PlutoSDR
```

**Check SD card files from PC:**
```bash
$ md5sum /media/arsatyants/BF32-DA7B/*
75ef4698612695e6c5f8c8c81f00a744  BOOT.bin
7a5825aef86734515efdf3ea895db5cc  uImage
c24e007013b1f276f055f870b790685e  devicetree.dtb
94ffe2a7dffd6144721e43401b550cb8  uramdisk.image.gz
# All checksums match build artifacts ✓
```

### Attempted Solutions & Why They Failed

#### Attempt 1: Modified config.txt to Enter DFU Mode

```bash
# Set dfu = 1 in config.txt on mass storage
[ACTIONS]
dfu = 1

# Result: FAILED
# - LibreSDR firmware doesn't support PlutoSDR's config.txt action mechanism
# - Device reboots but returns to same mass storage mode
# - DFU mode never activated
```

#### Attempt 2: Force SD Boot via Simplified uEnv.txt

Created minimal `uEnv.txt` to override QSPI environment:
```bash
# Force SD card boot - override QSPI environment
modeboot=sdboot
bootcmd=run sdboot
bootdelay=1

# SD boot command
sdboot=if mmcinfo; then echo Copying Linux from SD to RAM... && load mmc 0 0x2080000 uImage && load mmc 0 0x2000000 devicetree.dtb && load mmc 0 0x4000000 uramdisk.image.gz && bootm 0x2080000 0x4000000 0x2000000; fi
```

**Result: FAILED**
- U-Boot still reads QSPI environment first
- `bootcmd` from QSPI executed before `uEnv.txt` is processed
- Device still boots to mass storage mode

### Why This Is a Catch-22 Situation

**The problem:**
1. Need to **erase QSPI** to remove corrupted U-Boot environment
2. Erasing QSPI requires either:
   - Full Linux boot (to use `flashcp` or `sf` commands)
   - Working JTAG interface (to use `openFPGALoader`)
   - DFU mode (to flash via USB)
3. **BUT:**
   - Can't boot Linux because QSPI environment blocks it
   - Can't access JTAG because FT2232H is only initialized by Linux
   - Can't enter DFU mode because firmware doesn't support it

**Visual representation:**
```
QSPI has corrupted env
       ↓
Blocks Linux boot
       ↓
No /dev/ttyUSB* (FTDI not initialized)
       ↓
Can't use JTAG to erase QSPI
       ↓
Can't boot Linux to erase QSPI
       ↓
(cycle repeats)
```

### Solutions for This Specific Issue

#### Solution 1: External JTAG Programmer (Most Reliable)

Use external JTAG adapter that doesn't depend on the FT2232H on board:

**Hardware needed:**
- External JTAG adapter (Xilinx Platform Cable USB, SEGGER J-Link, or compatible)
- Connect to JTAG header on board (refer to schematic)

**Procedure:**
```bash
# Using Xilinx Vivado Hardware Manager
vivado -mode tcl
connect_hw_server
open_hw_target
current_hw_device [get_hw_devices xc7z020_1]

# Erase QSPI flash
create_hw_cfgmem -hw_device [current_hw_device] -mem_dev [lindex [get_cfgmem_parts {n25q128a11}] 0]
delete_hw_cfgmem [current_hw_cfgmem]

# Or use openFPGALoader with external adapter
openFPGALoader --cable <adapter_type> --bulk-erase
```

#### Solution 2: SD Card Hardware Investigation

Since FSBL + U-Boot load successfully, but kernel doesn't, check:

**Physical inspection:**
```bash
# Remove SD card, inspect for:
1. Dirty/oxidized gold contacts → Clean with isopropyl alcohol
2. Bent/broken spring pins in socket → Requires soldering repair
3. Loose SD card connection → Try gently pushing card while booting
```

**Try different SD card:**
```bash
# Sometimes specific cards work better
- Use smaller capacity (4GB or 8GB, not 32GB+)
- Use slower speed class (Class 4-10, not UHS-I/II)
- Try different brand (SanDisk, Samsung, Kingston)
```

#### Solution 3: U-Boot Network Console (If Enabled)

Some U-Boot builds have network console enabled:

```bash
# Check if U-Boot responds to network commands
nc -u 192.168.2.1 6666

# If console appears, try:
setenv modeboot sdboot
setenv bootcmd 'run sdboot'
saveenv
boot
```

**Verification:**
```bash
# In U-Boot network console (if accessible)
printenv modeboot
printenv bootcmd

# Should show:
# modeboot=sdboot
# bootcmd=run sdboot
```

#### Solution 4: Hardware QSPI Chip Desoldering (Last Resort)

If all else fails and external JTAG unavailable:

1. **Identify QSPI chip** (usually 25Q128 or similar near Zynq)
2. **Desolder or lift pin 1** (chip select)
3. **Boot from SD card** (QSPI disabled)
4. **Linux will boot** (no QSPI interference)
5. **Flash QSPI via software**, then resolder

**Warning:** Requires advanced soldering skills and risks board damage.

### Preventive Measures

To avoid this issue in future:

**Always erase QSPI before first SD card test:**
```bash
# Via JTAG before any firmware testing
sudo openFPGALoader -d /dev/ttyUSB1 --bulk-erase
```

**After successful SD boot, flash QSPI immediately:**
```bash
ssh root@192.168.2.1
mount /dev/mmcblk0p1 /mnt
flashcp -v /mnt/BOOT.bin /dev/mtd0
# Verify checksums match
md5sum /mnt/BOOT.bin
nanddump -f /tmp/verify /dev/mtd0 -l $(stat -c%s /mnt/BOOT.bin)
md5sum /tmp/verify
```

**Use proper boot mode for testing:**
```bash
# If board has boot mode jumpers/switches:
# Set to JTAG or SD Card mode during development
# Only switch to QSPI mode after firmware is stable
```

### Decision Tree for This Specific Issue

```
SD card files verified correct, but device stuck in U-Boot mass storage?

├─ Check QSPI for partial firmware
│  └─ Symptom: Ping works, no SSH, no serial ports
│
├─ Try external JTAG adapter
│  ├─ Available? → Erase QSPI directly (Solution 1)
│  └─ Not available? → Continue below
│
├─ Try different SD card
│  ├─ 4-8GB, Class 4-10, major brand
│  └─ Clean contacts with isopropyl alcohol
│
├─ Check for U-Boot network console
│  └─ nc -u 192.168.2.1 6666
│     └─ If accessible: setenv modeboot sdboot && saveenv && boot
│
└─ Last resort: Hardware modification
   └─ Desolder QSPI CS pin → Boot from SD → Flash via software → Resolder
```

### Key Takeaway

**The LibreSDR is functioning correctly** - this is a firmware state issue, not hardware failure. The SD card slot, Zynq SoC, and U-Boot are all working. The problem is a corrupted U-Boot environment in QSPI flash that prevents the boot sequence from completing to Linux.

**Most likely path forward:** Obtain external JTAG programmer (Xilinx Platform Cable USB ~$50-200) to erase QSPI, then SD card boot will work normally.

---

## Troubleshooting Common Issues

### USB Connection Instability (Continuous Disconnect/Reconnect)

**Symptom:** Device boots successfully but USB disconnects and reconnects every ~55 seconds:
```bash
$ dmesg | tail
[329019.438510] usb 3-5: USB disconnect, device number 62
[329074.721402] usb 3-5: new high-speed USB device number 63 using xhci_hcd
[329074.850931] usb 3-5: USB disconnect, device number 63
[329130.133318] usb 3-5: new high-speed USB device number 64 using xhci_hcd
```

**Impact:** 
- Network interface (`enx00e022adc83b`) repeatedly unregisters
- SSH connections drop
- SDR applications (SDR Angel, etc.) fail with "Could not start sample source"
- IIO operations timeout

**Causes:**
1. **Insufficient USB power** - Device drawing too much current
2. **Thermal shutdown** - FPGA or AD9361 overheating
3. **Software watchdog** - Kernel watchdog triggering resets
4. **Bad USB cable/port** - Poor connection or damaged cable
5. **USB power management** - Host OS suspending device

**Diagnostic Steps:**

1. **Monitor serial console during disconnect:**
```bash
sudo cat /dev/ttyACM0
# Watch for kernel panic, watchdog messages, thermal warnings, or OOM killer
```

2. **Check device temperature and logs when stable:**
```bash
ssh root@192.168.2.1
# Check thermal status
cat /sys/class/thermal/thermal_zone0/temp  # Temperature in millidegrees
# Check for watchdog/thermal in logs
dmesg | grep -i "thermal\|watchdog\|reset\|error\|oom"
# Check running processes
ps aux
```

3. **Test with different USB configuration:**
```bash
# Try different USB port (preferably USB 3.0 with higher power delivery)
# Try shorter/better quality USB cable
# Try powered USB hub
# Check if device feels hot to touch
```

4. **Disable USB autosuspend on host:**
```bash
# Temporary
echo -1 | sudo tee /sys/bus/usb/devices/*/power/autosuspend_delay_ms

# Permanent - add to /etc/udev/rules.d/50-usb-power.rules
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="0456", ATTR{idProduct}=="b673", ATTR{power/autosuspend}="-1"
```

5. **Reconfigure network after disconnect (workaround):**
```bash
# Network interface needs reconfiguration after each reconnect
sudo ip addr flush dev enx00e022adc83b
sudo ip addr add 192.168.2.10/24 dev enx00e022adc83b
sudo ip link set enx00e022adc83b up
ping -c 2 192.168.2.1
```

**Solution depends on cause:**
- **Power issue**: Use powered USB hub or different port
- **Thermal**: Add heatsink to FPGA, improve airflow, reduce clock speeds
- **Watchdog**: Disable or increase timeout via device tree modification
- **Cable**: Replace with high-quality USB cable (preferably <1 meter)

### SDR Applications Fail to Start (SDR Angel, GNU Radio, etc.)

**Symptom:** Application detects device but can't start streaming:
```
Error: Could not start sample source
Connection timed out
Unable to create IIO context
```

**Common Causes & Solutions:**

1. **IIO buffer size too small (most common):**
```bash
ssh root@192.168.2.1
# Check current buffer size
cat /sys/bus/iio/devices/iio:device3/buffer/length
# If < 128K, increase it:
echo 131072 > /sys/bus/iio/devices/iio:device3/buffer/length
```

**Why:** Default 4096 samples is insufficient for most SDR apps. SDR Angel and GNU Radio typically need 128K-1M samples.

2. **Device disconnected during startup:**
   - See "USB Connection Instability" section above
   - Fix USB stability first before troubleshooting app issues

3. **Test IIO streaming directly:**
```bash
# On host PC (install libiio-utils if needed)
sudo apt install -y libiio-utils

# Test capture from both RX channels
timeout 10 iio_readdev -u ip:192.168.2.1 -s 131072 cf-ad9361-lpc voltage0 voltage1 > /tmp/test.dat

# Check captured data
ls -lh /tmp/test.dat  # Should be ~512KB (131072 samples × 2 channels × 2 bytes)
```

4. **Verify IIO device configuration:**
```bash
iio_info -u ip:192.168.2.1 | grep -A 5 "cf-ad9361"
# Should show:
# - iio:device3: cf-ad9361-lpc (buffer capable)
# - iio:device2: cf-ad9361-dds-core-lpc (buffer capable)
```

5. **Start with conservative settings in SDR application:**
   - **Sample rate:** 2.0 MSPS (not 20+ MSPS initially)
   - **Bandwidth:** Match or slightly exceed sample rate
   - **RF Gain:** Manual mode, 50 dB
   - **Center frequency:** Known good frequency (e.g., 100 MHz)
   - **Decimation:** 1 (no decimation)

6. **Check AD9361 initialization:**
```bash
ssh root@192.168.2.1
dmesg | grep ad9361
# Should show:
# ad9361 spi0.0: ad9361_probe : AD936x Rev 0 successfully initialized
# cf_axi_adc 79020000.cf-ad9361-lpc: ADI AIM ... probed ADC AD9361 as MASTER
```

**If streaming works with iio_readdev but not SDR app:**
- Check app-specific buffer/timeout settings
- Increase timeout values in app configuration
- Ensure app uses correct IIO device (`cf-ad9361-lpc` for RX, `cf-ad9361-dds-core-lpc` for TX)
- Check app logs for specific error messages

---

## Support & Resources

- **Schematics:** See `zynqsdr_rev5.pdf` in this repo
- **Serial consoles:** 
  - `/dev/ttyACM0` - Primary USB CDC ACM console (appears when Linux boots), 115200N8
  - Credentials: `root` / `analog`
- **Default IPs:** 192.168.1.10 (Ethernet), 192.168.2.1 (USB gadget)
- **JTAG interface:** FT4232H on `/dev/ttyUSB0`, `/dev/ttyUSB3-5` (use `-c ft4232` with openFPGALoader)
- **Upstream PlutoSDR docs:** https://wiki.analog.com/university/tools/pluto
- **openFPGALoader docs:** https://trabucayre.github.io/openFPGALoader/

## Summary Decision Tree

```
Device won't boot?
├─ Boots from SD but not QSPI after SD removal?
│  └─ Manually flash QSPI (Method 1, Step 2) - LibreSDR doesn't auto-flash!
│
├─ JTAG detection works?
│  ├─ YES → Erase QSPI + SD card boot + Manual QSPI flash
│  └─ NO → Check hardware/cables
│
├─ Boots to U-Boot but hangs?
│  └─ Rebuild firmware + Check DDR timing
│
├─ Boots but network unreachable?
│  └─ Use serial console + Check eth0 config
│
├─ Sample rate limited (<20 MSPS)?
│  └─ Verify overclock + Rebuild with OVERCLOCK_CPU_MULT=44
│
└─ Crashes at high sample rates?
   └─ Reduce overclock + Improve cooling + Check power supply
```

**Recommended recovery path for most failures:**
1. Start with **SD Card Boot (Method 1, Step 1)** - safest and fastest
2. **MANUALLY flash QSPI** using `flashcp` (Method 1, Step 2) - LibreSDR does NOT auto-flash!
3. If SD fails, use **JTAG Erase + SD Boot + Manual QSPI** (Method 2 → Method 1)
4. Only use XSCT (Method 3) if openFPGALoader unavailable

---

## QSPI Persistence Issue Investigation (Rev.5 Hardware)

### Problem Summary

**LibreSDR Rev.5** with **Winbond w25q256 (32MB)** QSPI flash experiences data loss after power cycles:
- ✅ Data writes to QSPI succeed
- ✅ Data verifies immediately after write
- ❌ **Data erases to 0xFF after power cycle**
- ✅ BOOT.bin (mtd0) persists correctly
- ❌ Linux firmware (mtd3) erases

### Root Cause Analysis

**Device Tree Mismatch:**
The PlutoSDR v0.38 firmware was designed for **Micron n25q256a** but LibreSDR Rev.5 uses **Winbond w25q256**. The device tree in both Linux kernel and U-Boot incorrectly specified:
```dts
compatible = "n25q256a","micron,m25p80";  // WRONG for w25q256
```

**16MB Addressing Boundary Issue:**
The w25q256 (32MB) requires 4-byte addressing or Extended Address Register (EAR) for addresses above 16MB:
- **mtd0** (0-4MB): ✅ Persists - within 3-byte addressing range
- **mtd1** (4-4.125MB): ✅ Persists - tested and confirmed
- **mtd3** (5MB-32MB): ❌ Erases - crosses 16MB boundary, needs 4-byte addressing

**Boot Sequence Problem:**
1. **U-Boot runs FIRST** → Initializes QSPI with wrong driver (n25q256a)
2. **Linux boots** → Re-initializes with correct driver (after fix)
3. **User writes data** → Appears successful
4. **Power cycle** → Data lost because initial U-Boot misconfiguration

Even with Linux kernel device tree fixed, U-Boot's incorrect initialization at boot prevents proper flash programming.

### Fixes Applied

**1. Linux Kernel Device Tree Fix** (`linux/arch/arm/boot/dts/zynq-libre.dtsi`):
```dts
&qspi {
    primary_flash: ps7-qspi@0 {
        compatible = "winbond,w25q256", "jedec,spi-nor";  // FIXED
        spi-max-frequency = <50000000>;
        m25p,fast-read;
        broken-flash-reset;
        spi-nor,ddr-quad-read-dummy = <6>;
        no-wp;
```

**2. U-Boot Device Tree Fix** (`u-boot-xlnx/arch/arm/dts/zynq-libre-sdr.dts`):
```dts
flash@0 {
    compatible = "winbond,w25q256", "jedec,spi-nor";  // FIXED
    reg = <0x0>;
    spi-tx-bus-width = <1>;
    spi-rx-bus-width = <4>;
    spi-max-frequency = <50000000>;
    m25p,fast-read;
    broken-flash-reset;
    
    partition@0 {
        label = "qspi-fsbl-uboot";
        reg = <0x0 0x400000>;  // Increased to 4MB for larger BOOT.bin
    };
```

**3. Patches Updated:**
- `patches/linux.diff` - Linux kernel w25q256 fix
- `patches/u-boot-xlnx.diff` - U-Boot w25q256 fix

### Testing Results

**Test 1: Linux Kernel Fix Only**
- Applied w25q256 device tree to Linux kernel
- Rebuilt and flashed firmware
- Result: ❌ Data still erases after power cycle
- Conclusion: U-Boot initialization matters

**Test 2: 16MB Boundary Test (mtd1)**
- Wrote test data to mtd1 (below 16MB boundary)
- Power cycled device
- Result: ✅ Data persisted!
- Conclusion: Flash hardware works, issue is addressing mode

**Test 3: U-Boot Rebuild Without Vivado**
- Built new U-Boot with w25q256 device tree fix
- Created BOOT.bin using U-Boot SPL + bootgen
- Flashed to mtd0 and tested
- Result: ❌ Data still erases after power cycle
- Conclusion: **U-Boot SPL doesn't initialize QSPI properly**

### Current Status

**What Works:**
- ✅ Hybrid boot (QSPI BOOT.bin + SD card Linux)
- ✅ All firmware components built with w25q256 fixes
- ✅ Writes below 16MB boundary persist
- ✅ Device tree patches committed

**What Doesn't Work:**
- ❌ Standalone QSPI boot (data erases after power cycle)
- ❌ U-Boot SPL approach (lacks QSPI initialization)

**Blocking Issue:**
**Proper FSBL from Vivado is required.** U-Boot SPL (used as bootloader workaround) does not perform full QSPI flash initialization. Without Vivado:
- Cannot generate proper FSBL with QSPI support
- Cannot create complete BOOT.bin with full hardware init
- Cannot test if w25q256 fixes actually work

### Required Steps to Complete Fix

**Prerequisites:**
1. Install **Xilinx Vivado 2022.2** (or 2025.2)
   - Download: https://www.xilinx.com/support/download.html
   - Requires free Xilinx account
   - ~30GB download + ~150GB installation
   - Can install to external drive (e.g., `/media/vivado/Xilinx`)

**Build Process:**
```bash
cd ~/code/libresdr/plutosdr-fw_0.38_libre
source /path/to/Vivado/2022.2/settings64.sh
export TARGET=libre
make clean
make
```

This will:
1. Build HDL in Vivado (generates FPGA bitstream)
2. Create FSBL with proper QSPI initialization
3. Build U-Boot with w25q256 device tree
4. Package BOOT.bin with bootgen (FSBL + bitstream + U-Boot)
5. Build Linux kernel with w25q256 device tree
6. Create complete firmware

**Testing After Build:**
```bash
# Flash new BOOT.bin with proper FSBL
cat build/sdk/BOOT.bin | ssh root@192.168.1.10 \
  "cat > /tmp/BOOT.bin && \
   flash_erase /dev/mtd0 0 0 && \
   dd if=/tmp/BOOT.bin of=/dev/mtd0 bs=1M && sync"

# Flash Linux firmware
cat build/libre.itb | ssh root@192.168.1.10 \
  "cat > /tmp/libre.itb && \
   flash_erase /dev/mtd3 0 0 && \
   dd if=/tmp/libre.itb of=/dev/mtd3 bs=1M && sync"

# Power cycle and verify persistence
ssh root@192.168.1.10 "poweroff"
# Physically power cycle (unplug/replug)
# Wait 40 seconds for boot

ssh root@192.168.1.10 \
  "dd if=/dev/mtd3 bs=1M count=1 2>/dev/null | md5sum"
# Should NOT be: 2fdd6851b32ae931637d4845c037b550 (all 0xFF)
```

### Workaround (Until Vivado Build)

**Use Hybrid Boot:**
1. Keep BOOT.bin in QSPI (mtd0) - works fine
2. Boot Linux from SD card
3. Firmware location: `~/code/libresdr/firmware/build_sdimg_new/`
4. Copy to SD card FAT32 partition

**Alternative: Ask Community**
Post on forums/Discord asking if someone with Vivado can build BOOT.bin with these patches:
- U-Boot device tree: `u-boot-xlnx/arch/arm/dts/zynq-libre-sdr.dts` 
- Change line 61: `compatible = "winbond,w25q256", "jedec,spi-nor"`

### Hardware Notes

**Flash Chip Identification:**
```bash
# Check what's detected
ssh root@192.168.1.10 "dmesg | grep spi-nor"
# Should show: spi-nor spi1.0: w25q256 (32768 Kbytes)
```

**Partition Layout:**
```bash
ssh root@192.168.1.10 "cat /proc/mtd"
# mtd0: 00400000 00010000 "qspi-fsbl-uboot"    # 4MB - BOOT.bin
# mtd1: 00020000 00010000 "qspi-uboot-env"     # 128KB - U-Boot env
# mtd2: 000e0000 00010000 "qspi-nvmfs"         # 896KB - Config
# mtd3: 01b00000 00010000 "qspi-linux"         # 27MB - Linux firmware
```

**Addressing Test:**
```bash
# Test write below 16MB (should persist)
ssh root@192.168.1.10 \
  "echo 'TEST' > /tmp/test.bin && \
   flash_erase /dev/mtd1 0 0 && \
   dd if=/tmp/test.bin of=/dev/mtd1 && sync"
# Power cycle and verify
```

## QSPI Data Persistence Issue (Rev.5 w25q256)

### Issue Summary

LibreSDR Rev.5 uses Winbond **w25q256** (32MB) QSPI flash, but upstream PlutoSDR firmware expects Micron **n25q256a**. This causes data written to mtd3 (Linux partition, 5MB-32MB range) to **erase to 0xFF after power cycles**, while mtd0 (BOOT.bin, 0-4MB) persists correctly.

### Root Cause Analysis

**The Problem:**
- w25q256 uses **3-byte addressing** for 0-16MB and requires **4-byte addressing** or **Extended Address Register (EAR)** for 16MB-32MB
- mtd0 (0-4MB): ✅ Within 3-byte range, persists correctly
- mtd3 (5MB-32MB): ❌ Crosses 16MB boundary, requires 4-byte addressing

**Boot Sequence Impact:**
1. **U-Boot initializes QSPI first** with device tree specifying `n25q512a` driver
2. Wrong driver doesn't configure 4-byte addressing or EAR properly
3. **Linux kernel re-initializes** with correct `w25q256` driver, but initial misconfiguration persists
4. Writes above 16MB appear successful but don't actually program flash cells correctly
5. **Power cycle** → hardware reset → data appears as 0xFF (erased)

**Evidence:**
- mtd1 persistence test (4MB-4.125MB, below 16MB): ✅ Data persists after power cycle
- mtd3 persistence test (5MB-32MB, crosses 16MB): ❌ Data erases after power cycle
- Kernel error: `spi-nor spi1.0: failed to read ear reg` (Extended Address Register failure)

### Device Tree Fixes Applied

**Linux Kernel** (`linux/arch/arm/boot/dts/zynq-libre.dtsi`):
```dts
&qspi {
    primary_flash: ps7-qspi@0 {
        compatible = "winbond,w25q256", "jedec,spi-nor";
        spi-max-frequency = <50000000>;
        m25p,fast-read;
        broken-flash-reset;
        spi-nor,ddr-quad-read-dummy = <6>;
        no-wp;
        // ... partition definitions
    };
};
```

**U-Boot** (`u-boot-xlnx/arch/arm/dts/zynq-libre-sdr.dts`):
```dts
flash@0 {
    compatible = "winbond,w25q256", "jedec,spi-nor";
    spi-tx-bus-width = <1>;
    spi-rx-bus-width = <4>;
    spi-max-frequency = <50000000>;
    m25p,fast-read;
    broken-flash-reset;
    // Updated partition sizes
    partition@0 { reg = <0x0 0x400000>; }; // mtd0: 4MB for BOOT.bin
    // ... other partitions
};
```

### Build Requirements

To fix this issue, you **must rebuild BOOT.bin** with the corrected U-Boot device tree. This requires:

**Required:**
- Xilinx Vivado 2022.2 (generates FSBL and bitstream)
- `xilinx-bootgen` package (to create BOOT.bin)

**Attempted Workarounds (All Failed):**
- ❌ Rebuilding only U-Boot with U-Boot SPL as bootloader - SPL doesn't initialize QSPI
- ❌ Extracting FSBL from old BOOT.bin - creates oversized images that don't fit in mtd0
- ❌ Using Linux kernel fix alone - U-Boot still misconfigures flash during early boot

**Without Vivado, full QSPI boot is not possible.** The device can operate in **hybrid boot mode** (QSPI BOOT.bin + SD Linux) as a workaround.

### Rebuild Procedure (With Vivado)

```bash
# 1. Install Vivado 2022.2 (requires ~150GB disk space)
# Download from: https://www.xilinx.com/support/download.html

# 2. Install bootgen (if not already installed)
sudo apt install xilinx-bootgen

# 3. Clean and rebuild firmware
cd ~/code/libresdr/plutosdr-fw_0.38_libre
source /path/to/Vivado/2022.2/settings64.sh
export TARGET=libre
make clean
make              # Builds HDL, FSBL, U-Boot, Linux
make sdimg        # Creates SD card image

# 4. Flash new BOOT.bin to mtd0
cat build_sdimg/BOOT.bin | ssh root@192.168.1.10 \
  "cat > /tmp/BOOT.bin && \
   flash_erase /dev/mtd0 0 0 && \
   dd if=/tmp/BOOT.bin of=/dev/mtd0 bs=1M && sync"

# 5. Flash firmware to mtd3
cat build/libre.itb | ssh root@192.168.1.10 \
  "cat > /tmp/libre.itb && \
   flash_erase /dev/mtd3 0 0 && \
   dd if=/tmp/libre.itb of=/dev/mtd3 bs=1M && sync"

# 6. Power cycle and verify persistence
# Data should now persist after power cycles
```

### Verification Commands

```bash
# Check flash detection
ssh root@192.168.1.10 "dmesg | grep -i 'spi-nor\|w25q256'"
# Expected: "spi-nor spi1.0: w25q256 (32768 Kbytes)"
# May still show "failed to read ear reg" but data should persist

# Verify partition MD5 before power cycle
ssh root@192.168.1.10 \
  "dd if=/dev/mtd3 bs=1M count=1 2>/dev/null | md5sum"
# Record this MD5

# Power cycle device, then check again
ssh root@192.168.1.10 \
  "dd if=/dev/mtd3 bs=1M count=1 2>/dev/null | md5sum"
# Should match pre-power-cycle MD5 (NOT 2fdd6851b32ae931637d4845c037b550)
```

### Current Status (January 2026)

- ✅ **Device tree fixes**: Applied to both Linux kernel and U-Boot
- ✅ **Patches regenerated**: All fixes committed to repository
- ✅ **Linux kernel rebuild**: Completed with w25q256 driver
- ✅ **U-Boot rebuild**: Completed with w25q256 device tree
- ✅ **Hybrid boot**: Working (QSPI BOOT.bin + SD Linux)
- ❌ **QSPI data persistence**: **Still broken** - requires FSBL rebuild with Vivado
- ⏳ **Vivado installation**: Pending (requires manual download and installation)

**Interim Solution:** Use hybrid boot mode - flash BOOT.bin to mtd0, boot Linux from SD card. This provides full functionality while awaiting Vivado availability.

**Next Steps:**
1. Download Vivado 2022.2 from Xilinx (requires free account)
2. Install to `/media/vivado/Xilinx` (external SD card with 228GB available)
3. Rebuild firmware with proper FSBL (required - cannot use U-Boot SPL)
4. Flash new BOOT.bin with corrected FSBL + U-Boot w25q256 fix
5. Test QSPI mtd3 persistence after power cycle
6. Achieve standalone QSPI boot

## QSPI Flash Persistence Investigation

### Problem Summary

**Issue:** Data written to QSPI flash partition mtd3 (27MB, offset 5MB-32MB) erases to all 0xFF after power cycles, preventing standalone QSPI boot.

**Hardware:** LibreSDR Rev.5 with Winbond w25q256 (32MB NOR flash, JEDEC ID 0xef4019)

**Root Cause:** Incorrect flash chip specification in device trees causes improper 4-byte addressing mode initialization for >16MB address space.

### Investigation Timeline (Jan 16-17, 2026)

#### Initial Discovery
- Flashed `libre.itb` to mtd3, verified immediately: **SUCCESS** ✅
- Power cycled device: mtd3 data erased to all 0xFF: **FAILURE** ❌
- mtd0 (BOOT.bin) persists after power cycles: **SUCCESS** ✅
- Conclusion: Flash hardware is functional, issue is software initialization

#### Device Tree Mismatch Found

**Linux Kernel Device Tree** (`zynq-libre.dtsi`):
```diff
- compatible = "n25q256a", "jedec,spi-nor";  // WRONG - Micron chip
+ compatible = "winbond,w25q256", "jedec,spi-nor";  // CORRECT
```

**U-Boot Device Tree** (`zynq-libre-sdr.dts`):
```diff
- compatible = "n25q512a","micron,m25p80";  // WRONG - Micron chip
+ compatible = "winbond,w25q256", "jedec,spi-nor";  // CORRECT
```

#### Testing Linux Fix Alone

**Test:** Rebuilt Linux kernel with w25q256 device tree fix
- Error "expected n25q256a" eliminated ✅
- Error "failed to read ear reg" persists ❌
- Power cycle test: mtd3 still erases to 0xFF ❌

**Conclusion:** Linux kernel fix alone is insufficient. U-Boot initializes flash FIRST during boot sequence.

#### 16MB Address Boundary Discovery

**Critical Test:**
- mtd0 (0-4MB): Persists after power cycle ✅
- mtd1 (4-4.125MB): **Persists after power cycle** ✅  
- mtd3 (5MB-32MB): Erases after power cycle ❌

**Root Cause Identified:**
- w25q256 has **16MB addressing boundary**
- 0-16MB: Works with 3-byte addressing
- 16MB-32MB: Requires 4-byte addressing OR Extended Address Register (EAR)
- mtd3 crosses 16MB boundary, writes above 16MB fail

#### U-Boot Initialization Impact

**Boot Sequence:**
1. Power on → Zynq PS loads FSBL from QSPI
2. FSBL configures clocks/DDR, loads bitstream
3. **U-Boot initializes QSPI with wrong driver** ← CRITICAL FAILURE POINT
4. Linux boots, re-initializes QSPI (too late - chip state already corrupted)

**Why U-Boot Matters:**
- U-Boot runs before Linux
- Incorrect n25q512a driver doesn't enable 4-byte addressing
- Flash chip enters wrong mode
- Even though Linux has correct driver, writes to >16MB addresses fail
- Power cycle resets chip, revealing that data was never properly written

#### Attempted Fix: U-Boot Only Rebuild

**Approach:** Rebuild U-Boot with w25q256 fix, create new BOOT.bin without Vivado

**Steps Taken:**
1. Fixed U-Boot device tree: `arch/arm/dts/zynq-libre-sdr.dts`
2. Rebuilt U-Boot: `make -C u-boot-xlnx ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf-`
3. Installed `xilinx-bootgen` from Ubuntu repos (no Vivado needed!)
4. Created BOOT.bin using U-Boot SPL as bootloader:
   ```bash
   bootgen -arch zynq -image boot.bif -w -o BOOT.bin
   # BIF contained: SPL + bitstream + new U-Boot
   ```
5. Flashed to mtd0, power cycled

**Result:** FAILED ❌
- mtd3 still erases to 0xFF after power cycle
- U-Boot SPL doesn't initialize QSPI hardware
- QSPI initialization happens later, but without proper setup from FSBL

#### Why FSBL is Required

**FSBL (First Stage Boot Loader) responsibilities:**
- Full Zynq PS7 peripheral initialization
- QSPI controller configuration
- Sets up memory map and addressing modes
- **Must be built by Vivado** from HDL project

**U-Boot SPL limitations:**
- Minimal bootloader, focuses on loading next stage
- Does not perform full QSPI initialization
- Cannot replace FSBL for QSPI-dependent boot

**Conclusion:** Cannot achieve working QSPI boot without Vivado-generated FSBL.

### Technical Details

#### Flash Partitions
```
dev:    size     erasesize  name
mtd0: 00400000   00010000   "qspi-fsbl-uboot"      (0-4MB)      ✅ Persists
mtd1: 00020000   00010000   "qspi-uboot-env"       (4-4.125MB)  ✅ Persists  
mtd2: 000e0000   00010000   "qspi-nvmfs"           (4.125-5MB)
mtd3: 01b00000   00010000   "qspi-linux"           (5MB-32MB)   ❌ Erases
```

#### Kernel Errors
```
spi-nor spi1.0: failed to read ear reg
spi-nor spi1.0: w25q256 (32768 Kbytes)
```

**"failed to read ear reg"**: Extended Address Register read failure indicates 4-byte addressing mode not properly enabled.

#### Device Tree Fixes Applied

**Linux Kernel:** `linux/arch/arm/boot/dts/zynq-libre.dtsi`
```dts
&qspi {
    primary_flash: ps7-qspi@0 {
        compatible = "winbond,w25q256", "jedec,spi-nor";
        spi-max-frequency = <50000000>;
        m25p,fast-read;
        broken-flash-reset;
        spi-nor,ddr-quad-read-dummy = <6>;
        no-wp;
        #address-cells = <1>;
        #size-cells = <1>;
        
        partition@0 {
            label = "qspi-fsbl-uboot";
            reg = <0x0 0x400000>;  // 4MB (increased from 1MB)
        };
        // ... other partitions ...
    };
};
```

**U-Boot:** `u-boot-xlnx/arch/arm/dts/zynq-libre-sdr.dts`
```dts
flash@0 {
    compatible = "winbond,w25q256", "jedec,spi-nor";
    reg = <0x0>;
    spi-tx-bus-width = <1>;
    spi-rx-bus-width = <4>;
    spi-max-frequency = <50000000>;
    m25p,fast-read;
    broken-flash-reset;
    #address-cells = <1>;
    #size-cells = <1>;
    
    partition@0 {
        label = "qspi-fsbl-uboot";
        reg = <0x0 0x400000>;  // 4MB
    };
    // ... other partitions ...
};
```

#### Patches Updated
All fixes committed to `patches/linux.diff` and `patches/u-boot-xlnx.diff` for reproducible builds.

### Current Status

**Working:**
- ✅ Hybrid boot (QSPI BOOT.bin + SD card Linux)
- ✅ IIO/SDR functionality (30.72 MSPS confirmed)
- ✅ Device tree fixes applied and tested
- ✅ Writes to QSPI 0-16MB address range persist
- ✅ U-Boot rebuilt with w25q256 fix
- ✅ All patches regenerated with fixes

**Not Working:**
- ❌ QSPI mtd3 persistence (data erases after power cycle)
- ❌ Standalone QSPI boot (requires mtd3 working)

**Blocking Issue:**
- **Vivado required** to rebuild FSBL with proper QSPI initialization
- U-Boot SPL approach insufficient
- Cannot proceed without Vivado 2022.2 installation

### Solution Requirements

**Must Have:**
1. Xilinx Vivado 2022.2 (free WebPack edition)
2. ~150GB disk space for installation
3. Xilinx account (free registration)

**Build Process (once Vivado installed):**
```bash
cd ~/code/libresdr/plutosdr-fw_0.38_libre
export VIVADO_SETTINGS=/opt/Xilinx/Vivado/2022.2/settings64.sh
export TARGET=libre
make clean
make              # Full HDL + FSBL + U-Boot + Linux build (1-2 hours)
make sdimg        # Generate SD card boot files
```

**Expected Result:**
- New BOOT.bin with corrected FSBL + U-Boot w25q256 device trees
- Proper 4-byte addressing mode initialization
- QSPI mtd3 data persistence after power cycles
- Standalone QSPI boot capability

### Workarounds (Interim)

**Hybrid Boot Configuration:**
- BOOT.bin in QSPI mtd0 (U-Boot + FSBL)
- Linux kernel + rootfs on SD card
- Fully functional for development
- Network: 192.168.1.10/24 (gigabit Ethernet)
- Serial console: /dev/ttyACM0 @ 115200N8

**To Use Hybrid Boot:**
1. Ensure BOOT.bin in mtd0: `ssh root@192.168.1.10 "dd if=/dev/mtd0 bs=1M count=1 | md5sum"`
2. Boot files on SD card FAT32 partition:
   - `uImage` (Linux kernel)
   - `devicetree.dtb`
   - `uEnv.txt`
3. Device boots automatically, loads Linux from SD

### References

- PlutoSDR firmware: https://github.com/analogdevicesinc/plutosdr-fw
- Winbond w25q256 datasheet: https://www.winbond.com/resource-files/w25q256jv%20spi%20revg%2008032017.pdf
- Linux SPI-NOR driver: `drivers/mtd/spi-nor/winbond.c`
- Xilinx QSPI driver: `drivers/spi/spi-zynq-qspi.c`

### Last Updated

Investigation completed: January 17, 2026
- All device tree fixes applied and committed
- Awaiting Vivado installation for FSBL rebuild
- Hybrid boot confirmed working as interim solution