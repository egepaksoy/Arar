# Yerel varlıklar

Bu görüntüler proje için sağlanan belge örneklerinden elde edilmiştir.

- `receiving_report.png`: Receiving Report No başlığı ve barkodu. Kurulum ve testlerde
  OCR ile barkod okumanın çalıştığını doğrulamak için kullanılır.
- `stamp_blue_1.png` – `stamp_blue_5.png`, `stamp_faint.png`, `stamp_black.png`:
  mavi, soluk/renksiz ve siyah mühür örnekleri. Testlerde mühür bulucunun bu
  mühürleri doğru renkte bulduğu denetlenir.

Uygulama mühürleri ve barkodu şablonla eşleştirmez: mühürler yuvarlak halka
şekliyle, Receiving Report barkodu da hemen yanındaki başlık yazısıyla bulunur.
Bu yüzden farklı numaralı barkodlar ve farklı mühür tasarımları da tanınır.
`tessdata/eng.traineddata` OCR dil modelidir ve uygulamanın çalışması için gereklidir.
