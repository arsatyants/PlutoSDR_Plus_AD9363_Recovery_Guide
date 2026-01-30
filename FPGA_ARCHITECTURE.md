# LibreSDR FPGA Architecture and Resource Usage

## Zynq XC7Z020 Architecture Overview

LibreSDR uses the **Xilinx Zynq XC7Z020 SoC**, which combines:

```
┌────────────────────────────────────────────────────────────┐
│                    Zynq XC7Z020 SoC                        │
├─────────────────────────────┬──────────────────────────────┤
│  Processing System (PS)     │  Programmable Logic (PL)     │
│  NOT reprogrammable         │  FPGA fabric - programmable  │
├─────────────────────────────┼──────────────────────────────┤
│ • 2× ARM Cortex-A9 @ 750MHz │ • 85,000 Logic Cells         │
│ • 1GB DDR3 RAM Controller   │ • 4.9 Mb Block RAM           │
│ • Ethernet MAC              │ • 220 DSP48E1 Slices         │
│ • USB 2.0 OTG               │ • 4× Clock Management Tiles  │
│ • 2× SD/SDIO                │ • 200× I/O pins              │
│ • SPI, I2C, UART, CAN       │ • LVDS support               │
│ • GPIO, Timers              │                              │
│                             │                              │
│ RUNS LINUX KERNEL           │ IMPLEMENTS CUSTOM HARDWARE   │
└─────────────────────────────┴──────────────────────────────┘
           ↕                             ↕
    AXI4 Interconnect (High-speed data transfer)
```

## What's Implemented in FPGA Fabric (PL)

The LibreSDR FPGA design implements the following IP cores in the programmable logic:

### 1. **AD9361 Interface Core (`axi_ad9361`)**

**Purpose:** Hardware interface to AD9361 transceiver chip

**Implements:**
- **LVDS receiver** (6 differential pairs for RX data + clock + frame)
- **LVDS transmitter** (6 differential pairs for TX data + clock + frame)
- **Bit alignment** and clock recovery logic
- **Data deserializer** (LVDS → parallel samples)
- **Data serializer** (parallel samples → LVDS)
- **Control registers** (AXI4-Lite slave for ARM access)
- **Timing generation** (frame sync, enable signals)

**Configuration for LibreSDR:**
```tcl
CONFIG.CMOS_OR_LVDS_N 0       # LVDS mode (not CMOS)
CONFIG.MODE_1R1T 0            # 2R2T mode (2 RX + 2 TX channels)
CONFIG.ADC_INIT_DELAY 30      # Calibration delay
```

**FPGA Resources Used:**
- ~3,000 LUTs (Logic)
- ~2,000 Flip-Flops (Registers)
- IODELAYE2 primitives for clock alignment
- IDELAY/ODELAY for data skew compensation

### 2. **DMA Controllers (2× `axi_dmac`)**

**Purpose:** High-speed data transfer between FPGA and DDR3 RAM without CPU intervention

#### a. ADC DMA (`axi_ad9361_adc_dma`)
- **Direction:** FPGA → DDR3 RAM (receive path)
- **Mode:** Streaming (non-cyclic)
- **Data width:** 64-bit (32-bit I + 32-bit Q per channel)
- **Transfers:** RX samples from AD9361 to memory buffers

#### b. DAC DMA (`axi_ad9361_dac_dma`)
- **Direction:** DDR3 RAM → FPGA (transmit path)
- **Mode:** Cyclic (repeating buffers)
- **Data width:** 64-bit
- **Transfers:** TX samples from memory to AD9361

**FPGA Resources Used (per DMA):**
- ~1,500 LUTs
- ~2,000 Flip-Flops
- AXI4 master interface (high-speed DDR3 access)

### 3. **FIR Filter - RX Decimator (`rx_fir_decimator`)**

**Purpose:** Digital downconversion filter (reduces sample rate, improves SNR)

**Configuration:**
```tcl
Decimation: 8:1 or 2:1 (configurable)
Taps: 128
Input rate: 61.44 MSPS (max from AD9361)
Output rate: 7.68 MSPS or 30.72 MSPS
```

**Why this exists:**
- AD9361 outputs at fixed rates (61.44, 30.72, 15.36 MSPS)
- Users often want lower rates (to reduce USB/network bandwidth)
- Hardware filter is more efficient than software

**FPGA Resources Used:**
- ~5,000 LUTs
- 18× DSP48E1 slices (hardware multipliers)
- Block RAM for filter coefficients

---

## Complete Signal Chain - Detailed Explanation

### RX Path (Antenna → Software)

```
AD9361 Chip → LVDS Interface → axi_ad9361 → rx_fir_decimator → cpack → DMA → DDR3 RAM → libiio → Software
   (RF)      (12 diff pairs)   (Deserialize)   (Filter I0/Q0)  (Pack)  (Transfer) (Memory) (Driver) (App)
```

#### **Block 1: AD9361 RF Transceiver (Hardware Chip)**

**Function:** Converts RF signal to digital samples

**Process:**
1. **LNA (Low Noise Amplifier):** Amplifies weak RF signal (e.g., -90 dBm to -20 dBm)
2. **Mixer:** Down-converts RF (e.g., 2.4 GHz) to baseband I/Q (DC-centered)
3. **ADC (12-bit, up to 61.44 MSPS):** Digitizes I and Q for two channels
4. **Digital filters:** Half-band filters, decimation
5. **LVDS serializer:** Converts parallel data to 6 differential pairs

**Output:** 
- RX_CLK (clock ~246 MHz DDR = 123 MHz sample clock)
- RX_FRAME (marks I/Q boundaries)
- RX_DATA[5:0] (6 LVDS data lanes, 12 bits per sample DDR)

**Configuration:**
- Mode: 2T2R (2 transmit, 2 receive channels)
- Interface: LVDS (Low Voltage Differential Signaling)
- Sample rate: Software configurable 2.5-61.44 MSPS

---

#### **Block 2: axi_ad9361 (FPGA IP Core)**

**Location:** Programmable Logic (FPGA fabric)

**Function:** LVDS deserializer, clock recovery, parallel data interface

**Sub-blocks:**

##### a. **LVDS Receiver (rx_clk_in, rx_frame_in, rx_data_in)**
```verilog
// Converts differential signals to single-ended
IBUFDS_DIFF_OUT rx_clk_ibuf (.I(rx_clk_in_p), .IB(rx_clk_in_n), .O(rx_clk));
```

##### b. **IDELAY2 (Input Delay Calibration)**
- **Purpose:** Compensates for PCB trace length differences
- **Control:** `delay_clk` (200 MHz) provides delay tap resolution (~78 ps)
- **Configuration:** `CONFIG.ADC_INIT_DELAY 30` = 30 taps × 78 ps = 2.34 ns delay
- **Why needed:** LVDS lanes arrive with different skew due to PCB routing

##### c. **Deserializer (DDR → SDR)**
```
Input:  246 MHz DDR (rising+falling edges) = 492 Mbps per lane
Output: 123 MHz SDR (single edge) = 16-bit words
```

##### d. **Clock Recovery & Frame Alignment**
- Uses `rx_frame_in` to identify I/Q sample boundaries
- Aligns all 6 data lanes to same clock phase
- Generates `adc_valid_i0`, `adc_valid_q0` strobes

##### e. **Data Path Output (per channel)**
```
adc_data_i0[15:0]   - In-phase samples, channel 0 (16-bit signed)
adc_data_q0[15:0]   - Quadrature samples, channel 0
adc_data_i1[15:0]   - In-phase samples, channel 1
adc_data_q1[15:0]   - Quadrature samples, channel 1
adc_valid_i0        - Data valid strobe
adc_enable_i0       - Channel enable control
```

##### f. **AXI4-Lite Register Interface**
- Base address: `0x79020000`
- Software can read/write AD9361 SPI registers
- Control: gain, frequency, sample rate, filter bandwidth
- Status: RSSI, temperature, calibration state

**Clock Domain:** 
- Input: LVDS clock (from AD9361)
- Output: `l_clk` (internal logic clock, same freq as LVDS clock)

**FPGA Resources:**
- 6× IBUFDS (differential input buffers)
- 6× IDELAYE2 (programmable delay elements)
- 6× IDDR (DDR-to-SDR converters)
- ~3,000 LUTs (state machines, alignment logic)
- ~2,000 FFs (pipeline registers)

---

#### **Block 3: rx_fir_decimator (FIR Filter + Decimation)**

**Location:** Programmable Logic

**Function:** Reduces sample rate while improving SNR

**Why Decimation?**
- AD9361 might output 61.44 MSPS
- User wants 7.68 MSPS (8× less data)
- Gigabit Ethernet can't handle 4 channels × 32-bit × 61.44 MSPS = 7.86 Gbps
- Decimation: 61.44 MSPS ÷ 8 = 7.68 MSPS → 984 Mbps (fits in Gigabit Ethernet)

**Filter Stages:**

##### Stage 1: Halfband Filter (HB1)
- Taps: 47
- Decimation: 2:1
- Passband: 0 to 0.4 × Fs
- Stopband: 0.6 × Fs to Nyquist

##### Stage 2: Halfband Filter (HB2)
- Taps: 47
- Decimation: 2:1
- Cascades with HB1 for 4× total

##### Stage 3: Halfband Filter (HB3)
- Taps: 35
- Decimation: 2:1
- Total decimation: 8:1

**Data Flow:**
```
Input:  adc_data_i0[15:0] @ 61.44 MSPS
        ↓ [HB1 @ 2:1]
        @ 30.72 MSPS
        ↓ [HB2 @ 2:1]
        @ 15.36 MSPS
        ↓ [HB3 @ 2:1]
Output: data_out_0[15:0] @ 7.68 MSPS
```

**Connections (from system_bd.tcl):**
```tcl
ad_connect axi_ad9361/adc_data_i0 rx_fir_decimator/data_in_0
ad_connect axi_ad9361/adc_valid_i0 rx_fir_decimator/valid_in_0
ad_connect rx_fir_decimator/data_out_0 cpack/fifo_wr_data_0
ad_connect rx_fir_decimator/valid_out_0 cpack/fifo_wr_en
```

**Control:**
- Software sets decimation ratio via `decim_slice` (xlslice IP)
- Can be bypassed (1:1) or set to 2, 4, or 8
- Controlled via AXI register bit in `axi_ad9361/up_adc_gpio_out`

**FPGA Resources:**
- ~6,000 LUTs (filter logic + control)
- 36× DSP48E1 (hardware multipliers for filter taps)
- 4× BRAM (coefficient storage)

---

#### **Block 4: cpack (util_cpack2 - Channel Packer)**

**Location:** Programmable Logic

**Function:** Combines 4 separate data streams (I0, Q0, I1, Q1) into single AXI Stream

**Why Needed?**
- DMA engine expects single data stream
- But we have 4 channels: I0, Q0, I1, Q1
- Must interleave samples: I0[n], Q0[n], I1[n], Q1[n], I0[n+1], ...

**Data Flow:**
```
Input channels:
  fifo_wr_data_0[15:0]  ← rx_fir_decimator/data_out_0 (I0)
  fifo_wr_data_1[15:0]  ← rx_fir_decimator/data_out_1 (Q0)
  fifo_wr_data_2[15:0]  ← axi_ad9361/adc_data_i1 (I1, no filter)
  fifo_wr_data_3[15:0]  ← axi_ad9361/adc_data_q1 (Q1, no filter)

Output:
  packed_fifo_wr[63:0] = {Q1[15:0], I1[15:0], Q0[15:0], I0[15:0]}
  packed_fifo_wr_en    = Data valid strobe
```

**Note on LibreSDR Channel Processing:**
- **Channel 0 (I0/Q0):** Goes through FIR decimator (filtered)
- **Channel 1 (I1/Q1):** Bypasses FIR (direct from AD9361)
  - This is intentional - channel 1 runs at full rate for certain applications
  - User can enable/disable channels independently

**Connections:**
```tcl
# Channel 0: Filtered path
ad_connect cpack/fifo_wr_data_0 rx_fir_decimator/data_out_0  (I0)
ad_connect cpack/fifo_wr_data_1 rx_fir_decimator/data_out_1  (Q0)

# Channel 1: Direct path
ad_connect cpack/fifo_wr_data_2 axi_ad9361/adc_data_i1       (I1)
ad_connect cpack/fifo_wr_data_3 axi_ad9361/adc_data_q1       (Q1)
```

**FPGA Resources:**
- ~800 LUTs (packing logic)
- ~600 FFs (FIFO control)
- Small FIFO (512 samples) to handle clock domain crossing

---

#### **Block 5: axi_ad9361_adc_dma (DMA Controller)**

**Location:** Programmable Logic

**Function:** Transfers packed samples from FPGA to DDR3 RAM without CPU involvement

**Configuration:**
```tcl
CONFIG.DMA_TYPE_SRC 2         # Source = AXI Stream (from cpack)
CONFIG.DMA_TYPE_DEST 0        # Destination = AXI4 Memory-Mapped (DDR3)
CONFIG.CYCLIC 0               # Non-cyclic (streaming mode)
CONFIG.DMA_DATA_WIDTH_SRC 64  # 64-bit samples (4× 16-bit channels)
```

**Operation:**

##### 1. **Descriptor Setup (Software)**
```c
// Linux driver sets up transfer
dma_addr = 0x1E000000;  // Physical DDR3 address
dma_length = 1048576;   // 1 MB buffer
dma_start();
```

##### 2. **Hardware Transfer (Autonomous)**
```
Clock cycle 0:   cpack outputs packed_fifo_wr[63:0] = {Q1, I1, Q0, I0}
Clock cycle 1:   DMA stores to DDR3[0x1E000000] ← {Q1, I1, Q0, I0}
Clock cycle 2:   cpack outputs next sample
Clock cycle 3:   DMA stores to DDR3[0x1E000008] ← next sample
...
Clock cycle N:   Transfer complete, interrupt to ARM CPU
```

**Memory Bandwidth:**
- Sample rate: 7.68 MSPS (after decimation)
- Data width: 64 bits = 8 bytes per sample
- Bandwidth: 7.68M × 8 = 61.44 MB/s per second
- DDR3 bandwidth: 4.2 GB/s (plenty of headroom)

**AXI4 Interface:**
- Master port: 64-bit data, burst transfers
- Connects to PS7 HP0 (High Performance port 0)
- Can burst up to 256 beats (2 KB per burst)

**FPGA Resources:**
- ~1,500 LUTs (state machine, address generation)
- ~2,000 FFs (AXI interface registers)
- No DSP or BRAM (pure control logic)

---

#### **Block 6: DDR3 RAM (PS Side)**

**Location:** Processing System hardware (not reprogrammable)

**Function:** Temporary storage for sample buffers

**Memory Map:**
```
0x00000000 - 0x3FFFFFFF: Full 1 GB DDR3 address space
0x00000000 - 0x00100000: Linux kernel (1 MB)
0x00100000 - 0x10000000: User space (256 MB)
0x10000000 - 0x20000000: Reserved (256 MB)
0x1E000000 - 0x20000000: DMA buffers (32 MB typical)
```

**Circular Buffer Scheme:**
```
Buffer 0: [0x1E000000 - 0x1E100000]  (1 MB)
Buffer 1: [0x1E100000 - 0x1E200000]  (1 MB)
Buffer 2: [0x1E200000 - 0x1E300000]  (1 MB)
Buffer 3: [0x1E300000 - 0x1E400000]  (1 MB)

DMA fills buffer while CPU reads previous buffer
```

---

#### **Block 7: libiio Kernel Driver**

**Location:** Linux kernel space

**Function:** Manages DMA, exposes samples to userspace via IIO subsystem

**Key Components:**

##### a. **IIO Device (`/dev/iio:device0`)**
- Character device for sample streaming
- Supports `read()` syscall for zero-copy access
- Provides mmap() for direct buffer access

##### b. **IIO Buffers (`/dev/iio:device0:buffer0`)**
```bash
# Enable buffer
echo 1 > /sys/bus/iio/devices/iio:device0/scan_elements/in_voltage0_i_en
echo 1 > /sys/bus/iio/devices/iio:device0/scan_elements/in_voltage0_q_en
echo 1 > /sys/bus/iio/devices/iio:device0/buffer/enable

# Read samples
cat /dev/iio:device0:buffer0 > samples.bin
```

##### c. **Network Backend (iiod daemon)**
```
Local:    libiio → /dev/iio:device0 → DMA buffers
Network:  libiio → TCP:30431 → iiod → /dev/iio:device0 → DMA
```

**Data Format in Kernel:**
```c
struct iio_sample {
    int16_t i0;  // In-phase, channel 0
    int16_t q0;  // Quadrature, channel 0
    int16_t i1;  // In-phase, channel 1
    int16_t q1;  // Quadrature, channel 1
} __attribute__((packed));
```

---

#### **Block 8: Userspace Application**

**Function:** Consumes samples via libiio API

**Example (Python with pylibiio):**
```python
import iio

# Connect to device
ctx = iio.Context('ip:192.168.1.10')
dev = ctx.find_device('cf-ad9361-lpc')

# Configure channels
rx0_i = dev.find_channel('voltage0_i', is_output=False)
rx0_q = dev.find_channel('voltage0_q', is_output=False)
rx0_i.enabled = True
rx0_q.enabled = True

# Create buffer
buffer = iio.Buffer(dev, 16384)  # 16K samples

# Read samples
while True:
    buffer.refill()
    data = buffer.read()  # Raw bytes
    # Process I/Q samples...
```

---

### TX Path (Software → Antenna)

```
Software → libiio → DDR3 RAM → DMA → tx_upack → tx_fir_interpolator → axi_ad9361 → LVDS → AD9361 → RF
  (App)   (Driver)  (Memory)  (Transfer) (Unpack)  (Upsample 8×)     (Serialize)  (12 diff)  (DAC) (Antenna)
```

#### **TX Block 1: tx_upack (util_upack2 - Channel Unpacker)**

**Function:** Separates packed stream from DMA into 4 channels

**Data Flow:**
```
Input from DMA:
  s_axis[63:0] = {Q1[15:0], I1[15:0], Q0[15:0], I0[15:0]}

Output channels:
  fifo_rd_data_0[15:0] → tx_fir_interpolator/data_in_0 (I0)
  fifo_rd_data_1[15:0] → tx_fir_interpolator/data_in_1 (Q0)
  fifo_rd_data_2[15:0] → axi_ad9361/dac_data_i1 (I1, direct)
  fifo_rd_data_3[15:0] → axi_ad9361/dac_data_q1 (Q1, direct)
```

**Note:** Same asymmetry as RX - channel 0 interpolated, channel 1 direct

---

#### **TX Block 2: tx_fir_interpolator (FIR Interpolation Filter)**

**Function:** Upsamples from low rate (7.68 MSPS) to AD9361 rate (61.44 MSPS)

**Why Interpolation?**
- Software generates samples at low rate (less CPU usage)
- AD9361 DAC needs high sample rate for wide bandwidth
- Interpolator inserts zeros + filters = smooth upsampling

**Stages:**
```
Input:  7.68 MSPS
        ↓ [Zero-insert + HB1] × 2
        15.36 MSPS
        ↓ [Zero-insert + HB2] × 2
        30.72 MSPS
        ↓ [Zero-insert + HB3] × 2
Output: 61.44 MSPS
```

**Filter Characteristics:**
- Same as RX decimator, but time-reversed
- Removes imaging artifacts from zero-insertion
- Maintains signal quality

---

#### **TX Block 3: axi_ad9361 (DAC Path)**

**Function:** Serializes parallel data to LVDS for AD9361

**Process:**
1. Receives `dac_data_i0[15:0]`, `dac_data_q0[15:0]` etc.
2. Converts SDR → DDR (double data rate)
3. Serializes to 6 LVDS lanes
4. Outputs `tx_data_out_p/n[5:0]`, `tx_clk_out_p/n`, `tx_frame_out_p/n`

---

#### **TX Block 4: AD9361 DAC**

**Function:** Converts digital samples to RF

**Process:**
1. **LVDS deserializer:** Recovers 12-bit samples from 6 lanes
2. **DAC (12-bit, up to 61.44 MSPS):** Digital-to-analog conversion
3. **Digital filters:** Interpolation, half-band filters
4. **Mixer:** Up-converts baseband I/Q to RF frequency
5. **PA (Power Amplifier):** Amplifies to output power (+0 dBm typ)

### 4. **FIR Filter - TX Interpolator (`tx_fir_interpolator`)**

**Purpose:** Digital upconversion (increases sample rate for transmission)

**Configuration:**
```tcl
Interpolation: 1:8 or 1:2
Input rate: 7.68 MSPS
Output rate: 61.44 MSPS (to AD9361)
```

**FPGA Resources Used:**
- ~5,000 LUTs
- 18× DSP48E1 slices
- Block RAM for coefficients

### 5. **Data Pack/Unpack (`util_cpack2`, `util_upack2`)**

**Purpose:** Convert between planar (separate I/Q channels) and interleaved formats

**Functions:**
- **cpack:** Combine RX1_I, RX1_Q, RX2_I, RX2_Q into single 64-bit stream for DMA
- **upack:** Split 64-bit DMA stream into separate TX1_I, TX1_Q, TX2_I, TX2_Q

**FPGA Resources Used (per module):**
- ~500 LUTs
- ~800 Flip-Flops

### 6. **AXI Interconnect Infrastructure**

**Purpose:** Communication between ARM cores and FPGA IP

**Components:**
- **AXI4-Lite:** Control/status registers (low bandwidth, simple)
- **AXI4 Full:** High-speed DMA transfers to DDR3
- **Clock domain crossings:** 100 MHz (AXI) ↔ 200 MHz (AD9361) ↔ 525 MHz (DDR3)
- **Address decoders:** Route register accesses to correct IP blocks

**FPGA Resources Used:**
- ~2,000 LUTs
- ~3,000 Flip-Flops
- Block RAM for FIFOs

### 7. **SPI Core (`axi_spi`)**

**Purpose:** SPI master for controlling external devices (e.g., AD9361 config)

**FPGA Resources Used:**
- ~300 LUTs
- ~200 Flip-Flops

### 8. **I2C Core (`axi_iic_main`)**

**Purpose:** I2C bus master (for EEPROM, sensors, etc.)

**FPGA Resources Used:**
- ~400 LUTs
- ~300 Flip-Flops

### 9. **System Management**

- **Clock generators (MMCM/PLL):** Generate 100 MHz, 200 MHz clocks from 50 MHz crystal
- **Reset logic:** Synchronized reset distribution
- **Interrupt controller:** Concatenate interrupts to ARM cores

**FPGA Resources Used:**
- 2× Clock Management Tiles (MMCM)
- ~500 LUTs

## Total FPGA Resource Usage

Based on Vivado synthesis reports for LibreSDR (estimated):

| Resource | Used | Available | Utilization | Notes |
|----------|------|-----------|-------------|-------|
| **Slice LUTs** | ~25,000 | 53,200 | **47%** | Logic gates |
| **Slice Registers (FF)** | ~30,000 | 106,400 | **28%** | Flip-flops |
| **Block RAM (36Kb)** | ~35 | 140 | **25%** | Internal memory |
| **DSP48E1 Slices** | ~40 | 220 | **18%** | Hardware multipliers |
| **BUFG (Global Clocks)** | 4 | 32 | **12%** | Clock networks |
| **MMCM/PLL** | 2 | 4 | **50%** | Clock generation |
| **I/O Pins** | ~60 | 200 | **30%** | Physical pins |

### Resource Breakdown by Module

```
Module                      LUTs    Registers  BRAM  DSP48E1
─────────────────────────────────────────────────────────────
axi_ad9361                  3,000   2,000      2     0
axi_dmac (RX)               1,500   2,000      4     0
axi_dmac (TX)               1,500   2,000      4     0
rx_fir_decimator            5,000   4,000      10    18
tx_fir_interpolator         5,000   4,000      10    18
util_cpack2                 500     800        1     0
util_upack2                 500     800        1     0
AXI Interconnect            2,000   3,000      3     0
axi_spi                     300     200        0     0
axi_iic_main                400     300        0     0
Clock/Reset logic           500     400        0     0
Misc (buffers, mux, etc.)   4,800   10,500     0     4
─────────────────────────────────────────────────────────────
TOTAL                       25,000  30,000     35    40
```

## What's Available for Custom Logic

### Free FPGA Resources

| Resource | Available | Percentage | What You Can Add |
|----------|-----------|------------|------------------|
| **LUTs** | ~28,000 | **53%** | Medium-complex custom logic |
| **Registers** | ~76,000 | **72%** | Large state machines, pipelines |
| **Block RAM** | ~105 blocks | **75%** | 3.8 Mb of fast internal memory |
| **DSP Slices** | ~180 | **82%** | ~180 multipliers or 90 MACs |
| **I/O Pins** | ~140 | **70%** | Additional external interfaces |

### What You Can Implement with Free Resources

#### 1. **Custom DSP Processing** (Excellent fit)

You have **180 unused DSP48E1 slices** - each can do:
- 18×25-bit multiplication + 48-bit accumulate in **1 clock cycle**
- 25×18-bit multiply-accumulate (MAC)
- Pattern detection, rounding, saturation

**Example applications:**
- **FFT accelerator:** 1024-point complex FFT using ~50 DSP slices
- **Digital filters:** Additional FIR/IIR filters (100+ taps each)
- **Correlator:** Real-time cross-correlation for passive radar (20-50 DSP slices)
- **Beamforming:** Phase/amplitude processing for phased arrays
- **Automatic Gain Control (AGC):** Hardware AGC with <1μs response
- **Frequency translation:** Digital mixer (NCO + multiplier)

#### 2. **Custom Protocol Decoders** (Good fit)

With 28,000 free LUTs:
- **LoRa demodulator:** Chirp detection + symbol decoding (~5,000 LUTs)
- **ADS-B decoder:** 1090 MHz aircraft transponder decoder (~3,000 LUTs)
- **FSK/PSK demodulator:** Hardware modem (~2,000 LUTs)
- **BPSK correlator:** GPS/satellite signal acquisition (~4,000 LUTs)
- **Ethernet MAC:** 100 Mbps or 1 Gbps Ethernet (~8,000 LUTs)

#### 3. **High-Speed Data Capture** (Excellent fit)

You have **3.8 Mb unused Block RAM** (~475 KB):
- **Deep sample buffers:** Store 100,000+ complex samples
- **Waveform generators:** Arbitrary waveform with 64K samples
- **Burst capture:** Trigger-based high-speed recording
- **Sample rate conversion:** Resample 20 MSPS → 30 MSPS with CIC filters

#### 4. **Real-Time Signal Analysis** (Good fit)

- **Spectrum analyzer:** Streaming FFT with averaging (~8,000 LUTs + 30 DSP)
- **Power detector:** Log-magnitude calculation (~1,000 LUTs + 5 DSP)
- **Peak detector:** Real-time peak finding with timestamps
- **Pulse detector:** Width/period measurement for radar signals
- **Frequency counter:** Precision frequency measurement (1 Hz resolution)

#### 5. **Additional Interfaces** (Good fit)

You have **140 unused I/O pins**:
- **JESD204B:** High-speed ADC/DAC interface (6.25 Gbps/lane)
- **LVDS data capture:** External ADC or logic analyzer
- **GPIO expansion:** Control external RF switches, filters
- **SPI/I2C/UART:** Additional sensors or peripherals
- **PWM outputs:** Motor control, LED control

#### 6. **Radar Signal Processing** (Excellent fit)

For passive radar (as discussed earlier):
- **Range-Doppler processor:** 2D FFT for target detection (~15,000 LUTs + 80 DSP)
- **Cross-ambiguity function (CAF):** Real-time correlation
- **CFAR detector:** Constant False Alarm Rate threshold
- **Target tracker:** Kalman filter for position estimation (~5,000 LUTs + 20 DSP)

#### 7. **Custom TDD Timing** (Simple)

The current design has placeholder TDD (Time Division Duplex):
```tcl
ad_connect axi_ad9361/tdd_sync GND  # Not used!
```

You can add:
- **TDD scheduler:** Precise TX/RX switching patterns (~1,000 LUTs)
- **Guard times:** Prevent TX-RX overlap
- **Synchronization:** GPS 1PPS or external timing

## How to Add Custom Logic

### Method 1: Modify HDL Source (Advanced)

1. **Edit `hdl/projects/libre/system_bd.tcl`:**
   ```tcl
   # Add custom IP core
   ad_ip_instance my_custom_module my_custom_inst
   ad_ip_parameter my_custom_inst CONFIG.PARAM_NAME value
   
   # Connect to data path
   ad_connect axi_ad9361/adc_data_i0 my_custom_inst/data_in
   ad_connect my_custom_inst/data_out rx_fir_decimator/data_in_0
   
   # Connect to AXI bus (for ARM control)
   ad_cpu_interconnect 0x43C00000 my_custom_inst
   ```

2. **Create Verilog/VHDL module in `hdl/library/`**

3. **Rebuild FPGA bitstream:** `make build/system_top.xsa`

### Method 2: Use Vivado Block Design (GUI)

1. Open Vivado: `vivado hdl/projects/libre/libre.xpr`
2. Open Block Design
3. Add IP from catalog (FFT, FIR Compiler, DDS, etc.)
4. Connect to existing blocks
5. Generate bitstream
6. Copy to LibreSDR and boot

### Method 3: Use High-Level Synthesis (HLS)

Write C/C++ code, compile to HDL:

```cpp
// custom_filter.cpp
#include "ap_int.h"

void custom_filter(ap_int<16> input[1024], ap_int<16> output[1024]) {
    #pragma HLS INTERFACE axis port=input
    #pragma HLS INTERFACE axis port=output
    #pragma HLS PIPELINE II=1
    
    for (int i = 0; i < 1024; i++) {
        output[i] = input[i] * 2;  // Example: simple gain
    }
}
```

Compile with Vitis HLS, import as IP core.

## Practical Examples

### Example 1: Add Hardware FFT for Spectrum Analyzer

**Resources needed:**
- 8,192-point FFT IP: ~6,000 LUTs, ~30 DSP48E1, ~20 BRAM
- **Fits easily in available resources!**

**Benefits:**
- Real-time spectrum with 2.44 kHz resolution @ 20 MSPS
- Offloads ARM CPU (can now do 100+ FFT/sec instead of 10)
- Lower latency (hardware FFT: 100μs, software: 10ms)

### Example 2: Add LoRa Demodulator

**Resources needed:**
- LoRa decoder: ~5,000 LUTs, ~10 DSP48E1, ~5 BRAM
- **Fits easily!**

**Benefits:**
- Decode LoRa packets in real-time while recording raw samples
- Multi-channel decoding (monitor 4+ LoRa channels simultaneously)
- Timestamps with μs precision

### Example 3: Add Passive Radar Correlator

**Resources needed:**
- Cross-correlator (131K samples): ~10,000 LUTs, ~50 DSP48E1, ~40 BRAM
- **Fits!**

**Benefits:**
- Real-time correlation at 20 MSPS
- Hardware acceleration: 1000× faster than ARM cores
- Process full 20 MHz bandwidth (software limited to ~2 MHz)

## Performance Considerations

### Clock Domains

The FPGA has multiple clock domains:

| Clock | Frequency | Domain | Use |
|-------|-----------|--------|-----|
| **sys_cpu_clk** | 100 MHz | AXI4-Lite | Register access |
| **sys_200m_clk** | 200 MHz | AD9361 interface | LVDS timing, delays |
| **l_clk** | Variable | AD9361 data | Sample clock (61.44, 30.72, 15.36 MHz) |
| **DDR3 clk** | 525 MHz | Memory | DDR3 interface (overclockable to 750 MHz) |

**When adding custom logic:**
- Use `l_clk` for sample-rate processing (matches AD9361)
- Use `sys_cpu_clk` for control registers
- Use clock domain crossings (CDC) with FIFOs when necessary

### Data Rates

Current data rates through FPGA:

| Path | Sample Rate | Data Rate | Bits/Sample |
|------|-------------|-----------|-------------|
| RX (2 channels) | 20 MSPS | 640 MB/s | 16-bit I + 16-bit Q × 2 |
| TX (2 channels) | 20 MSPS | 640 MB/s | Same |
| DMA to DDR3 | Burst | 2.1 GB/s peak | AXI4 64-bit @ 525 MHz |

**Your custom logic must keep up with 20 MSPS** (50 ns per sample).

At 200 MHz clock, you have **10 clock cycles** per sample for processing.

### Resource Trade-offs

| Goal | Resource to Use | Why |
|------|----------------|-----|
| **Speed** | DSP48E1 slices | 18×25 multiply in 1 cycle (200 MHz) |
| **Memory** | Block RAM | ~200× faster than DDR3 access |
| **Flexibility** | LUTs | Can implement any logic |
| **Low power** | DSP48E1 | 10× more energy-efficient than LUT multipliers |

## Common Pitfalls to Avoid

1. **Running out of Block RAM:**
   - Large FFTs consume lots of BRAM
   - Use DDR3 for buffers >100 KB
   - Reuse BRAM (e.g., share FFT buffers)

2. **Timing failures:**
   - Don't create combinational paths >10 LUTs deep
   - Pipeline arithmetic operations
   - Use proper clock domain crossings

3. **AXI4 protocol violations:**
   - Follow Xilinx AXI4 guidelines
   - Use AXI interconnect wizard
   - Test with AXI Protocol Checker

4. **Forgetting to rebuild Linux device tree:**
   - New IP cores need Linux drivers
   - Update `zynq-libre.dts` for new memory maps
   - Rebuild device tree blob

## Summary

### Current FPGA Usage (LibreSDR Stock)
- **~47% LUTs used** → 28,000 free
- **~28% Registers used** → 76,000 free
- **~25% BRAM used** → 3.8 Mb free
- **~18% DSP slices used** → 180 free

### You Can Add:
✅ **Real-time FFT spectrum analyzer** (6K LUTs, 30 DSP)
✅ **LoRa/FSK/PSK demodulator** (5K LUTs, 10 DSP)
✅ **Passive radar correlator** (10K LUTs, 50 DSP)
✅ **ADS-B aircraft decoder** (3K LUTs)
✅ **Custom digital filters** (2-5K LUTs, 10-20 DSP each)
✅ **Beamforming processor** (8K LUTs, 40 DSP)
✅ **Additional I/O interfaces** (140 pins available)

### You CANNOT Add (would exceed resources):
❌ **GPU-style processor** (needs millions of LUTs)
❌ **Full 4K video encoder** (needs 10× more BRAM)
❌ **Machine learning inference** (for large models - small CNNs might fit)

### Best Use Cases:
1. **DSP acceleration:** Hardware multipliers are free!
2. **Real-time processing:** Lower latency than software
3. **Parallel operations:** Process multiple channels simultaneously
4. **Protocol offload:** Decode packets while ARM handles network

The Zynq 7020 is a perfect fit for LibreSDR - enough resources for AD9361 interface + significant headroom for custom signal processing!

---

## Signal Chain Timing & Latency Analysis

### RX Path Total Latency (Antenna → Software)

| Stage | Latency | Description |
|-------|---------|-------------|
| **AD9361 RF → ADC** | 500 ns | LNA + Mixer + ADC pipeline |
| **AD9361 Digital Filters** | 2.1 μs | 128-tap FIR decimator @ 61.44 MSPS |
| **LVDS Transmission** | 8 ns | PCB trace (20 cm @ 15 cm/ns) |
| **axi_ad9361 Deserializer** | 40 ns | IDELAY + clock recovery (5 clocks @ 123 MHz) |
| **rx_fir_decimator** | 1.7 μs | 129 taps @ 61.44 MSPS input |
| **cpack Buffer** | 65 ns | 8-sample FIFO @ 123 MHz |
| **DMA Transfer** | 200 ns | AXI4 burst write to DDR3 |
| **DDR3 Write** | 50 ns | Write latency |
| **CPU Cache Fetch** | 100 ns | ARM reads DMA buffer |
| **TOTAL (HW only)** | **~4.8 μs** | From antenna to DDR3 RAM |

### TX Path Total Latency (Software → Antenna)

| Stage | Latency | Description |
|-------|---------|-------------|
| **Software → DDR3** | 100 ns | memcpy() to DMA buffer |
| **DMA Read** | 200 ns | AXI4 burst read from DDR3 |
| **tx_upack** | 40 ns | Unpacking logic |
| **tx_fir_interpolator** | 680 ns | 129 taps @ 7.68 MSPS input |
| **axi_ad9361 Serializer** | 40 ns | Parallel → DDR → LVDS |
| **LVDS Transmission** | 8 ns | PCB trace |
| **AD9361 Digital Filters** | 2.1 μs | 128-tap interpolator |
| **AD9361 DAC → RF** | 500 ns | Mixer + PA delay |
| **TOTAL (HW only)** | **~3.7 μs** | From DDR3 to antenna |

### Clock Domains Reference

| Clock | Frequency | Source | Purpose |
|-------|-----------|--------|---------|
| sys_cpu_clk | 100 MHz | PS7 FCLK_CLK0 | AXI control bus |
| sys_200m_clk | 200 MHz | PS7 FCLK_CLK1 | IDELAY calibration |
| l_clk | 122.88 MHz | AD9361 LVDS | Data path (RX/TX) |
| ARM CPU | 750 MHz | PS7 ARM PLL | Cortex-A9 cores |
| DDR3 | 525 MHz | PS7 DDR PLL | Memory controller |

