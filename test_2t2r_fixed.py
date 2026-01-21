#!/usr/bin/env python3
import adi
import numpy as np
import time

LIBRESDR_IP = "ip:192.168.1.10"
TEST_FREQ = 2.4e9
SAMPLE_RATE = 27e6
TX_POWER = -30
BUFFER_SIZE = 2**14
TEST_DURATION = 0.5

def measure_rssi(rx_data):
    """Calculate RSSI in dBFS"""
    # Handle both 1D and 2D arrays
    if len(rx_data.shape) == 1:
        data = rx_data
    else:
        data = rx_data[0] if rx_data.shape[0] > 0 else rx_data.flatten()
    
    power_linear = np.mean(np.abs(data)**2)
    if power_linear > 1e-10:
        rssi_dbfs = 10 * np.log10(power_linear)
    else:
        rssi_dbfs = -100
    return rssi_dbfs

def test_tx_rx_pair(sdr, tx_channel, rx_channel):
    """Test TX->RX pair using direct IIO channel control"""
    print(f"\n{'='*60}")
    print(f"Testing: TX{tx_channel} → RX{rx_channel}")
    print(f"{'='*60}")
    
    try:
        # Stop any active TX
        try:
            sdr.tx_destroy_buffer()
        except:
            pass
        
        time.sleep(0.2)
        
        # Direct channel control via _ctrl attributes
        # Enable specific voltage channels for TX and RX
        tx_i_idx = 0 if tx_channel == 1 else 2
        tx_q_idx = 1 if tx_channel == 1 else 3
        rx_i_idx = 0 if rx_channel == 1 else 2
        rx_q_idx = 1 if rx_channel == 1 else 3
        
        # Access raw IIO channels
        tx_dev = sdr._txdac
        rx_dev = sdr._rxadc
        
        # Enable TX channels
        for i, ch in enumerate(tx_dev.channels):
            if i == tx_i_idx or i == tx_q_idx:
                ch.enabled = True
            else:
                ch.enabled = False
        
        # Enable RX channels  
        for i, ch in enumerate(rx_dev.channels):
            if i == rx_i_idx or i == rx_q_idx:
                ch.enabled = True
            else:
                ch.enabled = False
        
        # Set gains
        if tx_channel == 1:
            sdr.tx_hardwaregain_chan0 = TX_POWER
        else:
            sdr.tx_hardwaregain_chan1 = TX_POWER
            
        if rx_channel == 1:
            sdr.rx_hardwaregain_chan0 = 10
        else:
            sdr.rx_hardwaregain_chan1 = 10
        
        print(f"  TX{tx_channel} enabled: channels [{tx_i_idx},{tx_q_idx}]")
        print(f"  RX{rx_channel} enabled: channels [{rx_i_idx},{rx_q_idx}]")
        
        # Generate test tone
        tone_freq = 1e6
        t = np.arange(BUFFER_SIZE) / SAMPLE_RATE
        tx_signal_complex = 0.8 * np.exp(1j * 2 * np.pi * tone_freq * t)
        
        # When manually enabling I/Q channels, must provide [I, Q] arrays
        tx_signal = [tx_signal_complex.real, tx_signal_complex.imag]
        
        # Transmit
        sdr.tx_cyclic_buffer = True
        sdr.tx(tx_signal)
        print("  TX started...")
        
        time.sleep(TEST_DURATION)
        
        # Receive
        rx_data = sdr.rx()
        
        print(f"  RX data type: {type(rx_data)}")
        
        if rx_data is None:
            print("✗ No data received")
            sdr.tx_destroy_buffer()
            return False, None
        
        # Handle list of I/Q channels
        if isinstance(rx_data, list):
            if len(rx_data) == 0:
                print("✗ Empty data list")
                sdr.tx_destroy_buffer()
                return False, None
            
            # Debug: check which elements have data
            print(f"  RX list length: {len(rx_data)}")
            for i, elem in enumerate(rx_data):
                elem_len = len(elem) if hasattr(elem, '__len__') else 0
                print(f"    rx_data[{i}]: length={elem_len}")
            
            # Find the non-empty element(s)
            non_empty = [np.array(elem) for elem in rx_data if hasattr(elem, '__len__') and len(elem) > 0]
            
            if len(non_empty) == 0:
                print("✗ All list elements empty")
                sdr.tx_destroy_buffer()
                return False, None
            elif len(non_empty) == 2:
                # Both I and Q present, recombine
                rx_data = non_empty[0] + 1j * non_empty[1]
                print(f"  Recombined I/Q into complex: shape {rx_data.shape}")
            else:
                # Only one channel has data (shouldn't happen but handle it)
                rx_data = non_empty[0]
                print(f"  Using single channel data: shape {rx_data.shape}")
        
        print(f"  RX data shape: {rx_data.shape if hasattr(rx_data, 'shape') else 'no shape'}")
        
        if not hasattr(rx_data, 'shape') or len(rx_data) == 0:
            print("✗ Invalid data format")
            sdr.tx_destroy_buffer()
            return False, None
        
        # Calculate RSSI
        rssi = measure_rssi(rx_data)
        
        print(f"✓ Signal received!")
        print(f"  RSSI: {rssi:.1f} dBFS")
        print(f"  Samples: {len(rx_data)}")
        print(f"  Peak: {20*np.log10(np.max(np.abs(rx_data))+1e-10):.1f} dBFS")
        
        # Stop TX
        sdr.tx_destroy_buffer()
        
        # Check signal quality
        if rssi > -40:
            status = "EXCELLENT"
            passed = True
        elif rssi > -60:
            status = "GOOD"
            passed = True
        elif rssi > -80:
            status = "WEAK"
            passed = True
        else:
            status = "NO SIGNAL"
            passed = False
        
        print(f"  Status: {status}")
        return passed, rssi
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        try:
            sdr.tx_destroy_buffer()
        except:
            pass
        return False, None

def main():
    print("="*60)
    print("LibreSDR 2T2R Channel Test (Fixed)")
    print("="*60)
    print(f"pyadi-iio version: {adi.__version__}")
    print(f"Device: {LIBRESDR_IP}")
    print(f"Frequency: {TEST_FREQ/1e9:.3f} GHz")
    print("="*60)
    
    # Connect
    print("\nConnecting...")
    sdr = adi.ad9361(uri=LIBRESDR_IP)
    
    # Basic config
    sdr.tx_lo = int(TEST_FREQ)
    sdr.rx_lo = int(TEST_FREQ)
    sdr.tx_rf_bandwidth = int(SAMPLE_RATE)
    sdr.rx_rf_bandwidth = int(SAMPLE_RATE)
    sdr.sample_rate = int(SAMPLE_RATE)
    sdr.tx_buffer_size = BUFFER_SIZE
    sdr.rx_buffer_size = BUFFER_SIZE
    sdr.gain_control_mode_chan0 = "manual"
    sdr.gain_control_mode_chan1 = "manual"
    
    # Check available channels
    print(f"\nSDR Info:")
    try:
        print(f"  RX channels: {sdr._rx_channel_names}")
        print(f"  TX channels: {sdr._tx_channel_names}")
    except:
        print("  (Channel info not available)")
    
    print("✓ Connected!\n")
    
    # Run tests
    test_pairs = [(1,1), (2,1), (1,2), (2,2)]
    results = {}
    
    for tx_ch, rx_ch in test_pairs:
        success, rssi = test_tx_rx_pair(sdr, tx_ch, rx_ch)
        results[(tx_ch, rx_ch)] = (success, rssi)
        time.sleep(0.5)
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"{'TX':<6} {'RX':<6} {'Status':<12} {'RSSI (dBFS)':<15}")
    print("-"*60)
    
    for (tx_ch, rx_ch), (success, rssi) in results.items():
        status = "✓ PASS" if success else "✗ FAIL"
        rssi_str = f"{rssi:.1f}" if rssi is not None else "N/A"
        print(f"TX{tx_ch}   RX{rx_ch}   {status:<12} {rssi_str:<15}")
    
    print("="*60)
    
    all_passed = all(s for s, _ in results.values())
    if all_passed:
        print("\n✓✓✓ All channels working! RX2 is functional! ✓✓✓")
    else:
        failed = [(tx,rx) for (tx,rx), (s,_) in results.items() if not s]
        print(f"\n✗ Failed pairs: {failed}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
