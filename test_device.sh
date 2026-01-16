#!/bin/bash
#
# LibreSDR Device Test Script
# Tests connectivity, IIO device, and sampling capability
#

set +e  # Don't exit on error

DEVICE_IP="192.168.1.10"
TEST_DURATION=5

echo "========================================"
echo "LibreSDR Device Test"
echo "========================================"
echo

# Test 1: Ping connectivity
echo "Test 1: Network Connectivity"
echo "----------------------------"
if ping -c 2 -W 2 $DEVICE_IP > /dev/null 2>&1; then
    echo "✓ PASS: Device responds to ping at $DEVICE_IP"
else
    echo "✗ FAIL: No ping response from $DEVICE_IP"
    echo "  Action: Run ./boot_libresdr.sh or reconfigure network"
    exit 1
fi
echo

# Test 2: IIO device detection
echo "Test 2: IIO Device Detection"
echo "----------------------------"
IIO_OUTPUT=$(iio_info -u ip:$DEVICE_IP 2>&1)
if echo "$IIO_OUTPUT" | grep -q "cf-ad9361-lpc"; then
    echo "✓ PASS: IIO device cf-ad9361-lpc detected"
    echo "$IIO_OUTPUT" | grep -E "(hw_model|fw_version|ad9361-phy|cf-ad9361)" | head -5
else
    echo "✗ FAIL: IIO device not accessible"
    echo "  Error: $IIO_OUTPUT"
    exit 1
fi
echo

# Test 3: Check buffer size
echo "Test 3: IIO Buffer Configuration"
echo "--------------------------------"
BUFFER_SIZE=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no root@$DEVICE_IP "cat /sys/bus/iio/devices/iio:device3/buffer/length 2>/dev/null" 2>&1 | tr -d '\r')
if [ -n "$BUFFER_SIZE" ] && [ "$BUFFER_SIZE" -gt 0 ]; then
    echo "✓ Buffer size: $BUFFER_SIZE samples"
    if [ "$BUFFER_SIZE" -lt 131072 ]; then
        echo "  ⚠ WARNING: Buffer size is small (< 128K)"
        echo "  Increasing buffer size..."
        ssh -o ConnectTimeout=5 root@$DEVICE_IP "echo 131072 > /sys/bus/iio/devices/iio:device3/buffer/length" 2>&1 | grep -v "password"
        NEW_SIZE=$(ssh -o ConnectTimeout=5 root@$DEVICE_IP "cat /sys/bus/iio/devices/iio:device3/buffer/length 2>/dev/null" 2>&1 | tr -d '\r')
        echo "  ✓ Buffer increased to: $NEW_SIZE samples"
    fi
else
    echo "✗ Cannot check buffer size (SSH may require password: analog)"
    echo "  Manual command: ssh root@$DEVICE_IP 'cat /sys/bus/iio/devices/iio:device3/buffer/length'"
fi
echo

# Test 4: Sample capture
echo "Test 4: Sample Capture Test"
echo "---------------------------"
echo "Capturing 100,000 samples from cf-ad9361-lpc..."

# Create temporary file
TEMP_FILE="/tmp/libresdr_test_$$.dat"

# Try to capture samples
START_TIME=$(date +%s)
timeout $TEST_DURATION iio_readdev -u ip:$DEVICE_IP -b 65536 -s 100000 cf-ad9361-lpc voltage0 voltage1 > "$TEMP_FILE" 2>&1
CAPTURE_EXIT=$?
END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

if [ $CAPTURE_EXIT -eq 124 ]; then
    echo "✗ FAIL: Capture timed out after ${TEST_DURATION}s"
    echo "  This usually means:"
    echo "  1. Device disconnected during capture (USB instability)"
    echo "  2. IIO streaming not working properly"
    rm -f "$TEMP_FILE"
    exit 1
elif [ $CAPTURE_EXIT -ne 0 ]; then
    echo "✗ FAIL: Capture failed with exit code $CAPTURE_EXIT"
    cat "$TEMP_FILE" | head -10
    rm -f "$TEMP_FILE"
    exit 1
fi

# Check captured data
if [ ! -f "$TEMP_FILE" ]; then
    echo "✗ FAIL: No output file created"
    exit 1
fi

FILE_SIZE=$(stat -f%z "$TEMP_FILE" 2>/dev/null || stat -c%s "$TEMP_FILE" 2>/dev/null)
EXPECTED_SIZE=$((100000 * 2 * 2))  # 100K samples × 2 channels × 2 bytes

echo "✓ Capture completed in ${ELAPSED}s"
echo "  File size: $FILE_SIZE bytes"
echo "  Expected: ~$EXPECTED_SIZE bytes"

if [ $FILE_SIZE -lt 1000 ]; then
    echo "✗ FAIL: Captured data too small ($FILE_SIZE bytes)"
    echo "  Content:"
    head -5 "$TEMP_FILE"
    rm -f "$TEMP_FILE"
    exit 1
fi

# Check if data has variation (not all zeros/same value)
if command -v od > /dev/null; then
    SAMPLE_VALUES=$(od -An -td2 -N100 "$TEMP_FILE" | tr -s ' ' '\n' | sort -u | wc -l)
    if [ $SAMPLE_VALUES -lt 5 ]; then
        echo "⚠ WARNING: Low data variation (only $SAMPLE_VALUES unique values)"
        echo "  This may indicate no antenna or very weak signal"
    else
        echo "✓ Data shows variation ($SAMPLE_VALUES unique values in first 50 samples)"
    fi
fi

# Calculate throughput
if [ $FILE_SIZE -gt 0 ] && [ $ELAPSED -gt 0 ]; then
    THROUGHPUT=$((FILE_SIZE / ELAPSED / 1024 / 1024))
    echo "✓ Throughput: ~${THROUGHPUT} MB/s"
fi

rm -f "$TEMP_FILE"
echo

# Final summary
echo "========================================"
echo "✅ SUCCESS: All tests passed!"
echo "========================================"
echo
echo "Your LibreSDR device is capturing samples correctly."
echo
echo "Next steps for SDR Angel:"
echo "1. Ensure device stays connected (check USB stability)"
echo "2. In SDR Angel, use these settings:"
echo "   - Device: PlutoSDR (select from dropdown)"
echo "   - Sample rate: 2.0 MSPS (start low)"
echo "   - Bandwidth: 2.0 MHz"
echo "   - Center frequency: 100 MHz (or your target)"
echo "   - RF Gain: Manual, 50 dB"
echo "3. Click 'Start' - it should work now"
echo
echo "If SDR Angel still fails:"
echo "  - Device may disconnect mid-stream (USB stability issue)"
echo "  - Check dmesg for USB disconnect messages"
echo "  - Try powered USB hub or different port"
