/*
 * LibreSDR Sampling Test - C++ version
 * Verify IIO device can capture samples using libiio
 * 
 * Compile:
 *   g++ -o test_sampling test_sampling.cpp -liio -std=c++11
 * 
 * Run:
 *   ./test_sampling [uri] [duration_sec] [sample_rate_msps]
 *   Example: ./test_sampling ip:192.168.2.1 5 2.0
 */

#include <iio.h>
#include <iostream>
#include <string>
#include <vector>
#include <cstring>
#include <cstdlib>
#include <ctime>
#include <signal.h>
#include <unistd.h>
#include <limits>

static bool stop_capture = false;

void signal_handler(int sig) {
    std::cout << "\nInterrupted by user" << std::endl;
    stop_capture = true;
}

bool test_libresdr_sampling(const char* uri, int duration_sec, long long sample_rate) {
    std::cout << "LibreSDR Sampling Test (C++)" << std::endl;
    std::cout << std::string(60, '=') << std::endl;
    std::cout << "URI: " << uri << std::endl;
    std::cout << "Duration: " << duration_sec << " seconds" << std::endl;
    std::cout << "Sample rate: " << (sample_rate / 1e6) << " MSPS" << std::endl;
    std::cout << std::endl;
    
    // Create IIO context
    std::cout << "Connecting to device..." << std::endl;
    struct iio_context* ctx = iio_create_context_from_uri(uri);
    if (!ctx) {
        std::cerr << "✗ ERROR: Could not create IIO context for " << uri << std::endl;
        std::cerr << "  Check connection: ping 192.168.2.1" << std::endl;
        return false;
    }
    
    std::cout << "✓ Connected: " << iio_context_get_description(ctx) << std::endl;
    
    // Print context attributes
    unsigned int nb_attrs = iio_context_get_attrs_count(ctx);
    for (unsigned int i = 0; i < nb_attrs; i++) {
        const char* name;
        const char* value;
        if (iio_context_get_attr(ctx, i, &name, &value) == 0) {
            if (strcmp(name, "hw_model") == 0 || strcmp(name, "fw_version") == 0) {
                std::cout << "  " << name << ": " << value << std::endl;
            }
        }
    }
    std::cout << std::endl;
    
    // List devices
    std::cout << "Available IIO devices:" << std::endl;
    unsigned int nb_devices = iio_context_get_devices_count(ctx);
    for (unsigned int i = 0; i < nb_devices; i++) {
        struct iio_device* dev = iio_context_get_device(ctx, i);
        const char* name = iio_device_get_name(dev);
        unsigned int nb_channels = iio_device_get_channels_count(dev);
        std::cout << "  - " << (name ? name : iio_device_get_id(dev)) 
                  << ": " << nb_channels << " channels" << std::endl;
    }
    std::cout << std::endl;
    
    // Find RX device
    struct iio_device* rx_dev = iio_context_find_device(ctx, "cf-ad9361-lpc");
    if (!rx_dev) {
        std::cerr << "✗ ERROR: cf-ad9361-lpc device not found!" << std::endl;
        iio_context_destroy(ctx);
        return false;
    }
    
    std::cout << "Using RX device: " << (iio_device_get_name(rx_dev) ? 
              iio_device_get_name(rx_dev) : iio_device_get_id(rx_dev)) << std::endl;
    
    // Find PHY device for sample rate configuration
    struct iio_device* phy_dev = iio_context_find_device(ctx, "ad9361-phy");
    if (phy_dev) {
        struct iio_channel* phy_ch = iio_device_find_channel(phy_dev, "voltage0", false);
        if (phy_ch) {
            struct iio_channel_attr* attr = iio_channel_find_attr(phy_ch, "sampling_frequency");
            if (attr) {
                char buf[32];
                snprintf(buf, sizeof(buf), "%lld", sample_rate);
                if (iio_channel_attr_write(phy_ch, "sampling_frequency", buf) >= 0) {
                    long long actual_rate;
                    if (iio_channel_attr_read_longlong(phy_ch, "sampling_frequency", &actual_rate) == 0) {
                        std::cout << "✓ Sample rate set to: " << (actual_rate / 1e6) << " MSPS" << std::endl;
                    }
                }
            }
        }
    }
    
    // Enable RX channels (voltage0 and voltage1 for I/Q)
    std::vector<struct iio_channel*> rx_channels;
    for (const char* ch_name : {"voltage0", "voltage1"}) {
        struct iio_channel* ch = iio_device_find_channel(rx_dev, ch_name, false);
        if (ch) {
            iio_channel_enable(ch);
            rx_channels.push_back(ch);
            std::cout << "✓ Enabled channel: " << ch_name << std::endl;
        }
    }
    
    if (rx_channels.empty()) {
        std::cerr << "✗ ERROR: No RX channels could be enabled!" << std::endl;
        iio_context_destroy(ctx);
        return false;
    }
    std::cout << std::endl;
    
    // Create buffer
    size_t buffer_size = 16384;  // 16K samples
    std::cout << "Creating buffer (" << buffer_size << " samples)..." << std::endl;
    struct iio_buffer* buffer = iio_device_create_buffer(rx_dev, buffer_size, false);
    if (!buffer) {
        std::cerr << "✗ ERROR: Could not create buffer!" << std::endl;
        std::cerr << "  Hint: Increase buffer size on device:" << std::endl;
        std::cerr << "  ssh root@192.168.2.1 'echo 131072 > /sys/bus/iio/devices/iio:device3/buffer/length'" << std::endl;
        iio_context_destroy(ctx);
        return false;
    }
    std::cout << "✓ Buffer created: " << buffer_size << " samples" << std::endl;
    std::cout << std::endl;
    
    // Capture samples
    std::cout << "Capturing for " << duration_sec << " seconds..." << std::endl;
    std::cout << std::string(60, '-') << std::endl;
    
    signal(SIGINT, signal_handler);
    
    time_t start_time = time(NULL);
    unsigned long long total_samples = 0;
    unsigned int refill_count = 0;
    int16_t min_val = std::numeric_limits<int16_t>::max();
    int16_t max_val = std::numeric_limits<int16_t>::min();
    
    while (difftime(time(NULL), start_time) < duration_sec && !stop_capture) {
        ssize_t ret = iio_buffer_refill(buffer);
        if (ret < 0) {
            std::cerr << "\n✗ ERROR during buffer refill: " << ret << std::endl;
            break;
        }
        
        refill_count++;
        
        // Process each channel
        for (auto ch : rx_channels) {
            size_t sample_size = iio_channel_get_data_format(ch)->length / 8;
            size_t samples_in_buffer = iio_buffer_step(buffer) * 
                                       (iio_buffer_end(buffer) - iio_buffer_start(buffer)) / 
                                       iio_buffer_step(buffer);
            
            int16_t* data = (int16_t*)iio_buffer_first(buffer, ch);
            if (data) {
                for (size_t i = 0; i < samples_in_buffer; i++) {
                    int16_t val = data[i * iio_buffer_step(buffer) / sample_size];
                    if (val < min_val) min_val = val;
                    if (val > max_val) max_val = val;
                }
                total_samples += samples_in_buffer;
            }
        }
        
        // Progress
        double elapsed = difftime(time(NULL), start_time);
        double rate = (elapsed > 0) ? (total_samples / elapsed / 1e6) : 0;
        std::cout << "  Elapsed: " << elapsed << "s | Samples: " << total_samples 
                  << " | Rate: " << rate << " MSPS | Refills: " << refill_count
                  << " | Range: [" << min_val << ", " << max_val << "]        \r" << std::flush;
    }
    
    std::cout << std::endl;
    double elapsed = difftime(time(NULL), start_time);
    
    // Cleanup
    iio_buffer_destroy(buffer);
    iio_context_destroy(ctx);
    
    // Statistics
    std::cout << std::string(60, '-') << std::endl;
    std::cout << "\n📊 Capture Statistics:" << std::endl;
    std::cout << "  Duration: " << elapsed << " seconds" << std::endl;
    std::cout << "  Total samples: " << total_samples << std::endl;
    std::cout << "  Average rate: " << (total_samples / elapsed / 1e6) << " MSPS" << std::endl;
    std::cout << "  Buffer refills: " << refill_count << std::endl;
    std::cout << "  Sample range: [" << min_val << ", " << max_val << "]" << std::endl;
    
    // Validate
    std::cout << "\n✅ Validation:" << std::endl;
    bool success = true;
    
    if (total_samples == 0) {
        std::cout << "  ✗ FAIL: No samples captured!" << std::endl;
        success = false;
    } else {
        std::cout << "  ✓ PASS: Sample capture working" << std::endl;
    }
    
    if (min_val == max_val) {
        std::cout << "  ✗ FAIL: All samples same value (" << min_val << ")" << std::endl;
        success = false;
    } else {
        std::cout << "  ✓ PASS: Signal shows variation" << std::endl;
    }
    
    if (success) {
        std::cout << "\n" << std::string(60, '=') << std::endl;
        std::cout << "✅ SUCCESS: Device is capturing samples correctly!" << std::endl;
        std::cout << std::string(60, '=') << std::endl;
    }
    
    return success;
}

int main(int argc, char** argv) {
    const char* uri = "ip:192.168.2.1";
    int duration = 5;
    long long sample_rate = 2000000;  // 2 MSPS
    
    if (argc > 1) uri = argv[1];
    if (argc > 2) duration = atoi(argv[2]);
    if (argc > 3) sample_rate = (long long)(atof(argv[3]) * 1e6);
    
    bool success = test_libresdr_sampling(uri, duration, sample_rate);
    
    if (!success) {
        std::cout << "\n💡 Troubleshooting tips:" << std::endl;
        std::cout << "1. Check device connection: ping 192.168.2.1" << std::endl;
        std::cout << "2. Verify IIO device: iio_info -u ip:192.168.2.1" << std::endl;
        std::cout << "3. Increase buffer size on device" << std::endl;
        std::cout << "4. Check USB stability" << std::endl;
        return 1;
    }
    
    return 0;
}
