# 發票 PDF／Word 處理平台 Roadmap

更新日期：2026-09-10

## 專案目標

建立可在 Windows 本機瀏覽器使用的發票處理平台，支援 PDF 與 Word 上傳、發票資料擷取、OCR 辨識、指定欄位修改及一鍵部署。

## 已完成功能

### 檔案與資料擷取

- [x] 上傳 PDF (`.pdf`) 與 Word (`.docx`)
- [x] 顯示目前上傳的檔案名稱
- [x] 顯示 Invoice No、Item、Description、Quantity、Unit Price
- [x] 支援同一檔案包含多張 Invoice
- [x] 支援多行及非 WIFI 開頭的 Description
- [x] 支援不同 Word 欄位名稱，例如 `INV NO.`、`INV-QTY`、`PRICE`
- [x] PDF Item 若以 `(INTEL)` 結尾，顯示時自動移除該字樣
- [x] PDF 欄位名稱調整為 Cust Item 與 Cust Description
- [x] Cust Item 可透過內部 Oracle SQL API 查詢 ECS Item 與 ECS Description
- [x] PDF 上傳完成後自動查詢 ECS Item 與 ECS Description，不需另外按按鈕
- [x] Oracle 查無資料、多筆對應及 API 失敗時顯示明確狀態
- [x] 顯示資料來源

### OCR

- [x] 自動偵測影像型 PDF 並改用 OCR
- [x] Word 找不到一般表格時，擷取大型內嵌圖片進行 OCR
- [x] 略過小型 Logo 與裝飾圖片
- [x] OCR URL、模型、逾時與重試次數可由設定檔控制
- [x] API Key 可由環境變數、`ocr_api_key.txt` 或平台畫面輸入
- [x] 已遮蔽價格不進行反推

### PDF 欄位修改

- [x] 搜尋指定欄位
- [x] 在欄位後方加入文字
- [x] 取代原有文字
- [x] 選擇單筆或修改全部符合欄位
- [x] 調整位置與字體大小
- [x] 下載修改後的 PDF

### Word 欄位修改

- [x] 搜尋本文、表格、頁首與頁尾
- [x] 在欄位後方加入文字或取代原有文字
- [x] 支援欄位名稱與欄位值位於相鄰儲存格
- [x] 選擇單筆或修改全部符合欄位
- [x] 盡量保留段落與文字格式
- [x] 下載修改後的 Word (`.docx`)

### 平台與部署

- [x] Streamlit 本機網頁介面
- [x] Windows 一鍵安裝與啟動
- [x] 自動建立專案專用 `.venv`
- [x] 使用 `requirements.lock.txt` 固定主要套件版本
- [x] 首次執行自動安裝套件並開啟平台
- [x] 建立可分享的 ZIP 部署包
- [x] 部署包排除 OCR API Key、記錄與快取檔案

## 目前限制

- 舊版 Word `.doc` 尚未支援，需先另存為 `.docx`。
- OCR 需要連線至設定的內部 OCR 服務。
- 首次部署需要網路，且 Windows 電腦必須先安裝 Python 3。
- PDF 修改採用新增文字或白色遮蓋方式，複雜背景可能需要人工調整。
- 修改數位簽章 PDF 後，原簽章通常會失效。
- Word 特殊圖形、SmartArt 或非標準物件可能無法完整搜尋及修改。

## 下一階段

### P1

- [ ] PDF／Word 原始頁面預覽
- [ ] 修改前後並排預覽
- [ ] 匯出發票資料為 Excel 或 CSV
- [ ] 批次上傳與批次下載
- [ ] 改善 OCR 連線檢查及錯誤分類

### P2

- [ ] 保存常用欄位與輸入文字範本
- [ ] 支援更多供應商發票版型
- [ ] 可在平台人工修正擷取結果
- [ ] 顯示成功、待確認與失敗統計
- [ ] 建立不包含金鑰及機密價格的處理紀錄

### P3

- [ ] 評估離線 OCR
- [ ] 評估免安裝 Python 的 Windows 獨立執行版本
- [ ] 建立多種發票樣本的自動回歸測試
- [ ] 加入版本號與更新通知

## 主要部署檔案

- 程式目錄：`D:\python\invoice\pdf_field_editor`
- 一鍵啟動：`pdf_field_editor\一鍵安裝與啟動.bat`
- 固定套件版本：`pdf_field_editor\requirements.lock.txt`
- OCR 設定：`pdf_field_editor\ocr_config.json`
- 最新部署包：`D:\python\invoice\dist\invoice_platform_20260910.zip`
