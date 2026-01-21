# LibreSDR 2T2R Channel Testing Guide

This guide covers how to verify all TX/RX channels are functioning correctly on LibreSDR (Zynq 7020 + AD9363 in 2RX/2TX mode).

## Quick Test with Python Script

### Prerequisites
```bash
pip install pyadi-iio numpy
```

### Running the Test
```bash
cd /home/arsatyants/code/libresdr
python3 test_2t2r_fixed.py
```

### Expected Output
All 4 channel combinations should pass:
```
============================================================
TEST SUMMARY
============================================================
TX     RX     Status       RSSI (dBFS)    
------------------------------------------------------------
TX1   RX1   ✓ PASS       12.6           
TX2   RX1   ✓ PASS       9.5            
TX1   RX2   ✓ PASS       7.6            
TX2   RX2   ✓ PASS       9.6            
============================================================

✓✓✓ All channels working! RX2 is functional! ✓✓✓
```

**RSSI Values:**
- **> -40 dBFS**: Excellent (typical for loopback testing)
- **-40 to -60 dBFS**: Good
- **-60 to -80 dBFS**: Weak signal
- **< -80 dBFS**: Potential hardware issue

---

## Manual Testing via SSH (Low-Level Register Access)

This method directly tests the IIO device without Python dependencies. Useful for debugging or when pyadi-iio isn't available.

### Step 1: Connect via SSH
```bash
ssh root@192.168.1.10
# Password: analog
```

### Step 2: Verify AD9361 Configuration

Check that both RX channels are enabled:
```bash
# Read register 0x002 (RX Enable)
iio_attr -d ad9361-phy reg_read 0x002
# Expected: 0xCC (binary: 11001100)
# Bit 2 = RX2_EN = 1
# Bit 3 = RX1_EN = 1
```

Check PP_RX_SWAP configuration:
```bash
# Read register 0x010 (Parallel Port Config)
iio_attr -d ad9361-phy reg_read 0x010
# Expected: 0xC8 (binary: 11001000)
# Bit 3 = PP_RX_SWAP = 1 (RX1→D4/D5, RX2→D0/D1)
```

### Step 3: List Available IIO Channels

```bash
ls /sys/bus/iio/devices/iio:device3/scan_elements/
```

You should see:
```
in_voltage0_en  # RX1 I-channel
in_voltage1_en  # RX1 Q-channel
in_voltage2_en  # RX2 I-channel
in_voltage3_en  # RX2 Q-channel
```

### Step 4: Enable All RX Channels

```bash
# Enable all 4 voltage channels (RX1 I/Q, RX2 I/Q)
echo 1 > /sys/bus/iio/devices/iio:device3/scan_elements/in_voltage0_en
echo 1 > /sys/bus/iio/devices/iio:device3/scan_elements/in_voltage1_en
echo 1 > /sys/bus/iio/devices/iio:device3/scan_elements/in_voltage2_en
echo 1 > /sys/bus/iio/devices/iio:device3/scan_elements/in_voltage3_en
```

### Step 5: Capture Raw IIO Data

```bash
# Capture 1024 bytes from RX ADC
timeout 2 cat /dev/iio:device3 | hexdump -C | head -64
```

**What to look for:**
- **All channels working**: Values should vary (not all zeros or constant)
- **RX1 working**: Bytes at offsets corresponding to voltage0/1 show activity
- **RX2 working**: Bytes at offsets corresponding to voltage2/3 show activity

Example of healthy output (values change between captures):
```
00000000  3a 0f c1 0f 42 0f b9 0f  3a 0f c5 0f 45 0f bb 0f  |:...B...:...E...|
00000010  39 0f c8 0f 48 0f be 0f  38 0f ca 0f 4a 0f c0 0f  |9...H...8...J...|
```

**Bad examples:**
- All zeros: `00 00 00 00 ...` → Channel completely dead
- Constant value: `ff ff ff ff ...` → Stuck signal
- Two channels vary, two are zero → One RX channel failed

### Step 6: Verify Channel Mapping

To identify which bytes correspond to which channel, transmit a test signal on one TX and observe RX data:

```bash
# On TX1, generate a tone
iio_attr -c ad9361-phy TX1 hardwaregain -30
# (Use external signal generator or pyadi-iio script)

# Capture again and see which voltage channels show increased activity
```

**Channel order in hexdump:**
With 4 channels enabled, data is interleaved in order: `voltage0, voltage1, voltage2, voltage3, voltage0, ...`
- Each sample is 2 bytes (16-bit signed integer)
- Pattern: `I1_low I1_high Q1_low Q1_high I2_low I2_high Q2_low Q2_high` (repeats)

---

## Understanding IIO Channel Architecture

LibreSDR uses the AD9361 in **LVDS 2RX/2TX mode** with the following mapping:

### Physical FPGA Pins → IIO Channels
```
AD9361 Data Lines  FPGA Pins         IIO Channels
─────────────────  ─────────────     ──────────────
D0 (RX2_I)         Y19/Y18           voltage2 (I)
D1 (RX2_Q)         V18/V17           voltage3 (Q)
D4 (RX1_I)         W19/W18           voltage0 (I)
D5 (RX1_Q)         W16/V16           voltage1 (Q)
```

**Note:** With `adi,pp-rx-swap-enable` in device tree, RX1 maps to D4/D5 and RX2 maps to D0/D1.

### IIO Device Structure
- **iio:device0**: `ad9361-phy` (control interface)
- **iio:device1**: `xadc` (Zynq on-chip ADC)
- **iio:device2**: `cf-ad9361-dds-core-lpc` (TX DAC)
- **iio:device3**: `cf-ad9361-lpc` (RX ADC) ← **Used for RX testing**

---

## Troubleshooting

### RX2 Shows No Signal
1. **Verify AD9361 registers** (Step 2 above)
2. **Check IIO scan_elements** exist for voltage2/3
3. **Run manual hexdump test** to confirm hardware vs software issue
4. **Check device tree**: Ensure `adi,pp-rx-swap-enable` is present in `zynq-libre.dtsi`

### Python Script Fails with "TX mapping exceeds available channels"
This is a pyadi-iio limitation. The `test_2t2r_fixed.py` script bypasses this by directly accessing `sdr._txdac` and `sdr._rxadc` channels.

### Data Format Issues
- **pyadi-iio** returns different formats depending on enabled channels:
  - **Channels [0,1]**: Returns list with 2 elements (I and Q arrays)
  - **Channels [2,3]**: Same, returns list of 2 arrays
  - Must recombine: `complex_data = I_array + 1j * Q_array`

### All Channels Return Zero
- Check TX is actually transmitting (use spectrum analyzer or another SDR)
- Verify RX gain is not too low: `iio_attr -c ad9361-phy RX1 hardwaregain 10`
- Ensure TX/RX LO frequencies match

### AD9361 Digital Interface Tuning Failed
If you see `ad9361_dig_tune_delay: Tuning RX FAILED!` on boot:
- **Do NOT remove** `adi,pp-rx-swap-enable` from device tree
- This setting is calibrated during initialization and cannot be changed at runtime
- Removing it breaks the LVDS interface timing

---

## Hardware Validation Checklist

Use this checklist when bringing up new LibreSDR hardware:

- [ ] SSH access works (`ssh root@192.168.1.10`)
- [ ] AD9361 register 0x002 = 0xCC (both RX enabled)
- [ ] AD9361 register 0x010 = 0xC8 (swap enabled)
- [ ] IIO device3 has 4 voltage scan_elements (0-3)
- [ ] Manual hexdump shows varying data on all 4 channels
- [ ] Python test script: TX1→RX1 passes
- [ ] Python test script: TX2→RX1 passes
- [ ] Python test script: TX1→RX2 passes
- [ ] Python test script: TX2→RX2 passes

**If any test fails:**
1. Start with manual register checks (most reliable)
2. Confirm hardware with hexdump test
3. Only then debug software (Python/pyadi-iio)

---

## Reference: test_2t2r_fixed.py Script

The automated test script is located at: `/home/arsatyants/code/libresdr/test_2t2r_fixed.py`

**Key features:**
- Tests all 4 TX→RX combinations
- Direct IIO channel control (bypasses pyadi-iio limitations)
- Proper handling of I/Q channel pairs for both TX and RX
- RSSI calculation in dBFS
- Pass/fail criteria based on signal strength

**Usage:**
```bash
python3 test_2t2r_fixed.py
```

**Customization:**
Edit these constants at the top of the script:
```python
LIBRESDR_IP = "ip:192.168.1.10"  # Device IP address
TEST_FREQ = 2.4e9                 # Test frequency (Hz)
SAMPLE_RATE = 27e6                # Sample rate (27 MSPS)
TX_POWER = -30                    # TX gain (dBm)
BUFFER_SIZE = 2**14               # Number of samples (16384)
TEST_DURATION = 0.5               # TX duration per test (seconds)
```

---

## Additional Resources

- **PlutoSDR Wiki**: https://wiki.analog.com/university/tools/pluto (architecture reference)
- **AD9361 Register Map**: See AD9361 UG-570 datasheet
- **libiio Documentation**: https://analogdevicesinc.github.io/libiio/
- **pyadi-iio Source**: https://github.com/analogdevicesinc/pyadi-iio

---

## License

This documentation is part of the LibreSDR project. See LICENSE file in repository root.
