/*
 * ESP32-S3 CSI RECEIVER — ESP-NOW (based on official Espressif esp-csi)
 * -----------------------------------------------------------------------
 * No router needed. Listens on fixed channel 11.
 * Filters CSI by hardcoded transmitter MAC — zero interference.
 *
 * Board : ESP32S3 Dev Module
 * Baud  : 921600
 */

#include "nvs_flash.h"
#include "esp_wifi.h"
#include "esp_now.h"
#include "esp_netif.h"
#include <math.h>

// ── Must match transmitter exactly ─────────────────────────────────
static const uint8_t CSI_SEND_MAC[] = {0x1a, 0x00, 0x00, 0x00, 0x00, 0x00};

#define CHANNEL          11
#define MOTION_THRESHOLD 90.0f
#define SMOOTH_WINDOW    10
// ───────────────────────────────────────────────────────────────────

static int   pktCount = 0;
static float varHistory[SMOOTH_WINDOW] = {0};
static int   histIdx = 0;

float rollingAvg() {
    float s = 0;
    for (int i = 0; i < SMOOTH_WINDOW; i++) s += varHistory[i];
    return s / SMOOTH_WINDOW;
}

void wifi_csi_cb(void* ctx, wifi_csi_info_t* info) {
    if (!info || !info->buf || info->len < 2) return;

    // ── Filter: only process packets from our transmitter ───────────
    if (memcmp(info->mac, CSI_SEND_MAC, 6) != 0) return;

    pktCount++;
    int8_t* buf = info->buf;
    int pairs   = info->len / 2;

    float amps[128];
    int   n = 0;
    float sum = 0, sumSq = 0;

    for (int i = 0; i < pairs && i < 128; i++) {
        float I   = (float)buf[i * 2];
        float Q   = (float)buf[i * 2 + 1];
        float amp = sqrtf(I*I + Q*Q);
        if (amp < 0.5f) continue;
        amps[n++] = amp;
        sum      += amp;
        sumSq    += amp * amp;
    }
    if (n < 4) return;

    float mean     = sum / n;
    float variance = (sumSq / n) - (mean * mean);
    int   rssi     = info->rx_ctrl.rssi;

    varHistory[histIdx++ % SMOOTH_WINDOW] = variance;
    float smoothed = rollingAvg();
    bool  motion   = smoothed > MOTION_THRESHOLD;

    Serial.printf("CSI_DATA,%d,%d,%.2f,%.2f,%.2f,%d,[",
        pktCount, rssi, mean, variance, smoothed, motion ? 1 : 0);
    for (int i = 0; i < n; i++) {
        Serial.printf("%.1f", amps[i]);
        if (i < n-1) Serial.print(' ');
    }
    Serial.println("]");
}

void setup() {
    Serial.begin(921600);
    delay(500);

    Serial.println("\n╔══════════════════════════════════════╗");
    Serial.println(  "║  ESP32-S3 CSI RX — ESP-NOW Mode      ║");
    Serial.println(  "╚══════════════════════════════════════╝");

    // NVS
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }

    // WiFi — no router needed
    esp_netif_init();
    esp_event_loop_create_default();
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    esp_wifi_init(&cfg);
    esp_wifi_set_mode(WIFI_MODE_STA);
    esp_wifi_set_storage(WIFI_STORAGE_RAM);
    esp_wifi_set_bandwidth(WIFI_IF_STA, WIFI_BW_HT40);
    esp_wifi_start();
    esp_wifi_set_ps(WIFI_PS_NONE);

    // Fixed channel — same as transmitter
    esp_wifi_set_channel(CHANNEL, WIFI_SECOND_CHAN_BELOW);

    // Promiscuous mode — required for CSI
    esp_wifi_set_promiscuous(true);

    // ESP-NOW
    esp_now_init();
    esp_now_set_pmk((uint8_t *)"pmk1234567890123");

    esp_now_peer_info_t peer = {};
    peer.channel = CHANNEL;
    peer.ifidx   = WIFI_IF_STA;
    peer.encrypt = false;
    memset(peer.peer_addr, 0xff, 6);
    esp_now_add_peer(&peer);

    // CSI config
    wifi_csi_config_t csi_cfg = {
        .lltf_en           = true,
        .htltf_en          = true,
        .stbc_htltf2_en    = true,
        .ltf_merge_en      = true,
        .channel_filter_en = true,
        .manu_scale        = false,
        .shift             = false,
    };
    esp_wifi_set_csi_config(&csi_cfg);
    esp_wifi_set_csi_rx_cb(wifi_csi_cb, NULL);
    esp_wifi_set_csi(true);

    Serial.printf("  Channel          : %d\n", CHANNEL);
    Serial.printf("  Filtering MAC    : %02x:%02x:%02x:%02x:%02x:%02x\n",
                  CSI_SEND_MAC[0], CSI_SEND_MAC[1], CSI_SEND_MAC[2],
                  CSI_SEND_MAC[3], CSI_SEND_MAC[4], CSI_SEND_MAC[5]);
    Serial.printf("  Motion threshold : %.0f\n\n", MOTION_THRESHOLD);
    Serial.println("  Waiting for transmitter packets...\n");
}

void loop() {
    static unsigned long last = 0;
    if (millis() - last > 5000) {
        Serial.printf("# Stats: %d CSI packets from TX\n", pktCount);
        last = millis();
    }
    delay(1);
}
