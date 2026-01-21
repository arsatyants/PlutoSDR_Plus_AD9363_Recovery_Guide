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
