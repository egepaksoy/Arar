# Offline English OCR model

- Upstream: https://github.com/tesseract-ocr/tessdata_fast/tree/4.1.0
- File: `eng.traineddata` (Tesseract LSTM English, fast model)
- SHA-256: `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`
- License: Apache-2.0, see the adjacent `LICENSE` copied from upstream.

The model is bundled with Arar. Runtime code never downloads it. The native
engine is provided by the pinned tesserocr wheel in `libs`, with its licenses.
