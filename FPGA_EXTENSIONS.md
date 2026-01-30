# FPGA Custom DSP Extensions Guide

## Overview

This guide explains how to inject custom DSP elements (filters, spectrum analyzers, custom processing blocks) into the LibreSDR FPGA design and control them from software.

## Current LibreSDR Signal Flow

```
AD9361 (LVDS) → util_ad9361_adc_pack → axi_ad9361 → axi_dmac → PS DDR3 → Software
                                          ↑                           ↓
                                     [INJECT HERE]              DMA to IIO
```

**Recommended injection point**: Between `axi_ad9361` and `axi_dmac` (after AD9361 interface, before DMA)

## Architecture Layers

### 1. FPGA Layer (HDL)
- Custom Verilog/VHDL modules
- AXI Stream interfaces for data path
- AXI-Lite registers for control
- Memory-mapped control registers

### 2. Linux Kernel Layer
- Device tree entries
- IIO device attributes
- Kernel module (optional)
- UIO (Userspace I/O) driver

### 3. Software Layer
- libiio controls
- Direct register access
- GNU Radio integration
- Python/C++ applications

---

## Method 1: Create Custom IP with Bypass Control

### Step 1: Create Custom Verilog Module

Example: Switchable FIR filter

```verilog
// hdl/library/custom_filter/custom_filter.v
module custom_filter #(
    parameter DATA_WIDTH = 16,
    parameter NUM_CHANNELS = 4  // I0, Q0, I1, Q1 for 2T2R
) (
    input clk,
    input resetn,
    
    // AXI Stream input (from AD9361)
    input [DATA_WIDTH*NUM_CHANNELS-1:0] s_axis_tdata,
    input s_axis_tvalid,
    output s_axis_tready,
    
    // AXI Stream output (to DMA)
    output [DATA_WIDTH*NUM_CHANNELS-1:0] m_axis_tdata,
    output m_axis_tvalid,
    input m_axis_tready,
    
    // AXI-Lite control registers
    input [31:0] filter_enable,     // 0=bypass, 1=active
    input [31:0] filter_config,     // Filter type/parameters
    input [31:0] filter_coeff_addr, // Coefficient loading
    input [31:0] filter_coeff_data
);
    
    // Bypass mux (software-controlled)
    reg bypass_mode;
    always @(posedge clk) begin
        if (!resetn)
            bypass_mode <= 1'b1;  // Default: bypass
        else
            bypass_mode <= !filter_enable;
    end
    
    // Data path selection
    wire [DATA_WIDTH*NUM_CHANNELS-1:0] filtered_data;
    assign m_axis_tdata = bypass_mode ? s_axis_tdata : filtered_data;
    assign m_axis_tvalid = s_axis_tvalid;
    assign s_axis_tready = m_axis_tready;
    
    // FIR filter implementation
    // ... (use Xilinx FIR Compiler IP or custom implementation)
    
endmodule
```

### Step 2: Create AXI-Lite Register Interface

```verilog
// hdl/library/custom_filter/custom_filter_regs.v
module custom_filter_regs #(
    parameter BASE_ADDR = 32'h79020000
) (
    input s_axi_aclk,
    input s_axi_aresetn,
    
    // AXI-Lite interface (connected to PS7)
    input [31:0] s_axi_awaddr,
    input s_axi_awvalid,
    output s_axi_awready,
    input [31:0] s_axi_wdata,
    input s_axi_wvalid,
    output s_axi_wready,
    output [1:0] s_axi_bresp,
    output s_axi_bvalid,
    input s_axi_bready,
    input [31:0] s_axi_araddr,
    input s_axi_arvalid,
    output s_axi_arready,
    output [31:0] s_axi_rdata,
    output [1:0] s_axi_rresp,
    output s_axi_rvalid,
    input s_axi_rready,
    
    // Register outputs to filter core
    output reg [31:0] filter_enable,
    output reg [31:0] filter_config,
    output reg [31:0] filter_coeff_addr,
    output reg [31:0] filter_coeff_data
);

// Register map:
// 0x00: FILTER_ENABLE  (bit 0: 0=bypass, 1=active)
// 0x04: FILTER_CONFIG  (filter parameters)
// 0x08: COEFF_ADDR     (coefficient index)
// 0x0C: COEFF_DATA     (coefficient value)

// AXI-Lite register implementation
// ... (standard AXI-Lite slave logic)

endmodule
```

### Step 3: Integrate into system_bd.tcl

```tcl
# In plutosdr-fw_0.38_libre/hdl/projects/libre/system_bd.tcl

# Add after axi_ad9361 instance creation (around line 200)

# Create custom filter IP instance
ad_ip_instance custom_filter custom_filter_inst
ad_ip_parameter custom_filter_inst CONFIG.DATA_WIDTH 16
ad_ip_parameter custom_filter_inst CONFIG.NUM_CHANNELS 4

# Connect to data path - intercept between AD9361 and DMA
# Find the original connections and replace with:

# Original: axi_ad9361 -> axi_ad9361_adc_dma
# New: axi_ad9361 -> custom_filter -> axi_ad9361_adc_dma

ad_connect axi_ad9361/adc_data_i0 custom_filter_inst/s_axis_tdata
ad_connect axi_ad9361/adc_valid_i0 custom_filter_inst/s_axis_tvalid
ad_connect custom_filter_inst/s_axis_tready axi_ad9361/adc_ready_i0

ad_connect custom_filter_inst/m_axis_tdata axi_ad9361_adc_dma/fifo_wr_din
ad_connect custom_filter_inst/m_axis_tvalid axi_ad9361_adc_dma/fifo_wr_en
ad_connect axi_ad9361_adc_dma/fifo_wr_overflow custom_filter_inst/m_axis_tready

# Create AXI-Lite control interface
ad_ip_instance axi_lite_ipif custom_filter_ctrl
ad_ip_parameter custom_filter_ctrl CONFIG.C_BASEADDR 0x79020000
ad_ip_parameter custom_filter_ctrl CONFIG.C_HIGHADDR 0x7902FFFF

# Connect control registers to filter
ad_connect custom_filter_ctrl/filter_enable custom_filter_inst/filter_enable
ad_connect custom_filter_ctrl/filter_config custom_filter_inst/filter_config

# Connect to PS7 AXI bus (for software access)
ad_cpu_interconnect 0x79020000 custom_filter_ctrl

# Add address to device tree generation
ad_mem_hp0_interconnect sys_cpu_clk custom_filter_ctrl/s_axi
```

---

## Method 2: Non-Intrusive Spectrum Monitor (Parallel Tap)

For monitoring/analysis without affecting data path:

### Spectrum Monitor Module

```verilog
// hdl/library/spectrum_monitor/spectrum_monitor.v
module spectrum_monitor #(
    parameter FFT_SIZE = 1024,
    parameter DATA_WIDTH = 16
) (
    input clk,
    input resetn,
    
    // Tap from ADC data path (non-blocking)
    input [DATA_WIDTH-1:0] adc_data_i,
    input [DATA_WIDTH-1:0] adc_data_q,
    input adc_valid,
    
    // AXI-Lite for reading FFT results
    input [31:0] s_axi_araddr,
    input s_axi_arvalid,
    output s_axi_arready,
    output [31:0] s_axi_rdata,
    output [1:0] s_axi_rresp,
    output s_axi_rvalid,
    input s_axi_rready,
    
    // Control registers
    input [31:0] fft_enable,
    input [31:0] averaging_count
);

// Instantiate Xilinx FFT IP
xfft_0 fft_core (
    .aclk(clk),
    .s_axis_data_tdata({adc_data_q, adc_data_i}),
    .s_axis_data_tvalid(adc_valid & fft_enable[0]),
    .m_axis_data_tdata(fft_out),
    .m_axis_data_tvalid(fft_valid)
);

// Magnitude calculation
wire [31:0] magnitude;
assign magnitude = fft_out[15:0] * fft_out[15:0] + 
                   fft_out[31:16] * fft_out[31:16];

// Dual-port RAM for bin storage (software can read)
// ... RAM implementation ...

endmodule
```

### Integration (Non-Blocking)

```tcl
# Tap into data path without modifying it
ad_ip_instance spectrum_monitor spectrum_mon

ad_connect axi_ad9361/adc_data_i0 spectrum_mon/adc_data_i
ad_connect axi_ad9361/adc_data_q0 spectrum_mon/adc_data_q
ad_connect axi_ad9361/adc_valid_i0 spectrum_mon/adc_valid

# Separate AXI address for spectrum readout
ad_cpu_interconnect 0x79030000 spectrum_mon/s_axi
```

---

## Software Control Methods

### Option A: IIO Device Attributes (Recommended for Production)

#### 1. Device Tree Entry

```dts
// linux/arch/arm/boot/dts/zynq-libre.dts or zynq-libre.dtsi

&axi {
    custom_filter: filter@79020000 {
        compatible = "adi,custom-filter-1.0";
        reg = <0x79020000 0x10000>;
        clocks = <&clkc 15>;
        clock-names = "s_axi_aclk";
    };
    
    spectrum_mon: spectrum@79030000 {
        compatible = "adi,spectrum-monitor-1.0";
        reg = <0x79030000 0x10000>;
        clocks = <&clkc 15>;
        clock-names = "s_axi_aclk";
    };
};

// Link to AD9361 device
&axi_ad9361 {
    custom-filter = <&custom_filter>;
    spectrum-monitor = <&spectrum_mon>;
};
```

#### 2. Kernel Driver Extension

Extend AD9361 driver or create separate module:

```c
// buildroot/package/ad9361-custom/ad9361-custom.c

#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/io.h>

#define FILTER_ENABLE_REG   0x00
#define FILTER_CONFIG_REG   0x04

struct custom_filter_dev {
    void __iomem *regs;
    struct device *dev;
};

static ssize_t filter_enable_show(struct device *dev,
                                   struct device_attribute *attr,
                                   char *buf)
{
    struct custom_filter_dev *filter = dev_get_drvdata(dev);
    u32 val = readl(filter->regs + FILTER_ENABLE_REG);
    return sprintf(buf, "%u\n", val);
}

static ssize_t filter_enable_store(struct device *dev,
                                    struct device_attribute *attr,
                                    const char *buf, size_t len)
{
    struct custom_filter_dev *filter = dev_get_drvdata(dev);
    u32 val;
    
    if (kstrtou32(buf, 0, &val))
        return -EINVAL;
    
    writel(val, filter->regs + FILTER_ENABLE_REG);
    return len;
}

static DEVICE_ATTR_RW(filter_enable);

static struct attribute *filter_attrs[] = {
    &dev_attr_filter_enable.attr,
    NULL,
};

ATTRIBUTE_GROUPS(filter);

static int custom_filter_probe(struct platform_device *pdev)
{
    struct custom_filter_dev *filter;
    struct resource *res;
    
    filter = devm_kzalloc(&pdev->dev, sizeof(*filter), GFP_KERNEL);
    if (!filter)
        return -ENOMEM;
    
    res = platform_get_resource(pdev, IORESOURCE_MEM, 0);
    filter->regs = devm_ioremap_resource(&pdev->dev, res);
    if (IS_ERR(filter->regs))
        return PTR_ERR(filter->regs);
    
    filter->dev = &pdev->dev;
    platform_set_drvdata(pdev, filter);
    
    return sysfs_create_groups(&pdev->dev.kobj, filter_groups);
}

static const struct of_device_id custom_filter_of_match[] = {
    { .compatible = "adi,custom-filter-1.0", },
    { }
};
MODULE_DEVICE_TABLE(of, custom_filter_of_match);

static struct platform_driver custom_filter_driver = {
    .probe = custom_filter_probe,
    .driver = {
        .name = "custom-filter",
        .of_match_table = custom_filter_of_match,
    },
};
module_platform_driver(custom_filter_driver);
```

#### 3. Software Access (Python with libiio)

```python
import iio

# Access filter control
ctx = iio.Context('ip:192.168.1.10')
filter_dev = ctx.find_device('custom-filter')

# Enable filter
filter_dev.debug_attrs['filter_enable'].value = '1'

# Read status
status = filter_dev.debug_attrs['filter_enable'].value
print(f"Filter enabled: {status}")
```

### Option B: Direct Register Access (Quick Development/Testing)

#### Python Example

```python
import mmap
import struct
import os

class FPGAControl:
    def __init__(self):
        self.FILTER_BASE = 0x79020000
        self.SPECTRUM_BASE = 0x79030000
        self.PAGE_SIZE = 4096
        
        # Open /dev/mem
        self.fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        
        # Memory map control regions
        self.filter_mem = mmap.mmap(
            self.fd, self.PAGE_SIZE,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=self.FILTER_BASE
        )
        
        self.spectrum_mem = mmap.mmap(
            self.fd, self.PAGE_SIZE,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=self.SPECTRUM_BASE
        )
    
    def set_filter_enable(self, enable):
        """Enable/disable custom filter"""
        self.filter_mem[0:4] = struct.pack("I", 1 if enable else 0)
    
    def get_filter_enable(self):
        """Read filter enable status"""
        return struct.unpack("I", self.filter_mem[0:4])[0]
    
    def set_filter_config(self, config):
        """Configure filter parameters"""
        self.filter_mem[4:8] = struct.pack("I", config)
    
    def read_spectrum_bin(self, bin_index):
        """Read FFT magnitude for specific bin"""
        # Write bin address
        self.spectrum_mem[0x10:0x14] = struct.pack("I", bin_index)
        # Read magnitude
        return struct.unpack("I", self.spectrum_mem[0x14:0x18])[0]
    
    def get_spectrum(self, num_bins=1024):
        """Read full spectrum"""
        spectrum = []
        for i in range(num_bins):
            spectrum.append(self.read_spectrum_bin(i))
        return spectrum
    
    def __del__(self):
        self.filter_mem.close()
        self.spectrum_mem.close()
        os.close(self.fd)

# Usage
fpga = FPGAControl()

# Enable filter
fpga.set_filter_enable(True)
print(f"Filter enabled: {fpga.get_filter_enable()}")

# Read spectrum
spectrum = fpga.get_spectrum(1024)
print(f"Peak bin: {spectrum.index(max(spectrum))}")
```

#### C++ Example

```cpp
#include <iostream>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <cstdint>

class FPGAControl {
private:
    int fd;
    volatile uint32_t* filter_regs;
    volatile uint32_t* spectrum_regs;
    
    static constexpr uint32_t FILTER_BASE = 0x79020000;
    static constexpr uint32_t SPECTRUM_BASE = 0x79030000;
    static constexpr size_t MAP_SIZE = 4096;
    
public:
    FPGAControl() {
        fd = open("/dev/mem", O_RDWR | O_SYNC);
        if (fd < 0) {
            throw std::runtime_error("Cannot open /dev/mem");
        }
        
        filter_regs = static_cast<volatile uint32_t*>(
            mmap(NULL, MAP_SIZE, PROT_READ | PROT_WRITE,
                 MAP_SHARED, fd, FILTER_BASE)
        );
        
        spectrum_regs = static_cast<volatile uint32_t*>(
            mmap(NULL, MAP_SIZE, PROT_READ | PROT_WRITE,
                 MAP_SHARED, fd, SPECTRUM_BASE)
        );
    }
    
    void setFilterEnable(bool enable) {
        filter_regs[0] = enable ? 1 : 0;
    }
    
    bool getFilterEnable() {
        return filter_regs[0] != 0;
    }
    
    void setFilterConfig(uint32_t config) {
        filter_regs[1] = config;
    }
    
    uint32_t readSpectrumBin(uint32_t bin) {
        spectrum_regs[4] = bin;  // Address register
        return spectrum_regs[5];  // Data register
    }
    
    ~FPGAControl() {
        munmap((void*)filter_regs, MAP_SIZE);
        munmap((void*)spectrum_regs, MAP_SIZE);
        close(fd);
    }
};

int main() {
    FPGAControl fpga;
    
    // Enable filter
    fpga.setFilterEnable(true);
    std::cout << "Filter enabled: " << fpga.getFilterEnable() << std::endl;
    
    // Read spectrum peak
    uint32_t peak = 0;
    int peak_bin = 0;
    for (int i = 0; i < 1024; i++) {
        uint32_t mag = fpga.readSpectrumBin(i);
        if (mag > peak) {
            peak = mag;
            peak_bin = i;
        }
    }
    std::cout << "Peak at bin " << peak_bin << ": " << peak << std::endl;
    
    return 0;
}
```

### Option C: UIO (Userspace I/O)

#### Device Tree

```dts
filter_uio: uio@79020000 {
    compatible = "generic-uio";
    reg = <0x79020000 0x10000>;
    interrupt-parent = <&intc>;
    interrupts = <0 57 4>;  // Optional: for interrupt support
};

spectrum_uio: uio@79030000 {
    compatible = "generic-uio";
    reg = <0x79030000 0x10000>;
};
```

#### Software Access

```c
#include <stdio.h>
#include <fcntl.h>
#include <sys/mman.h>
#include <stdint.h>

int main() {
    int fd = open("/dev/uio0", O_RDWR);
    if (fd < 0) {
        perror("Cannot open /dev/uio0");
        return 1;
    }
    
    // Map registers
    volatile uint32_t* regs = mmap(NULL, 0x10000,
                                    PROT_READ | PROT_WRITE,
                                    MAP_SHARED, fd, 0);
    
    // Enable filter
    regs[0] = 1;
    
    // Configure
    regs[1] = 0x12345678;
    
    printf("Filter enabled: %u\n", regs[0]);
    
    munmap((void*)regs, 0x10000);
    close(fd);
    return 0;
}
```

---

## GNU Radio Integration

### Custom GNU Radio Block

```python
# gr-libresdr/python/libresdr/filter_control.py
from gnuradio import gr
import pmt

class filter_control(gr.sync_block):
    def __init__(self, fpga_control_addr=0x79020000):
        gr.sync_block.__init__(
            self,
            name="LibreSDR Filter Control",
            in_sig=None,
            out_sig=None
        )
        
        self.fpga_addr = fpga_control_addr
        self.setup_mem_map()
        
        # Register message port
        self.message_port_register_in(pmt.intern("control"))
        self.set_msg_handler(pmt.intern("control"), self.handle_control)
    
    def setup_mem_map(self):
        import mmap
        import os
        fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
        self.mem = mmap.mmap(fd, 4096, 
                             mmap.MAP_SHARED,
                             mmap.PROT_READ | mmap.PROT_WRITE,
                             offset=self.fpga_addr)
    
    def handle_control(self, msg):
        if pmt.is_dict(msg):
            if pmt.dict_has_key(msg, pmt.intern("enable")):
                enable = pmt.to_long(pmt.dict_ref(
                    msg, pmt.intern("enable"), pmt.from_long(0)
                ))
                self.set_filter_enable(enable)
    
    def set_filter_enable(self, enable):
        import struct
        self.mem[0:4] = struct.pack("I", 1 if enable else 0)
```

### GRC Block XML

```xml
<!-- gr-libresdr/grc/libresdr_filter_control.block.yml -->
id: libresdr_filter_control
label: LibreSDR Filter Control

category: '[LibreSDR]'

parameters:
- id: fpga_addr
  label: FPGA Address
  dtype: int
  default: '0x79020000'

inputs:
- domain: message
  id: control
  optional: true

templates:
  imports: from gnuradio import libresdr
  make: libresdr.filter_control(${fpga_addr})
  callbacks:
  - set_filter_enable(${enable})

documentation: |-
  Control LibreSDR FPGA custom filter module.
  Send dict messages to 'control' port with 'enable' key.

file_format: 1
```

---

## Practical Examples

### Example 1: Bypass-able DC Blocker

Simple high-pass filter to remove DC offset:

```verilog
module dc_blocker #(
    parameter WIDTH = 16,
    parameter ALPHA = 16'h7FFF  // 0.9999 in Q15
) (
    input clk,
    input resetn,
    input [WIDTH-1:0] din,
    input din_valid,
    output reg [WIDTH-1:0] dout,
    output dout_valid,
    input bypass
);

reg signed [WIDTH-1:0] x_prev, y_prev;
wire signed [WIDTH-1:0] y;

// y[n] = x[n] - x[n-1] + alpha * y[n-1]
assign y = din - x_prev + ((ALPHA * y_prev) >>> 15);

always @(posedge clk) begin
    if (!resetn) begin
        x_prev <= 0;
        y_prev <= 0;
        dout <= 0;
    end else if (din_valid) begin
        x_prev <= din;
        y_prev <= y;
        dout <= bypass ? din : y;
    end
end

assign dout_valid = din_valid;

endmodule
```

### Example 2: Power Detector

Monitor signal power in FPGA:

```verilog
module power_detector (
    input clk,
    input resetn,
    input [15:0] i_data,
    input [15:0] q_data,
    input valid,
    output reg [31:0] power_avg,
    input [15:0] averaging_length  // Number of samples to average
);

wire [31:0] instant_power = i_data * i_data + q_data * q_data;
reg [47:0] accumulator;
reg [15:0] sample_count;

always @(posedge clk) begin
    if (!resetn) begin
        accumulator <= 0;
        sample_count <= 0;
        power_avg <= 0;
    end else if (valid) begin
        accumulator <= accumulator + instant_power;
        sample_count <= sample_count + 1;
        
        if (sample_count >= averaging_length) begin
            power_avg <= accumulator >> $clog2(averaging_length);
            accumulator <= 0;
            sample_count <= 0;
        end
    end
end

endmodule
```

---

## Available Analog Devices IP Blocks

LibreSDR's HDL repository includes ready-to-use blocks in `hdl/library/`:

### Useful Existing IP:
- **util_cpack2** - Pack/unpack IQ data
- **util_upack2** - Unpack compressed data
- **util_fir_dec** - Decimating FIR filter
- **util_fir_int** - Interpolating FIR filter
- **util_cic_decim** - CIC decimation filter
- **axi_dmac** - DMA controller (study for reference)
- **axi_ad9361** - AD9361 interface (study signal flow)

### How to Use Existing IP:

```tcl
# Example: Add decimation filter
ad_ip_instance util_fir_dec fir_decimator
ad_ip_parameter fir_decimator CONFIG.NUM_CHANNELS 2
ad_ip_parameter fir_decimator CONFIG.DECIMATION_RATIO 2

# Insert in data path
ad_connect axi_ad9361/adc_data fir_decimator/s_axis
ad_connect fir_decimator/m_axis axi_dmac/fifo_wr
```

---

## Testing Workflow

### 1. Quick Test with devmem (Root Access Required)

```bash
# SSH to LibreSDR
ssh root@192.168.1.10

# Test filter enable register
devmem 0x79020000 32 0x00000001  # Enable
devmem 0x79020000 32              # Read back

# Test spectrum monitor
for i in $(seq 0 1023); do
    devmem 0x79030010 32 $i        # Set bin address
    devmem 0x79030014 32           # Read magnitude
done
```

### 2. Python Test Script

```python
#!/usr/bin/env python3
import sys
sys.path.append('/root')

from fpga_control import FPGAControl
import numpy as np
import matplotlib.pyplot as plt

# Initialize control
fpga = FPGAControl()

# Test filter bypass
print("Testing filter bypass...")
fpga.set_filter_enable(False)
assert fpga.get_filter_enable() == 0, "Bypass failed"
print("✓ Bypass working")

# Test filter enable
fpga.set_filter_enable(True)
assert fpga.get_filter_enable() == 1, "Enable failed"
print("✓ Enable working")

# Read spectrum
print("Reading spectrum...")
spectrum = fpga.get_spectrum(1024)
spectrum_db = 10 * np.log10(np.array(spectrum) + 1e-10)

# Plot
plt.figure(figsize=(12, 6))
plt.plot(spectrum_db)
plt.xlabel('FFT Bin')
plt.ylabel('Magnitude (dB)')
plt.title('LibreSDR FPGA Spectrum Monitor')
plt.grid(True)
plt.savefig('/tmp/spectrum.png')
print("✓ Spectrum saved to /tmp/spectrum.png")
```

### 3. GNU Radio Flowgraph Test

```python
#!/usr/bin/env python3
from gnuradio import gr, blocks, iio
from gnuradio import libresdr  # Your custom module

class test_flowgraph(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self)
        
        # LibreSDR source
        self.sdr = iio.fmcomms2_source_fc32(
            'ip:192.168.1.10',
            [True, True],  # Both channels
            32768
        )
        self.sdr.set_params(2400000000, 20000000, 20000000, True, True, True, 'slow_attack', 64.0, 'manual', 64.0, 'A_BALANCED', '', True)
        
        # FPGA filter control
        self.filter_ctrl = libresdr.filter_control()
        
        # File sink for testing
        self.sink = blocks.file_sink(gr.sizeof_gr_complex, '/tmp/sdr_output.dat')
        
        # Connect
        self.connect((self.sdr, 0), self.sink)
        
    def enable_filter(self):
        msg = pmt.dict_add(pmt.make_dict(), 
                           pmt.intern("enable"), 
                           pmt.from_long(1))
        self.filter_ctrl.to_basic_block()._post(pmt.intern("control"), msg)

if __name__ == '__main__':
    tb = test_flowgraph()
    tb.start()
    
    # Toggle filter during capture
    import time
    time.sleep(2)
    tb.enable_filter()
    time.sleep(2)
    
    tb.stop()
    tb.wait()
```

---

## Build Process After HDL Changes

```bash
cd /home/arsatyants/code/libresdr/plutosdr-fw_0.38_libre

# Clean previous build
export VIVADO_SETTINGS=/media/arsatyants/vivado/vivado/Vivado/2022.2/settings64.sh
export TARGET=libre
make clean

# Rebuild with new FPGA design
make

# Generate SD card image
make sdimg

# Or use automated script
./FULL_BUILD.sh
```

**Build time**: ~30-60 minutes depending on FPGA design complexity.

---

## Memory Map Reference

Reserve address space for custom IP in LibreSDR:

| Base Address | Size   | Function                  |
|--------------|--------|---------------------------|
| 0x79020000   | 64KB   | Custom Filter Control     |
| 0x79030000   | 64KB   | Spectrum Monitor          |
| 0x79040000   | 64KB   | Reserved for future use   |
| 0x79050000   | 64KB   | Reserved for future use   |

**Note**: Avoid conflicts with existing peripherals. Check current memory map:
```bash
ssh root@192.168.1.10 'cat /proc/iomem | grep axi'
```

---

## Resource Estimation

FPGA resource usage for typical custom blocks (Zynq 7020):

| Block Type           | LUTs  | FFs   | DSP48 | BRAM |
|----------------------|-------|-------|-------|------|
| Simple Bypass Mux    | <100  | <50   | 0     | 0    |
| FIR Filter (32-tap)  | 2K    | 1K    | 4     | 2    |
| 1024-pt FFT          | 8K    | 5K    | 20    | 16   |
| Power Detector       | <500  | <200  | 4     | 0    |
| DC Blocker           | <200  | <100  | 0     | 0    |

**Zynq 7020 Total Resources**: 53,200 LUTs, 106,400 FFs, 220 DSP48, 140 BRAM (36Kb)

---

## Common Pitfalls

1. **Clock Domain Crossing**: Ensure proper CDC if using different clocks
2. **AXI Stream Backpressure**: Always implement `tready` properly
3. **Register Read-Back**: Implement read-back for all writable registers
4. **Reset Handling**: Synchronize resets to clock domain
5. **Timing Closure**: Complex filters may need pipelining for 200+ MHz operation
6. **Memory Access**: Use cached memory mapping for high-speed register access

---

## Additional Resources

- **Xilinx IP Documentation**: Check Vivado IP Catalog for built-in blocks
- **AD9361 Register Map**: For direct transceiver control
- **AXI Protocol Spec**: Understanding AXI4-Stream and AXI4-Lite
- **HDL Reference**: Study `hdl/library/axi_ad9361/` for integration examples

---

## Support & Development

For questions about extending LibreSDR FPGA functionality:
1. Study existing IP in `hdl/library/`
2. Check PlutoSDR forums for similar modifications
3. Test with devmem before kernel integration
4. Use ILA (Integrated Logic Analyzer) for debugging signal flow

**Next Steps**: 
- Start with simple bypass mux to verify software control
- Add basic filtering/processing
- Integrate spectrum analysis for monitoring
- Optimize for performance and resource usage
