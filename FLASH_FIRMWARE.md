# LibreSDR Firmware Flashing Guide

## Current Status

Your firmware is built and ready:
- **boot.frm**: 639KB (BOOT.bin + U-Boot env)
- **libre.frm**: 16MB (Kernel + rootfs with updated 1MB boot partition)

## Method 1: Serial Console (Recommended for initial flash)

### Requirements
- USB to Serial adapter (FTDI)
- Terminal: minicom, picocom, or screen

### Steps

1. **Connect serial console:**
   ```bash
   # Find serial port (usually /dev/ttyUSB0, ttyUSB1, or ttyUSB2)
   ls -l /dev/ttyUSB*
   
   # Connect with 115200 baud
   sudo picocom -b 115200 /dev/ttyUSB2
   # or
   sudo screen /dev/ttyUSB2 115200
   ```

2. **Boot to U-Boot prompt:**
   - Power on LibreSDR
   - Press any key when you see "Hit any key to stop autoboot"
   - You should see `ZynqMP>` or `Zynq>` prompt

3. **Setup network (on U-Boot):**
   ```
   setenv ipaddr 192.168.1.10
   setenv serverip 192.168.1.1
   saveenv
   ```

4. **On your PC, start TFTP server in one terminal:**
   ```bash
   cd /home/arsatyants/code/libresdr/plutosdr-fw_0.38_libre/build
   
   # Install TFTP server if not installed
   sudo apt-get install tftpd-hpa
   
   # Or use Python TFTP server
   python3 -m pip install --user py3tftp
   python3 -m py3tftp.py3tftp -p 69
   
   # Or simplest: use dnsmasq
   sudo dnsmasq -d -p0 -i eth0 --enable-tftp --tftp-root=$PWD
   ```

5. **Flash from U-Boot:**
   ```
   # Erase boot partition (1MB @ 0x0)
   sf probe 0
   sf erase 0x0 0x100000
   
   # Download and write boot.frm
   tftp 0x10000000 boot.frm
   sf write 0x10000000 0x0 ${filesize}
   
   # Erase Linux partition (30MB @ 0x200000)
   sf erase 0x200000 0x1E00000
   
   # Download and write libre.frm (takes a while - 16MB)
   tftp 0x10000000 libre.frm
   sf write 0x10000000 0x200000 ${filesize}
   
   # Reset
   reset
   ```

---

## Method 2: Via Running Linux (if system boots)

### 2A: Using SSH + nc (netcat)

**On LibreSDR (serial console or SSH):**
```bash
cd /tmp
nc -l -p 1234 > libre.frm
# Wait for file transfer...

# After transfer completes:
md5sum libre.frm  # Verify

# Flash to MTD
cat libre.frm > /dev/mtd3
sync
reboot
```

**On your PC:**
```bash
cd /home/arsatyants/code/libresdr/plutosdr-fw_0.38_libre/build
nc 192.168.1.10 1234 < libre.frm
```

### 2B: Using device_reboot script (if available)

```bash
# From your PC
cd /home/arsatyants/code/libresdr/plutosdr-fw_0.38_libre/build
cat libre.frm | ssh root@192.168.1.10 "cat > /tmp/libre.frm && device_reboot ram"
```

---

## Method 3: DFU via USB (if USB gadget is working)

### Requirements
- USB cable connected to LibreSDR micro-USB port
- dfu-util installed: `sudo apt-get install dfu-util`

### Steps

1. **Check if device is in DFU mode:**
   ```bash
   lsusb | grep 0456:b673
   dfu-util -l
   ```

2. **Flash firmware:**
   ```bash
   cd /home/arsatyants/code/libresdr/plutosdr-fw_0.38_libre/build
   
   # Flash main firmware
   sudo dfu-util -d 0456:b673 -a firmware.dfu -D libre.dfu
   
   # Optionally flash boot
   sudo dfu-util -d 0456:b673 -a boot.dfu -D boot.dfu
   
   # Reset device
   sudo dfu-util -d 0456:b673 -a firmware.dfu -e
   ```

---

## Method 4: JTAG (Recovery/Brick Recovery)

### Requirements
- Xilinx Platform Cable USB II or compatible JTAG adapter
- Vivado/Vitis 2022.2 installed

### Steps

1. **Connect JTAG adapter to LibreSDR JTAG header**

2. **Program via Vivado:**
   ```bash
   cd /home/arsatyants/code/libresdr/plutosdr-fw_0.38_libre/build
   
   source /media/arsatyants/vivado/vivado/Vitis/2022.2/settings64.sh
   
   # Program FPGA and boot
   xsdb scripts/run-xsdb.tcl
   ```

3. **Or use the bootstrap ZIP:**
   ```bash
   unzip libresdr-jtag-bootstrap-v0.38-dirty.zip -d /tmp/jtag
   cd /tmp/jtag
   
   # Edit run.tcl to set correct JTAG cable
   xsct run.tcl
   ```

---

## Partition Layout (Important!)

Your new firmware uses this layout:
```
0x0000000 - 0x0100000 (1MB)   : boot.frm (BOOT.bin + U-Boot env)
0x0100000 - 0x0120000 (128KB) : U-Boot environment
0x0120000 - 0x0200000 (896KB) : NVMFS (persistent config)
0x0200000 - 0x2000000 (30MB)  : libre.frm (kernel + rootfs)
```

**⚠️ WARNING:** If your device currently has different partition offsets, you **must** flash both boot.frm AND libre.frm together. Flashing only one will cause boot failure!

---

## Verification

After flashing and reboot:

1. **Check boot log (serial console):**
   - Should see: `Booting using the fdt blob at...`
   - Should mount rootfs from MTD3

2. **SSH into device:**
   ```bash
   ssh root@192.168.1.10
   ```

3. **Check MTD partitions:**
   ```bash
   cat /proc/mtd
   # Should show:
   # mtd0: 00100000 00001000 "qspi-fsbl-uboot"
   # mtd1: 00020000 00001000 "qspi-uboot-env"
   # mtd2: 000e0000 00001000 "qspi-nvmfs"
   # mtd3: 01e00000 00001000 "qspi-linux"
   ```

4. **Check AD9361:**
   ```bash
   iio_info -n 192.168.1.10 | grep ad9361
   iio_attr -C ad9361-phy
   ```

---

## Troubleshooting

### Device won't boot after flash

1. **Connect serial console** - check for error messages
2. **Check U-Boot environment** - might need to reset
3. **Re-flash via JTAG** using bootstrap files

### Wrong partition layout

If you see errors like:
```
VFS: Cannot open root device "ubi0:rootfs"
```

This means boot.frm and libre.frm have mismatched partition offsets. Re-flash both.

### AD9361 not detected

Check device tree is loaded:
```bash
ls /sys/firmware/devicetree/base/fpga*/ad9361*
```

If missing, kernel DT blob might be wrong. Re-flash libre.frm.

---

## Files Reference

- **build/boot.frm** (639KB): BOOT.bin (FSBL + bitstream + U-Boot) + U-Boot env
- **build/libre.frm** (16MB): Kernel + device tree + rootfs (squashfs)
- **build/boot.dfu** (510KB): DFU version of BOOT.bin
- **build/libre.dfu** (16MB): DFU version of firmware
- **build/libresdr-fw-v0.38-dirty.zip**: Complete firmware package
- **build/libresdr-jtag-bootstrap-v0.38-dirty.zip**: JTAG recovery files

---

## Next Steps After Successful Flash

1. Test basic connectivity: `ping 192.168.1.10`
2. Test IIO: `iio_info -n 192.168.1.10`
3. Set up overclocking (if desired): See main README.md
4. Try passive radar examples: See examples/passive_radar/

Default credentials:
- Username: `root`
- Password: `analog` (PlutoSDR default)
