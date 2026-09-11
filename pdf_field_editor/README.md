# PDF 欄位文字修改工具

這是一個在本機瀏覽器執行的 Streamlit 工具。它可以上傳 PDF 或 Word (`.docx`) 並擷取發票內容，兩種格式都可搜尋指定欄位、在欄位後方加入文字或取代原有文字。

平台也會擷取並顯示發票的 `Invoice No`、`Item`、`Description`、`Quantity` 與 `Unit Price`。若來源 PDF 的價格已被實際遮蓋，價格會顯示為「無法辨識」，不會利用其他欄位反推。

PDF 上傳後，原始 Item 與 Description 會顯示為 `Vendor Item` 與 `Vendor Description`。平台會自動將不重複的 Vendor Item 傳入內部 Oracle SQL API，並顯示對應的 `ECS Item` 與 `ECS Description`，不需要另外按查詢按鈕。

同一份 PDF 含有多張 Invoice 時，每一頁會重新辨識 Invoice No；若續頁沒有重複顯示號碼，才會沿用上一頁的 Invoice No。

Description 依 Item 同一商品列的版面位置擷取，不限制必須以 `WIFI` 開頭，因此可辨識 `W11` 或其他產品描述。

多行 Description 會先依垂直位置分行，再於每一行依水平位置排序，最後由上到下合併，避免續行文字插入第一行。

## 安裝與啟動

部署包解壓縮後，最簡單的方式是直接雙擊：

`一鍵安裝與啟動.bat`

首次啟動會建立 `.venv` 專案環境、依 `requirements.lock.txt` 安裝固定版本套件，然後開啟瀏覽器。首次安裝需要網路連線。

也可以手動執行：

```powershell
cd D:\python\invoice\pdf_field_editor
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

瀏覽器開啟畫面後：

1. 上傳 PDF。
2. 輸入要尋找的欄位，例如 `SHIPMENT FROM:`。
3. 選擇「加入欄位後方」或「取代原有文字」。
4. 輸入新文字並選擇正確的搜尋結果。
5. 選擇只修改一筆，或修改所有符合欄位。
6. 產生並下載修改後的 PDF。

## 注意事項

- 原始 PDF 不會被覆寫。
- 取代功能使用白色區塊遮蓋原文字，適合白色背景的表單。
- 掃描影像型 PDF 沒有可搜尋文字，需要先進行 OCR。
- 數位簽章 PDF 經修改後，原簽章通常會失效。

## 影像型 PDF 與 OCR

平台會先讀取 PDF 文字層。若頁面只有影像且沒有足夠文字，會自動改用設定於 `ocr_config.json` 的 OCR 服務。

API Key 可在畫面的密碼欄位輸入；若要自動載入，可將 `ocr_api_key.example.txt` 複製為 `ocr_api_key.txt`，並只放入 API Key。平台會直接讀取這個檔案。請勿將 `ocr_api_key.txt` 分享或提交至版本控制。
