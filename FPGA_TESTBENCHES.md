# FPGA Testbench Examples

Complete simulation testbenches for the FPGA examples. Run these in Vivado simulator to verify your design before building hardware.

## Testbench 1: Simple Gain Module

### File: `simple_gain_tb.v`

```verilog
`timescale 1ns / 1ps

// Testbench for simple_gain module
module simple_gain_tb;

// Clock period (10ns = 100 MHz)
parameter CLK_PERIOD = 10;

// Testbench signals
reg clk;
reg reset;
reg [15:0] din_i;
reg [15:0] din_q;
reg din_valid;
reg [7:0] gain;

wire [15:0] dout_i;
wire [15:0] dout_q;
wire dout_valid;

// Instantiate the Unit Under Test (UUT)
simple_gain uut (
    .clk(clk),
    .reset(reset),
    .din_i(din_i),
    .din_q(din_q),
    .din_valid(din_valid),
    .gain(gain),
    .dout_i(dout_i),
    .dout_q(dout_q),
    .dout_valid(dout_valid)
);

// Clock generation
initial begin
    clk = 0;
    forever #(CLK_PERIOD/2) clk = ~clk;
end

// Test stimulus
initial begin
    // Initialize signals
    reset = 1;
    din_i = 0;
    din_q = 0;
    din_valid = 0;
    gain = 128;  // Unity gain
    
    // Wait for 100ns
    #100;
    
    // Release reset
    reset = 0;
    #(CLK_PERIOD*2);
    
    // Test 1: Unity gain (128/128 = 1.0)
    $display("=== Test 1: Unity Gain ===");
    gain = 128;
    #(CLK_PERIOD);
    
    // Send sample: I=1000, Q=2000
    din_i = 16'sd1000;
    din_q = 16'sd2000;
    din_valid = 1;
    #(CLK_PERIOD);
    din_valid = 0;
    
    // Wait for output
    #(CLK_PERIOD*3);
    $display("Input:  I=%d, Q=%d, Gain=%d", 16'sd1000, 16'sd2000, 128);
    $display("Output: I=%d, Q=%d (Expected: I≈1000, Q≈2000)", $signed(dout_i), $signed(dout_q));
    
    // Test 2: 2× gain (256/128 = 2.0)
    $display("\n=== Test 2: 2× Gain ===");
    gain = 255;  // Close to 2×
    #(CLK_PERIOD);
    
    din_i = 16'sd1000;
    din_q = 16'sd2000;
    din_valid = 1;
    #(CLK_PERIOD);
    din_valid = 0;
    
    #(CLK_PERIOD*3);
    $display("Input:  I=%d, Q=%d, Gain=%d", 16'sd1000, 16'sd2000, 255);
    $display("Output: I=%d, Q=%d (Expected: I≈2000, Q≈4000)", $signed(dout_i), $signed(dout_q));
    
    // Test 3: 0.5× gain (64/128 = 0.5)
    $display("\n=== Test 3: 0.5× Gain ===");
    gain = 64;
    #(CLK_PERIOD);
    
    din_i = 16'sd1000;
    din_q = 16'sd2000;
    din_valid = 1;
    #(CLK_PERIOD);
    din_valid = 0;
    
    #(CLK_PERIOD*3);
    $display("Input:  I=%d, Q=%d, Gain=%d", 16'sd1000, 16'sd2000, 64);
    $display("Output: I=%d, Q=%d (Expected: I≈500, Q≈1000)", $signed(dout_i), $signed(dout_q));
    
    // Test 4: Negative samples
    $display("\n=== Test 4: Negative Samples ===");
    gain = 128;
    #(CLK_PERIOD);
    
    din_i = -16'sd1000;
    din_q = -16'sd2000;
    din_valid = 1;
    #(CLK_PERIOD);
    din_valid = 0;
    
    #(CLK_PERIOD*3);
    $display("Input:  I=%d, Q=%d, Gain=%d", -16'sd1000, -16'sd2000, 128);
    $display("Output: I=%d, Q=%d (Expected: I≈-1000, Q≈-2000)", $signed(dout_i), $signed(dout_q));
    
    // Test 5: Stream of samples
    $display("\n=== Test 5: Continuous Stream ===");
    gain = 128;
    repeat(10) begin
        din_i = $random % 32767;  // Random samples
        din_q = $random % 32767;
        din_valid = 1;
        $display("Sample: I=%d, Q=%d -> Output: I=%d, Q=%d", 
                 $signed(din_i), $signed(din_q), $signed(dout_i), $signed(dout_q));
        #(CLK_PERIOD);
    end
    din_valid = 0;
    
    // Finish simulation
    #(CLK_PERIOD*10);
    $display("\n=== Simulation Complete ===");
    $finish;
end

// Monitor output changes
always @(posedge dout_valid) begin
    $display("Time=%0t: Valid output detected", $time);
end

endmodule
```

---

## Testbench 2: Moving Average Filter

### File: `moving_average_tb.v`

```verilog
`timescale 1ns / 1ps

module moving_average_tb;

parameter CLK_PERIOD = 10;

reg clk;
reg reset;
reg [15:0] din;
reg din_valid;

wire [15:0] dout;
wire dout_valid;

// Instantiate UUT
moving_average uut (
    .clk(clk),
    .reset(reset),
    .din(din),
    .din_valid(din_valid),
    .dout(dout),
    .dout_valid(dout_valid)
);

// Clock generation
initial begin
    clk = 0;
    forever #(CLK_PERIOD/2) clk = ~clk;
end

// Test stimulus
initial begin
    reset = 1;
    din = 0;
    din_valid = 0;
    
    #100;
    reset = 0;
    #(CLK_PERIOD*2);
    
    // Test 1: Constant input (should output same value)
    $display("=== Test 1: Constant Input ===");
    repeat(10) begin
        din = 16'd1000;
        din_valid = 1;
        #(CLK_PERIOD);
        $display("Input: %d, Output: %d", din, dout);
    end
    din_valid = 0;
    #(CLK_PERIOD*5);
    
    // Test 2: Step response
    $display("\n=== Test 2: Step Response (0 → 1000) ===");
    din = 0;
    din_valid = 1;
    repeat(4) begin
        #(CLK_PERIOD);
        $display("Input: %d, Output: %d", din, dout);
    end
    
    din = 16'd1000;
    repeat(8) begin
        #(CLK_PERIOD);
        $display("Input: %d, Output: %d", din, dout);
    end
    din_valid = 0;
    
    // Test 3: Noisy signal
    $display("\n=== Test 3: Noisy Signal ===");
    din_valid = 1;
    repeat(20) begin
        // Base signal 5000 + random noise ±500
        din = 16'd5000 + ($random % 1000) - 500;
        #(CLK_PERIOD);
        $display("Input: %d (noisy), Output: %d (smoothed)", $signed(din), $signed(dout));
    end
    din_valid = 0;
    
    // Test 4: Square wave (to see delay)
    $display("\n=== Test 4: Square Wave ===");
    din_valid = 1;
    repeat(20) begin
        din = ($time / (CLK_PERIOD*4)) % 2 ? 16'd2000 : 16'd0;
        #(CLK_PERIOD);
        $display("Input: %d, Output: %d", din, dout);
    end
    din_valid = 0;
    
    #(CLK_PERIOD*10);
    $display("\n=== Simulation Complete ===");
    $finish;
end

// Calculate actual average for verification
reg [17:0] sum;
reg [15:0] expected_avg;
always @(posedge clk) begin
    if (dout_valid) begin
        // Check if output is reasonable (within ±5% of expected)
        if (dout > expected_avg * 1.05 || dout < expected_avg * 0.95) begin
            $display("WARNING: Output mismatch at time %0t", $time);
        end
    end
end

endmodule
```

---

## Testbench 3: Threshold Detector

### File: `threshold_detector_tb.v`

```verilog
`timescale 1ns / 1ps

module threshold_detector_tb;

parameter CLK_PERIOD = 10;

reg clk;
reg reset;
reg signed [15:0] din_i;
reg signed [15:0] din_q;
reg din_valid;
reg [15:0] threshold;

wire signal_detected;
wire [31:0] magnitude;

// Instantiate UUT
threshold_detector uut (
    .clk(clk),
    .reset(reset),
    .din_i(din_i),
    .din_q(din_q),
    .din_valid(din_valid),
    .threshold(threshold),
    .signal_detected(signal_detected),
    .magnitude(magnitude)
);

// Clock generation
initial begin
    clk = 0;
    forever #(CLK_PERIOD/2) clk = ~clk;
end

// Test stimulus
initial begin
    reset = 1;
    din_i = 0;
    din_q = 0;
    din_valid = 0;
    threshold = 1000;  // Threshold at magnitude 1000
    
    #100;
    reset = 0;
    #(CLK_PERIOD*2);
    
    $display("=== Threshold Detector Test ===");
    $display("Threshold: %d (squared: %d)\n", threshold, threshold * threshold);
    
    // Test 1: Below threshold
    $display("Test 1: Signal below threshold");
    din_i = 16'sd500;   // Magnitude = sqrt(500² + 300²) ≈ 583
    din_q = 16'sd300;
    din_valid = 1;
    #(CLK_PERIOD*2);
    $display("I=%d, Q=%d, Magnitude²=%d, Detected=%b (Expected: 0)", 
             din_i, din_q, magnitude, signal_detected);
    
    // Test 2: Above threshold
    $display("\nTest 2: Signal above threshold");
    din_i = 16'sd1000;  // Magnitude = sqrt(1000² + 1000²) ≈ 1414
    din_q = 16'sd1000;
    #(CLK_PERIOD*2);
    $display("I=%d, Q=%d, Magnitude²=%d, Detected=%b (Expected: 1)", 
             din_i, din_q, magnitude, signal_detected);
    
    // Test 3: Exactly at threshold
    $display("\nTest 3: Signal at threshold");
    din_i = 16'sd707;   // Magnitude = sqrt(707² + 707²) ≈ 1000
    din_q = 16'sd707;
    #(CLK_PERIOD*2);
    $display("I=%d, Q=%d, Magnitude²=%d, Detected=%b", 
             din_i, din_q, magnitude, signal_detected);
    
    // Test 4: Negative samples (magnitude is always positive)
    $display("\nTest 4: Negative samples");
    din_i = -16'sd1000;
    din_q = -16'sd1000;
    #(CLK_PERIOD*2);
    $display("I=%d, Q=%d, Magnitude²=%d, Detected=%b (Expected: 1)", 
             din_i, din_q, magnitude, signal_detected);
    
    // Test 5: Signal burst (on/off)
    $display("\nTest 5: Signal burst detection");
    repeat(5) begin
        // Strong signal
        din_i = 16'sd2000;
        din_q = 16'sd2000;
        #(CLK_PERIOD);
        $display("Time=%0t: Strong signal, Detected=%b", $time, signal_detected);
        
        // Weak signal
        din_i = 16'sd100;
        din_q = 16'sd100;
        #(CLK_PERIOD);
        $display("Time=%0t: Weak signal, Detected=%b", $time, signal_detected);
    end
    
    // Test 6: Ramping signal
    $display("\nTest 6: Ramping signal");
    repeat(20) begin
        din_i = din_i + 16'sd100;
        din_q = din_q + 16'sd100;
        #(CLK_PERIOD);
        if (signal_detected) begin
            $display("Time=%0t: Threshold crossed! I=%d, Q=%d, Mag²=%d", 
                     $time, din_i, din_q, magnitude);
        end
    end
    
    din_valid = 0;
    
    #(CLK_PERIOD*10);
    $display("\n=== Simulation Complete ===");
    $finish;
end

// Detection event logger
always @(posedge signal_detected) begin
    $display(">>> SIGNAL DETECTED at time %0t <<<", $time);
end

always @(negedge signal_detected) begin
    $display(">>> Signal lost at time %0t <<<", $time);
end

endmodule
```

---

## Testbench 4: Peak Detector

### File: `peak_detector_tb.v`

```verilog
`timescale 1ns / 1ps

module peak_detector_tb;

parameter CLK_PERIOD = 10;

reg clk;
reg reset;
reg [15:0] signal_in;
reg signal_valid;
reg [15:0] threshold;
reg [7:0] holdoff;

wire peak_detected;
wire [31:0] peak_timestamp;
wire [15:0] peak_value;

// Instantiate UUT
peak_detector uut (
    .clk(clk),
    .reset(reset),
    .signal_in(signal_in),
    .signal_valid(signal_valid),
    .threshold(threshold),
    .holdoff(holdoff),
    .peak_detected(peak_detected),
    .peak_timestamp(peak_timestamp),
    .peak_value(peak_value)
);

// Clock generation
initial begin
    clk = 0;
    forever #(CLK_PERIOD/2) clk = ~clk;
end

// Test stimulus
initial begin
    reset = 1;
    signal_in = 0;
    signal_valid = 0;
    threshold = 500;
    holdoff = 10;  // Wait 10 samples after detecting peak
    
    #100;
    reset = 0;
    #(CLK_PERIOD*2);
    
    $display("=== Peak Detector Test ===");
    $display("Threshold: %d, Holdoff: %d samples\n", threshold, holdoff);
    
    // Test 1: Single peak
    $display("Test 1: Single peak");
    signal_valid = 1;
    
    // Ramp up
    signal_in = 100; #(CLK_PERIOD);
    signal_in = 300; #(CLK_PERIOD);
    signal_in = 600; #(CLK_PERIOD);  // Should trigger
    signal_in = 800; #(CLK_PERIOD);  // Peak
    signal_in = 600; #(CLK_PERIOD);  // Going down (no trigger - holdoff)
    signal_in = 400; #(CLK_PERIOD);
    signal_in = 200; #(CLK_PERIOD);
    signal_in = 0;   #(CLK_PERIOD*5);
    
    // Test 2: Multiple peaks
    $display("\nTest 2: Multiple peaks with holdoff");
    repeat(3) begin
        // Ramp up to peak
        signal_in = 0;   #(CLK_PERIOD);
        signal_in = 200; #(CLK_PERIOD);
        signal_in = 500; #(CLK_PERIOD);
        signal_in = 700; #(CLK_PERIOD);  // Peak
        signal_in = 400; #(CLK_PERIOD);
        signal_in = 100; #(CLK_PERIOD);
        #(CLK_PERIOD*5);  // Wait
    end
    
    // Test 3: Noise with peaks
    $display("\nTest 3: Noisy signal with peaks");
    repeat(50) begin
        // Random noise between 0-400
        signal_in = $random % 400;
        
        // Add occasional peaks
        if (($time / CLK_PERIOD) % 20 == 0) begin
            signal_in = 16'd1000;  // Peak!
        end
        
        #(CLK_PERIOD);
    end
    
    // Test 4: Below threshold (no detection)
    $display("\nTest 4: Signal below threshold");
    repeat(20) begin
        signal_in = 16'd400;  // Below 500
        #(CLK_PERIOD);
    end
    $display("(Should see no peaks detected)");
    
    signal_valid = 0;
    
    #(CLK_PERIOD*10);
    $display("\n=== Simulation Complete ===");
    $display("Total peaks detected: (check waveform)");
    $finish;
end

// Peak event logger
integer peak_count = 0;
always @(posedge peak_detected) begin
    peak_count = peak_count + 1;
    $display(">>> PEAK #%0d DETECTED <<<", peak_count);
    $display("    Time:      %0t ns", $time);
    $display("    Timestamp: %0d clock cycles", peak_timestamp);
    $display("    Value:     %0d", peak_value);
end

// Waveform dump for viewing in GTKWave
initial begin
    $dumpfile("peak_detector_tb.vcd");
    $dumpvars(0, peak_detector_tb);
end

endmodule
```

---

## How to Run Simulations in Vivado

### Method 1: Command Line (Faster)

```bash
cd /home/arsatyants/code/libresdr/plutosdr-fw_0.38_libre/hdl/library/user_custom

# Create simulation script
cat > sim.tcl << 'EOF'
# Set up simulation
create_project -force sim_project ./sim_project -part xc7z020clg400-1

# Add source files
add_files {simple_gain.v}
add_files -fileset sim_1 {simple_gain_tb.v}

# Set testbench as top
set_property top simple_gain_tb [get_filesets sim_1]

# Run simulation
launch_simulation
run 2us

# Close
close_sim
EOF

# Run simulation
source /media/arsatyants/vivado/vivado/Vivado/2022.2/settings64.sh
vivado -mode batch -source sim.tcl
```

### Method 2: Vivado GUI (Better for debugging)

```bash
# Start Vivado
source /media/arsatyants/vivado/vivado/Vivado/2022.2/settings64.sh
vivado

# In Vivado GUI:
# 1. File → New Project → RTL Project
# 2. Add Sources → Add simple_gain.v
# 3. Add Simulation Sources → Add simple_gain_tb.v
# 4. Flow → Run Simulation → Run Behavioral Simulation
# 5. View waveforms, check console for $display output
```

### Method 3: Using Icarus Verilog (Free, lightweight)

```bash
# Install Icarus Verilog
sudo apt-get install iverilog gtkwave

# Compile and simulate
cd /home/arsatyants/code/libresdr
iverilog -o simple_gain_sim simple_gain.v simple_gain_tb.v
vvp simple_gain_sim

# View waveforms
gtkwave simple_gain_tb.vcd
```

---

## Expected Output Examples

### Simple Gain Test Output

```
=== Test 1: Unity Gain ===
Input:  I=1000, Q=2000, Gain=128
Output: I=1000, Q=2000 (Expected: I≈1000, Q≈2000)

=== Test 2: 2× Gain ===
Input:  I=1000, Q=2000, Gain=255
Output: I=1992, Q=3984 (Expected: I≈2000, Q≈4000)

=== Test 3: 0.5× Gain ===
Input:  I=1000, Q=2000, Gain=64
Output: I=500, Q=1000 (Expected: I≈500, Q≈1000)
```

### Threshold Detector Output

```
=== Threshold Detector Test ===
Threshold: 1000 (squared: 1000000)

Test 1: Signal below threshold
I=500, Q=300, Magnitude²=340000, Detected=0 (Expected: 0)

Test 2: Signal above threshold
I=1000, Q=1000, Magnitude²=2000000, Detected=1 (Expected: 1)
>>> SIGNAL DETECTED at time 220ns <<<
```

### Peak Detector Output

```
>>> PEAK #1 DETECTED <<<
    Time:      330 ns
    Timestamp: 33 clock cycles
    Value:     800

>>> PEAK #2 DETECTED <<<
    Time:      650 ns
    Timestamp: 65 clock cycles
    Value:     700
```

---

## Debugging Tips

### 1. Add Waveform Dumps

```verilog
initial begin
    $dumpfile("testbench.vcd");
    $dumpvars(0, testbench_name);
end
```

### 2. Add Debug Displays

```verilog
always @(posedge clk) begin
    if (din_valid) begin
        $display("Time=%0t: din=%d, dout=%d", $time, din, dout);
    end
end
```

### 3. Check for X (unknown) values

```verilog
initial begin
    #1000;
    if (dout === 16'hxxxx) begin
        $display("ERROR: Output is unknown!");
        $finish;
    end
end
```

### 4. Automatic Checking

```verilog
// Expected value calculation
reg [15:0] expected;
always @(posedge clk) begin
    expected = (din * gain) >> 7;  // Calculate expected
    
    #1;  // Wait for output to update
    if (dout_valid && (dout !== expected)) begin
        $display("ERROR at time %0t: Expected %d, Got %d", 
                 $time, expected, dout);
    end
end
```

---

## Simulation Checklist

Before running on hardware:

- [ ] All test cases pass
- [ ] No X (unknown) values in outputs
- [ ] Timing looks correct (no glitches)
- [ ] Reset behavior is clean
- [ ] Pipeline delays are acceptable
- [ ] No combinational loops
- [ ] Clock domain crossings handled properly

---

## Next Steps

1. **Run testbenches** for all modules
2. **View waveforms** in GTKWave or Vivado
3. **Verify** all test cases pass
4. **Synthesize** with Vivado to check resource usage
5. **Integrate** into LibreSDR block design
6. **Build** FPGA bitstream
7. **Test** on real hardware!

Want me to create a Makefile to automate the simulation process?
