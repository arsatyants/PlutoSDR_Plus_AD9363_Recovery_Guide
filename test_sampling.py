#!/usr/bin/env python3
"""
LibreSDR Sampling Test - Verify IIO device can capture samples
Tests both RX channels and displays sample statistics
"""

import iio
import numpy as np
import time
import sys

def test_libresdr_sampling(uri="ip:192.168.2.1", duration_sec=5, sample_rate=2000000):
    """
    Test LibreSDR sampling capability
    
    Args:
        uri: IIO context URI (default: ip:192.168.2.1)
        duration_sec: How long to capture (seconds)
        sample_rate: Sample rate in Hz (default: 2 MSPS)
    """
    print(f"LibreSDR Sampling Test")
    print(f"=" * 60)
    print(f"URI: {uri}")
    print(f"Duration: {duration_sec} seconds")
    print(f"Sample rate: {sample_rate / 1e6:.1f} MSPS")
    print()
    
    try:
        # Create IIO context
        print("Connecting to device...")
        ctx = iio.Context(uri)
        print(f"✓ Connected: {ctx.description}")
        print(f"  Hardware: {ctx.attrs.get('hw_model', 'Unknown')}")
        print(f"  Firmware: {ctx.attrs.get('fw_version', 'Unknown')}")
        print()
        
        # Find devices
        print("Available IIO devices:")
        for dev in ctx.devices:
            print(f"  - {dev.name or dev.id}: {len(dev.channels)} channels")
        print()
        
        # Get RX device (cf-ad9361-lpc)
        rx_dev = ctx.find_device("cf-ad9361-lpc")
        if not rx_dev:
            print("✗ ERROR: cf-ad9361-lpc device not found!")
            return False
        
        print(f"Using RX device: {rx_dev.name or rx_dev.id}")
        print(f"Channels: {[ch.id for ch in rx_dev.channels]}")
        print()
        
        # Get PHY device for configuration
        phy_dev = ctx.find_device("ad9361-phy")
        if not phy_dev:
            print("✗ WARNING: ad9361-phy not found, cannot configure sample rate")
        else:
            # Set sample rate
            try:
                phy_dev.find_channel("voltage0", False).attrs["sampling_frequency"].value = str(sample_rate)
                actual_rate = int(phy_dev.find_channel("voltage0", False).attrs["sampling_frequency"].value)
                print(f"✓ Sample rate set to: {actual_rate / 1e6:.3f} MSPS")
            except Exception as e:
                print(f"✗ WARNING: Could not set sample rate: {e}")
                actual_rate = sample_rate
        
        # Configure RX channels (enable voltage0 and voltage1 for I/Q)
        rx_channels = []
        for ch_id in ["voltage0", "voltage1"]:
            try:
                ch = rx_dev.find_channel(ch_id, False)
                if ch:
                    ch.enabled = True
                    rx_channels.append(ch)
                    print(f"✓ Enabled channel: {ch_id}")
            except Exception as e:
                print(f"✗ WARNING: Could not enable {ch_id}: {e}")
        
        if len(rx_channels) == 0:
            print("✗ ERROR: No RX channels could be enabled!")
            return False
        
        print()
        
        # Create buffer
        buffer_size = 16384  # 16K samples
        print(f"Creating buffer ({buffer_size} samples)...")
        try:
            buffer = iio.Buffer(rx_dev, buffer_size)
            print(f"✓ Buffer created: {buffer_size} samples")
        except Exception as e:
            print(f"✗ ERROR: Could not create buffer: {e}")
            print(f"  Hint: Try increasing buffer size on device:")
            print(f"  ssh root@192.168.2.1 'echo 131072 > /sys/bus/iio/devices/iio:device3/buffer/length'")
            return False
        
        print()
        
        # Capture samples
        print(f"Capturing for {duration_sec} seconds...")
        print("-" * 60)
        
        start_time = time.time()
        total_samples = 0
        refill_count = 0
        min_val = float('inf')
        max_val = float('-inf')
        
        while (time.time() - start_time) < duration_sec:
            try:
                # Refill buffer (blocking call, waits for new data)
                buffer.refill()
                refill_count += 1
                
                # Read data from each channel
                for ch in rx_channels:
                    data = np.frombuffer(ch.read(), dtype=np.int16)
                    total_samples += len(data)
                    
                    if len(data) > 0:
                        min_val = min(min_val, data.min())
                        max_val = max(max_val, data.max())
                
                # Progress indicator
                elapsed = time.time() - start_time
                samples_per_sec = total_samples / elapsed if elapsed > 0 else 0
                print(f"  Elapsed: {elapsed:.1f}s | Samples: {total_samples:,} | "
                      f"Rate: {samples_per_sec / 1e6:.2f} MSPS | "
                      f"Refills: {refill_count} | Range: [{min_val}, {max_val}]", 
                      end='\r', flush=True)
                
            except KeyboardInterrupt:
                print("\n\nInterrupted by user")
                break
            except Exception as e:
                print(f"\n✗ ERROR during capture: {e}")
                return False
        
        print()  # New line after progress
        elapsed = time.time() - start_time
        
        # Statistics
        print("-" * 60)
        print("\n📊 Capture Statistics:")
        print(f"  Duration: {elapsed:.3f} seconds")
        print(f"  Total samples: {total_samples:,}")
        print(f"  Average rate: {total_samples / elapsed / 1e6:.3f} MSPS")
        print(f"  Buffer refills: {refill_count}")
        print(f"  Samples per refill: {total_samples / refill_count if refill_count > 0 else 0:.0f}")
        print(f"  Sample range: [{min_val}, {max_val}]")
        
        # Validate results
        print("\n✅ Validation:")
        if total_samples == 0:
            print("  ✗ FAIL: No samples captured!")
            return False
        elif total_samples < sample_rate * duration_sec * 0.5:
            print(f"  ⚠ WARNING: Captured fewer samples than expected")
            print(f"    Expected: ~{sample_rate * duration_sec / len(rx_channels):,.0f}")
            print(f"    Actual: {total_samples:,}")
        else:
            print(f"  ✓ PASS: Sample capture working correctly")
        
        if min_val == max_val:
            print(f"  ✗ FAIL: All samples have same value ({min_val}) - no signal variation!")
            return False
        elif abs(min_val) < 10 and abs(max_val) < 10:
            print(f"  ⚠ WARNING: Very low signal amplitude (range: {min_val} to {max_val})")
            print(f"    Check antenna connection and RF gain settings")
        else:
            print(f"  ✓ PASS: Signal shows variation (range: {min_val} to {max_val})")
        
        print("\n" + "=" * 60)
        print("✅ SUCCESS: Device is capturing samples correctly!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n✗ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Parse arguments
    uri = "ip:192.168.2.1"
    duration = 5
    sample_rate = 2000000  # 2 MSPS
    
    if len(sys.argv) > 1:
        uri = sys.argv[1]
    if len(sys.argv) > 2:
        duration = int(sys.argv[2])
    if len(sys.argv) > 3:
        sample_rate = int(float(sys.argv[3]) * 1e6)
    
    # Run test
    success = test_libresdr_sampling(uri, duration, sample_rate)
    
    if not success:
        print("\n💡 Troubleshooting tips:")
        print("1. Check device connection: ping 192.168.2.1")
        print("2. Verify IIO device: iio_info -u ip:192.168.2.1")
        print("3. Increase buffer size: ssh root@192.168.2.1 'echo 131072 > /sys/bus/iio/devices/iio:device3/buffer/length'")
        print("4. Check USB stability (disconnect/reconnect issues)")
        sys.exit(1)
    
    sys.exit(0)
