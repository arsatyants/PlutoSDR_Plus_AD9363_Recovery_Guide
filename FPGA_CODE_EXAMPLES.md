# FPGA Code Examples for LibreSDR

This guide shows FPGA code from simplest to more complex, with real examples you can add to LibreSDR.

## Example 1: Simple Gain Control (Easiest)

**What it does:** Multiply IQ samples by a programmable gain value

### Verilog Code (`simple_gain.v`)

```verilog
// Simple digital gain control
// Multiplies input samples by a gain factor

module simple_gain (
    input wire clk,              // Clock input
    input wire reset,            // Active-high reset
    
    // Input samples (16-bit signed I and Q)
    input wire [15:0] din_i,     // Input I channel
    input wire [15:0] din_q,     // Input Q channel
    input wire din_valid,        // Input data valid
    
    // Gain control register (8-bit, from ARM CPU)
    input wire [7:0] gain,       // Gain: 0-255 (128 = unity gain)
    
    // Output samples
    output reg [15:0] dout_i,    // Output I channel
    output reg [15:0] dout_q,    // Output Q channel
    output reg dout_valid        // Output data valid
);

// Internal signals for multiplication
wire signed [23:0] mult_i;  // 16-bit × 8-bit = 24-bit
wire signed [23:0] mult_q;

// Multiply input by gain
assign mult_i = $signed(din_i) * $signed(gain);
assign mult_q = $signed(din_q) * $signed(gain);

// Register outputs (pipeline stage)
always @(posedge clk) begin
    if (reset) begin
        dout_i <= 16'd0;
        dout_q <= 16'd0;
        dout_valid <= 1'b0;
    end else begin
        // Scale back down (divide by 128)
        dout_i <= mult_i[23:7];  // Keep upper 17 bits, drop lowest 7
        dout_q <= mult_q[23:7];
        dout_valid <= din_valid;
    end
end

endmodule
```

**Complexity:** 🟢 Very Easy
- **Resources:** ~100 LUTs, 2 DSP48E1 slices
- **What you learned:** Basic Verilog syntax, registers, multiplication
- **Useful for:** Software-controlled gain (better than AD9361 AGC)

---

## Example 2: Moving Average Filter (Easy)

**What it does:** Smooth samples by averaging last N values (reduces noise)

### Verilog Code (`moving_average.v`)

```verilog
// Moving average filter (4-tap)
// Averages last 4 samples to reduce noise

module moving_average (
    input wire clk,
    input wire reset,
    
    input wire [15:0] din,       // Input sample
    input wire din_valid,
    
    output reg [15:0] dout,      // Output sample
    output reg dout_valid
);

// Shift register for last 4 samples
reg [15:0] samples [0:3];
integer i;

// Sum accumulator
wire [17:0] sum;  // 16-bit samples + 2 bits for 4 samples

// Calculate sum of all 4 samples
assign sum = samples[0] + samples[1] + samples[2] + samples[3];

// Main logic
always @(posedge clk) begin
    if (reset) begin
        for (i = 0; i < 4; i = i + 1) begin
            samples[i] <= 16'd0;
        end
        dout <= 16'd0;
        dout_valid <= 1'b0;
    end else if (din_valid) begin
        // Shift samples
        samples[0] <= din;
        samples[1] <= samples[0];
        samples[2] <= samples[1];
        samples[3] <= samples[2];
        
        // Output average (divide by 4 = shift right 2 bits)
        dout <= sum[17:2];
        dout_valid <= 1'b1;
    end else begin
        dout_valid <= 1'b0;
    end
end

endmodule
```

**Complexity:** 🟢 Easy
- **Resources:** ~200 LUTs, 64 Flip-Flops
- **What you learned:** Shift registers, averaging
- **Useful for:** Noise reduction, anti-aliasing

---

## Example 3: Threshold Detector (Medium-Easy)

**What it does:** Detect when signal magnitude exceeds threshold (for squelch, burst detection)

### Verilog Code (`threshold_detector.v`)

```verilog
// Magnitude threshold detector
// Detects when |I + jQ| > threshold

module threshold_detector (
    input wire clk,
    input wire reset,
    
    // IQ input
    input wire signed [15:0] din_i,
    input wire signed [15:0] din_q,
    input wire din_valid,
    
    // Threshold (from ARM register)
    input wire [15:0] threshold,
    
    // Outputs
    output reg signal_detected,     // 1 when signal > threshold
    output reg [31:0] magnitude     // Signal magnitude (for monitoring)
);

// Calculate magnitude squared: I² + Q²
// (avoids square root for speed)
wire [31:0] i_squared;
wire [31:0] q_squared;
wire [31:0] mag_squared;

assign i_squared = din_i * din_i;
assign q_squared = din_q * din_q;
assign mag_squared = i_squared + q_squared;

// Compare with threshold squared
wire [31:0] threshold_squared;
assign threshold_squared = threshold * threshold;

always @(posedge clk) begin
    if (reset) begin
        signal_detected <= 1'b0;
        magnitude <= 32'd0;
    end else if (din_valid) begin
        magnitude <= mag_squared;
        
        if (mag_squared > threshold_squared) begin
            signal_detected <= 1'b1;
        end else begin
            signal_detected <= 1'b0;
        end
    end
end

endmodule
```

**Complexity:** 🟡 Medium-Easy
- **Resources:** ~300 LUTs, 3 DSP48E1 slices
- **What you learned:** Magnitude calculation, comparisons
- **Useful for:** Squelch, trigger, burst detection

---

## Example 4: Peak Detector with Timestamp (Medium)

**What it does:** Find peaks in signal and record their timestamp

### Verilog Code (`peak_detector.v`)

```verilog
// Peak detector with timestamp
// Records time when signal peaks occur

module peak_detector (
    input wire clk,
    input wire reset,
    
    input wire [15:0] signal_in,
    input wire signal_valid,
    
    // Peak detection parameters
    input wire [15:0] threshold,     // Minimum peak height
    input wire [7:0] holdoff,        // Samples to wait after peak
    
    // Outputs (connect to AXI registers for ARM readout)
    output reg peak_detected,
    output reg [31:0] peak_timestamp,
    output reg [15:0] peak_value
);

// Timestamp counter
reg [31:0] timestamp;

// Holdoff counter (prevents detecting same peak multiple times)
reg [7:0] holdoff_counter;

// Previous sample (for slope detection)
reg [15:0] prev_sample;
reg prev_valid;

// Detect rising edge crossing threshold
wire is_peak;
assign is_peak = signal_valid && 
                 (signal_in > threshold) && 
                 (signal_in > prev_sample) &&  // Rising
                 prev_valid &&
                 (holdoff_counter == 0);

always @(posedge clk) begin
    if (reset) begin
        timestamp <= 32'd0;
        holdoff_counter <= 8'd0;
        peak_detected <= 1'b0;
        peak_timestamp <= 32'd0;
        peak_value <= 16'd0;
        prev_sample <= 16'd0;
        prev_valid <= 1'b0;
    end else begin
        // Increment timestamp every clock
        timestamp <= timestamp + 1;
        
        // Update previous sample
        if (signal_valid) begin
            prev_sample <= signal_in;
            prev_valid <= 1'b1;
        end
        
        // Holdoff counter
        if (holdoff_counter > 0) begin
            holdoff_counter <= holdoff_counter - 1;
        end
        
        // Peak detection
        if (is_peak) begin
            peak_detected <= 1'b1;
            peak_timestamp <= timestamp;
            peak_value <= signal_in;
            holdoff_counter <= holdoff;
        end else begin
            peak_detected <= 1'b0;
        end
    end
end

endmodule
```

**Complexity:** 🟡 Medium
- **Resources:** ~400 LUTs, 80 Flip-Flops
- **What you learned:** State machines, timing, edge detection
- **Useful for:** Pulse measurement, radar, time-of-arrival

---

## Example 5: Simple Correlator (Medium-Hard)

**What it does:** Cross-correlate two signals (for passive radar, sync detection)

### Verilog Code (`simple_correlator.v`)

```verilog
// Simple cross-correlator
// Computes correlation between reference and signal

module simple_correlator #(
    parameter TAP_LENGTH = 64  // Correlation length
)(
    input wire clk,
    input wire reset,
    
    // Reference signal (stored pattern)
    input wire [15:0] ref_i,
    input wire [15:0] ref_q,
    
    // Input signal to correlate
    input wire [15:0] sig_i,
    input wire [15:0] sig_q,
    input wire sig_valid,
    
    // Correlation output
    output reg [31:0] corr_magnitude,
    output reg corr_valid
);

// Shift register for incoming signal
reg [15:0] sig_i_delay [0:TAP_LENGTH-1];
reg [15:0] sig_q_delay [0:TAP_LENGTH-1];

// Accumulator for correlation sum
reg signed [31:0] corr_i_acc;
reg signed [31:0] corr_q_acc;

integer i;

always @(posedge clk) begin
    if (reset) begin
        for (i = 0; i < TAP_LENGTH; i = i + 1) begin
            sig_i_delay[i] <= 16'd0;
            sig_q_delay[i] <= 16'd0;
        end
        corr_i_acc <= 32'd0;
        corr_q_acc <= 32'd0;
        corr_valid <= 1'b0;
        corr_magnitude <= 32'd0;
    end else if (sig_valid) begin
        // Shift signal into delay line
        sig_i_delay[0] <= sig_i;
        sig_q_delay[0] <= sig_q;
        
        for (i = 1; i < TAP_LENGTH; i = i + 1) begin
            sig_i_delay[i] <= sig_i_delay[i-1];
            sig_q_delay[i] <= sig_q_delay[i-1];
        end
        
        // Compute correlation (simplified single-tap example)
        // Real version would sum over all TAP_LENGTH samples
        corr_i_acc <= (sig_i_delay[0] * ref_i) - (sig_q_delay[0] * ref_q);
        corr_q_acc <= (sig_i_delay[0] * ref_q) + (sig_q_delay[0] * ref_i);
        
        // Magnitude (I² + Q²)
        corr_magnitude <= (corr_i_acc * corr_i_acc) + (corr_q_acc * corr_q_acc);
        corr_valid <= 1'b1;
    end else begin
        corr_valid <= 1'b0;
    end
end

endmodule
```

**Complexity:** 🟠 Medium-Hard
- **Resources:** ~2,000 LUTs, ~2K Flip-Flops, 8 DSP48E1
- **What you learned:** Convolution, DSP algorithms
- **Useful for:** Passive radar, GPS sync, burst detection

---

## How to Add These to LibreSDR

### Step 1: Create Verilog File

```bash
cd /home/arsatyants/code/libresdr/plutosdr-fw_0.38_libre/hdl/library
mkdir user_custom
cd user_custom

# Copy one of the example modules above into:
nano simple_gain.v
```

### Step 2: Modify Block Design

Edit `hdl/projects/libre/system_bd.tcl`:

```tcl
# Add after line 280 (after axi_ad9361 connections)

# ============== CUSTOM USER LOGIC ==============

# Instantiate custom module
create_bd_cell -type module -reference simple_gain user_gain_i
create_bd_cell -type module -reference simple_gain user_gain_q

# Connect to AD9361 output (intercept samples)
disconnect_bd_net /axi_ad9361_adc_data_i0 [get_bd_pins rx_fir_decimator/data_in_0]
connect_bd_net [get_bd_pins axi_ad9361/adc_data_i0] [get_bd_pins user_gain_i/din]
connect_bd_net [get_bd_pins user_gain_i/dout] [get_bd_pins rx_fir_decimator/data_in_0]

# Connect clock and reset
connect_bd_net [get_bd_pins sys_cpu_clk] [get_bd_pins user_gain_i/clk]
connect_bd_net [get_bd_pins sys_cpu_resetn] [get_bd_pins user_gain_i/reset]

# Connect gain control register (from AXI register at 0x43C00000)
# (You'd need to add an AXI GPIO module for this - see next example)
```

### Step 3: Rebuild FPGA

```bash
cd /home/arsatyants/code/libresdr/plutosdr-fw_0.38_libre
export VIVADO_SETTINGS=/media/arsatyants/vivado/vivado/Vitis/2022.2/settings64.sh
export TARGET=libre

# Rebuild just the FPGA
make clean
make build/system_top.xsa

# Or rebuild everything
make
```

---

## Complete Example: Add AXI Control Register

This shows how to add ARM-controlled registers for your custom logic:

### Modified `system_bd.tcl`

```tcl
# Add AXI GPIO for user controls
ad_ip_instance axi_gpio user_control_gpio
ad_ip_parameter user_control_gpio CONFIG.C_GPIO_WIDTH 32
ad_ip_parameter user_control_gpio CONFIG.C_ALL_OUTPUTS 1

# Connect to AXI bus (ARM can access at this address)
ad_cpu_interconnect 0x43C00000 user_control_gpio

# Connect GPIO output to custom module
ad_connect user_control_gpio/gpio_io_o user_gain_i/gain
```

### Access from Linux (after boot):

```bash
# Write gain value (0-255) to register
devmem 0x43C00000 32 128  # Set gain to 128 (unity)
devmem 0x43C00000 32 255  # Set gain to 255 (2× amplification)
```

---

## Learning Path

### Week 1: Understanding
1. Read existing LibreSDR TCL scripts
2. Simulate simple examples in Vivado
3. Understand clock domains

### Week 2: Modification  
1. Change FIR filter coefficients
2. Modify gain constants
3. Add printf-style debug signals

### Week 3: Addition
1. Add simple gain control (Example 1)
2. Wire it into data path
3. Control from Linux

### Week 4: Custom IP
1. Write moving average filter (Example 2)
2. Add AXI registers
3. Python control script

### Month 2: Real Projects
- Hardware FFT using Xilinx IP
- Custom demodulator
- Passive radar correlator

---

## Useful Resources

### Official Xilinx Documentation
- **UG953:** Vivado Design Suite User Guide
- **UG761:** AXI Reference Guide  
- **UG479:** 7 Series DSP48E1 User Guide

### Online Tutorials
- **Nandland:** Great Verilog/VHDL tutorials (nandland.com)
- **ZipCPU:** FPGA design blog with practical examples
- **HDLBits:** Interactive Verilog practice (hdlbits.01xz.net)

### Example Projects
```bash
# Analog Devices HDL library (what LibreSDR uses)
cd hdl/library/
ls -la
# Study: axi_ad9361, axi_dmac, util_cpack2
```

### Simulation (Before Hardware)

```bash
# Create testbench
cd hdl/library/user_custom/
nano simple_gain_tb.v

# Simulate in Vivado
vivado -mode batch -source sim.tcl
```

---

## Pro Tips

1. **Start VERY simple:** Blink an LED, pass-through data unchanged
2. **Simulate first:** Debug in software (Vivado simulator) before hardware
3. **One change at a time:** Don't modify 5 things simultaneously
4. **Use ChipScope/ILA:** Add debug logic to see internal signals
5. **Check timing reports:** Vivado will warn if design is too slow
6. **Keep backups:** FPGA changes can brick hardware if wrong

---

## What Example Should You Try First?

- **Want easy win?** → Example 1 (Gain Control)
- **Want noise reduction?** → Example 2 (Moving Average)
- **Want burst detection?** → Example 3 (Threshold Detector)
- **Want radar processing?** → Example 5 (Correlator)

All of these fit easily in the 53% free FPGA resources!

Want me to generate a complete working module with testbench for any of these?
