# Arar

Python ile geliştirilmiş, tamamen çevrimdışı çalışan Türkçe PDF ayırma uygulaması.
Belge tarayıcısının bilgisayara kaydettiği PDF’lerdeki **Receiving Report No** barkodunu
ve mühürleri inceleyerek kapak ve devam sayfalarını gruplar, ayrı PDF’ler oluşturur.

## Özellikler

- Yerel PDF’leri içe aktarma, seçili dosyayı kaldırma ve çalışma alanındaki dosyaları temizleme.
- Sayfa önizlemesi, %25–%400 yakınlaştırma, Ctrl + fare tekerleği ve sürükleyerek gezinme.
- Code 39 ve Code 128 barkodlarını okuma; ürün barkodları yerine Receiving Report başlığını doğrulama.
- Mavi, siyah, soluk/renksiz ve birden fazla mühür türü için kapak değerlendirmesi.
- **Analiz sürerken tamamlanan sayfaları inceleme ve kullanıcı kararı verme.** Arka plandaki sonuçlar manuel kararları değiştirmez.
- İşlenen sayfalarda yeşil tik, kullanıcı incelemesi gerekenlerde kırmızı işaret.
- Sırayla gruplama veya art arda kapaklara ortak devam sayfalarını ekleme.
- Sonraki Receiving Report barkodlarında isteğe bağlı duraklama.
- Barkod adıyla PDF kaydı, çakışan isimlere numara ekleme ve JSON işlem raporu.

## Gereksinimler

- Python 3.10 veya üzeri.
- Tkinter içeren bir Python kurulumu ve masaüstü oturumu.
- `requirements.txt` içindeki Pillow, NumPy, pypdf ve pypdfium2 paketleri.

Windows için `Başlat.bat` bulunur. EXE veya Python çalışma ortamı depoya dahil değildir.

## Çevrimdışı kurulum ve çalıştırma

Python’u ve bilgisayarınızın Python sürümüne/mimarisine uygun wheel dosyalarını yerel
kurulum ortamınızdan sağlayın. Wheel dosyalarını `wheelhouse` klasörüne yerleştirin:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\wheelhouse -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Sonraki açılışlarda **Başlat.bat** dosyasına çift tıklayabilirsiniz.
Uygulama bağımlılık indirmez ve çalışırken ağ kullanmaz.

## Kullanım

1. **PDF ekle** ile yerel dosyaları seçin.
2. **Analizi başlat** düğmesine basın.
3. Analiz diğer sayfalarda sürerken tamamlanan sayfaları seçip inceleyin. Henüz işlenmeyen sayfalarda karar düğmeleri kapalıdır.
4. Gerekirse numarayı düzeltin ve **Kapak olarak onayla** veya **Devam sayfası olarak işaretle** seçeneğini kullanın.
5. Tüm sayfalar bir belgeye bağlandığında **Belgeleri kaydet** ile yerel bir klasör seçin.

**Dosyaları temizle**, eklenmiş dosyaları ve oturumdaki kararları çalışma alanından kaldırır.
Kaynak dosyalar diskte kalır. Dosya kaldırma ve temizleme, aktif işlem bittikten sonra kullanılabilir.
Analizi durdurmak için **Durdur** düğmesini kullanabilirsiniz.

Detaylı kurallar ve ekran kontrolleri: [KULLANIM.md](KULLANIM.md).

## Çevrimdışı çalışma

Uygulamada web sunucusu, bulut hizmeti, telemetri veya güncelleme kontrolü bulunmaz.
Başlangıçta Python soket oluşturma, bağlantı açma, dinleme ve DNS çözümleme engellenir.
URL, UNC ağ yolu, eşlenmiş ağ sürücüsü ve ağ hedefi olan dosya bağlantıları kabul edilmez.

PDF’ler farklı kaynak dosyalar arasında otomatik birleştirilmez. Belirsiz veya
gruplandırılmamış sayfalar sessizce atılmaz. Kaynak dosya analizden sonra değiştirilirse
kayıt engellenir. Kayıt sırasında mevcut PDF’lerin üzerine yazılmaz.

## Tanımanın kapsamı

Başlık ve mühür tespiti `assets` klasöründeki yerel görsel şablonları kullanır.
Tam sayfa taramalarda barkod okuma ve 90 derece yön düzeltme desteklenir;
mühür sonucu kullanıcı onayı gerektirir. Farklı mühür tasarımları, yazı tipleri,
eğik veya düşük kaliteli taramalar manuel inceleme gerektirebilir.

Doğrudan tarayıcı cihazı bağlantısı, klasör izleme, OCR, parola korumalı PDF açma
ve oturum geri yükleme bu sürümün kapsamında değildir. Ayarlar yerel `.arar`
klasörüne kaydedilir; sayfa kararları oturum içinde tutulur.

## Testler

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Temel testler gruplama, barkod doğrulama, PDF kaydı, değişmiş kaynakları reddetme
ve ağ engelini kontrol eder. Test PDF’leri geçici klasörlerde oluşturulur.

Sağlanan belge örnekleri depoya dahil değildir. Bunları kendi bilgisayarınızda
`Örnek/Kolay` altına koyarsanız belge örneklerine bağlı entegrasyon testleri de çalışır;
bulunmazlarsa ilgili testler açıkça atlanır. **Örnekleri aç** düğmesi yerel `Örnek`
klasörünü kullanır.

Masaüstü arayüz testlerini de çalıştırmak için:

```powershell
$env:ARAR_UI_TESTS = '1'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:ARAR_UI_TESTS
```

Arayüz testleri analiz devam ederken karar vermeyi, manuel kararların korunmasını
ve dosyaları temizleme işlemini doğrular. Görünür bir masaüstü oturumu gerekir.

## Proje yapısı

```text
main.py              Uygulama başlangıcı ve ağ engeli
arar/app.py          Masaüstü arayüzü ve arka plan işlem kuyruğu
arar/models.py       Sayfa kararları, ayarlar ve belge grupları
arar/detection.py    Yerel barkod/başlık/mühür incelemesi
arar/barcodes.py     Code 39 ve Code 128 okuyucusu
arar/exporter.py     PDF kaydı ve işlem raporu
arar/offline.py      Ağ engeli ve yerel dosya yolu doğrulaması
assets/              Gerekli görsel şablonlar
tests/               Temel ve isteğe bağlı arayüz testleri
```

## GitHub’a yükleme

`.gitignore`; yerel ayarları, PDF’leri, örnek belgeleri, çıktı raporlarını,
geçici dosyaları, Python ortamlarını ve yerel wheel dosyalarını dışarıda tutar.
Gerekli görsel şablonlar depoya dahildir. `.gitattributes` metin dosyalarının
satır sonlarını düzenler.

GitHub’da boş bir depo oluşturduktan sonra aşağıdaki `DEPO_ADRESI` yerine
GitHub’ın gösterdiği depo adresini yazın. Bu komutları proje klasöründe çalıştırın:

```powershell
git status
git add .
git commit -m "Arar: çevrimdışı PDF ayırma uygulaması"
git remote add origin "DEPO_ADRESI"
git push -u origin main
```

Yeni bir kopyayı sıfırdan Git deposuna dönüştürüyorsanız önce `git init -b main` çalıştırın.
