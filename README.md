# TopRacer-spd — model-delivery speed test

`spdtest.py`(純 stdlib)對正式 event server 逐步計時:出票 → 直傳 PUT → finalize、
舊多部上傳、列表簽 URL、每個 mirror 下載(sha 驗證)、ack。

- 永久使用 `spd-ci` 車頻道:device_id=車名=spd-ci,每次 claim 同一頻道,PIN 用
  `/cars/rotate-pin` 取回 —— 零儲存機密、零垃圾頻道。
- **正確性失敗(HTTP 錯、sha 不符)→ exit 1,build 紅**;速度數字只進 job summary。
- 環境變數:`EVENT_SERVER_URL`(預設正式站)、`SPD_SIZE_MB`(預設 5)、`SPD_CHANNEL`。

CI 掛鉤:TopRacer-svr 與 TopRacer-console 每次 build 都跑(見各 repo workflow 的
`speed-test` job)。

## ecs/run-on-ecs.sh — 從阿里雲主機測(牆內視角)

開一台拋棄式 ECS → 跑 spdtest → 自動刪機(trap EXIT)。香港免實名;深圳需帳號完成
大陸實名登記。憑證:`source ~/.oss_creds` 後執行:

```bash
./ecs/run-on-ecs.sh hk          # 香港
./ecs/run-on-ecs.sh sz          # 深圳(需大陸實名)
```

資源鏈(VPC/交換機/安全組/金鑰)已預建,ID 寫在腳本裡;主機約 ¥0.2/hr,測完即刪。
