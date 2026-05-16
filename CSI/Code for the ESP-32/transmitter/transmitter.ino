/*
 * ESP32-S3 CSI TRANSMITTER — ESP-NOW (based on official Espressif esp-csi)
 * -------------------------------------------------------------------------
 * Uses ESP-NOW instead of UDP — no router needed at all.
 * Sets a fixed known MAC so the receiver can filter precisely.
 * Sends at 100Hz on channel 11.
 *
 * Board : ESP32S3 Dev Module
 * Baud  : 115200
 */

#include "nvs_flash.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_log.h"
#include "esp_netif.h"
#include <unistd.h>

// ── Fixed MAC — receiver uses this exact address to filter ─────────
// DO NOT CHANGE unless you change it in receiver too
static const uint8_t CSI_SEND_MAC[] = {0x1a, 0x00, 0x00, 0x00, 0x00, 0x00};

#define CHANNEL       11    // fixed channel — must match receiver
#define SEND_FREQ_HZ  100   // packets per second

void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println("\n╔══════════════════════════════════════╗");
    Serial.println(  "║  ESP32-S3 CSI TX — ESP-NOW Mode      ║");
    Serial.println(  "╚══════════════════════════════════════╝");

    // Init NVS (required by WiFi)
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    // Init WiFi in STA mode — no router connection needed
    esp_netif_init();
    esp_event_loop_create_default();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);
    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_storage(WIFI_STORAGE_RAM);
    esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT40);  // 40MHz = more subcarriers
    esp_wifi_start();
    esp_wifi_set_ps(WIFI_PS_NONE);

    // Set to fixed channel
    esp_wifi_set_channel(CHANNEL, WIFI_SECOND_CHAN_BELOW);

    // Set fixed MAC — receiver knows this address
    esp_wifi_set_mac(WIFI_IF_STA, CSI_SEND_MAC);

    // Init ESP-NOW
    esp_now_init();
    esp_now_set_pmk((uint8_t *)"pmk1234567890123");

    // Add broadcast peer
    esp_now_peer_info_t peer = {};
    peer.channel = CHANNEL;
    peer.ifidx   = WIFI_IF_STA;
    peer.encrypt = false;
    memset(peer.peer_addr, 0xff, 6);  // broadcast
    esp_now_add_peer(&peer);

    // Set PHY rate — MCS0 LGI same as Espressif official
    esp_now_rate_config_t rate = {
        .phymode = WIFI_PHY_MODE_HT40,
        .rate    = WIFI_PHY_RATE_MCS0_LGI,
        .ersu    = false,
        .dcm     = false
    };
    esp_now_set_peer_rate_config(peer.peer_addr, &rate);

    Serial.printf("  Channel  : %d\n", CHANNEL);
    Serial.printf("  Rate     : %d Hz\n", SEND_FREQ_HZ);
    Serial.printf("  MAC      : %02x:%02x:%02x:%02x:%02x:%02x\n",
                  CSI_SEND_MAC[0], CSI_SEND_MAC[1], CSI_SEND_MAC[2],
                  CSI_SEND_MAC[3], CSI_SEND_MAC[4], CSI_SEND_MAC[5]);
    Serial.println("  Transmitting...\n");
}

uint32_t count = 0;

void loop() {
    uint8_t peer_addr[] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
    esp_now_send(peer_addr, (uint8_t*)&count, sizeof(count));
    count++;

    static unsigned long last = 0;
    if (millis() - last > 5000) {
        Serial.printf("  Sent %lu packets\n", count);
        last = millis();
    }

    usleep(1000000 / SEND_FREQ_HZ);  // precise timing like official code
}
