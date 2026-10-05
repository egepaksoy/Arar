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
- Kapak işaretleme onay sorusunu ayarlardan açma veya kapatma.
- PDF analizi tamamlandığında ayarlardan açılıp kapatılabilen “Tarama bitti” bildirimi.
- Barkod adıyla PDF kaydı, çakışan isimlere numara ekleme ve JSON işlem raporu.

## Gereksinimler

- Hazırlanan `libs/` kopyası için CPython 3.12.x, Windows x64.
- Tkinter içeren bir Python kurulumu ve masaüstü oturumu.
- Projeyle birlikte taşınan dolu `libs/` klasörü (Pillow, NumPy, pypdf ve pypdfium2).

Windows için `baslat.bat`, Unix / Linux / macOS için `baslat.sh` bulunur.
Windows binary paketleri diğer işletim sistemlerinde çalışmaz; bu platformlar için ayrı libs hazırlığı gerekir.
EXE veya Python çalışma ortamı depoya dahil değildir.

## Çevrimdışı kurulum ve çalıştırma

Hedef bilgisayara `libs/` ve `assets/` dahil proje klasörünü kopyalayın. Uyumlu
Python kurulumu ile hedefte yalnızca şu komutu çalıştırın; pip veya internet gerekmez:

```bat
python main.py
```

Windows’ta **baslat.bat** dosyasına çift tıklamak, Unix’te **baslat.sh** çalıştırmak yeterlidir.
Başlatıcı uyumlu Python’u seçer ve `prepare_local_libs.py --launch` üzerinden
yerel paketleri kontrol ederek uygulamayı açar. Eksik veya uyumsuz paketler varsa
`wheelhouse/` içindeki uygun wheel dosyalarından ya da mevcut kurulu paketlerden
otomatik hazırlık yapar. Bu açılış akışı internetten paket indirmez.
Paketleri geliştirme bilgisayarında hazırlamak için Windows’ta **setup_offline_libs.bat**,
Linux/Unix/macOS’ta **setup_offline_libs.sh** kullanılır.
Mevcut dolu `libs/` korunur; `--replace` seçeneği doğrulanan yeni kopyayı yerleştirirken
eski klasörü yedekler. Kurulu paketlerden indirimsiz hazırlık için `--from-installed`,
yerel wheel dosyaları için `--wheelhouse wheelhouse` seçenekleri bulunur.
Doğrudan `main.py` mevcut yerel paketleri kullanır. Uygulama çalışırken ağ kullanmaz.

Hazırlama, taşıma ve Python uyumluluğu: [README_OFFLINE.md](README_OFFLINE.md).

## Kullanım

1. **PDF ekle** ile yerel dosyaları seçin.
2. **Analizi başlat** düğmesine basın.
3. Analiz diğer sayfalarda sürerken tamamlanan sayfaları seçip inceleyin. Henüz işlenmeyen sayfalarda karar düğmeleri kapalıdır.
4. Gerekirse numarayı düzeltin ve **Kapak olarak onayla** veya **Devam sayfası olarak işaretle** seçeneğini kullanın.
5. Tüm sayfalar bir belgeye bağlandığında **Belgeleri kaydet** ile yerel bir klasör seçin.

**Dosyaları temizle**, eklenmiş dosyaları ve oturumdaki kararları çalışma alanından kaldırır.
Kaynak dosyalar diskte kalır. Dosya kaldırma ve temizleme, aktif işlem bittikten sonra kullanılabilir.
Analizi durdurmak için **Durdur** düğmesini kullanabilirsiniz.

**Ayarlar → Kapak işaretleme → Kapak olarak işaretlerken onay sor** seçeneği
varsayılan olarak açıktır. Kapatıp **Ayarları kaydet** düğmesine bastığınızda
manuel kapak işaretleme onay sorusu gösterilmez. Seçiminiz sonraki açılışlarda korunur;
kapak numarası girme gerekliliği devam eder.

**Ayarlar → Tamamlanma bildirimi → Tarama bittiğinde uyarı göster** seçeneği
varsayılan olarak açıktır. PDF sayfalarının analizi tamamlandığında bildirim gösterir;
durdurulan analizde gösterilmez. Seçiminiz kaydedilir.

Çevrimdışı kullanım ve sorun giderme: [README_OFFLINE.md](README_OFFLINE.md).

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
python -S -m unittest discover -s tests -v
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
python -S -m unittest discover -s tests -v
Remove-Item Env:ARAR_UI_TESTS
```

Arayüz testleri analiz devam ederken karar vermeyi, manuel kararların korunmasını
ve dosyaları temizleme işlemini doğrular. Görünür bir masaüstü oturumu gerekir.

## Proje yapısı

```text
main.py              Uygulama başlangıcı ve ağ engeli
local_dependencies.py Proje içindeki libs paketlerini yükleme
libs/                Hazır üçüncü taraf paketler ve native dosyalar
setup_offline_libs.bat Geliştirme bilgisayarında bağımlılık hazırlığı
setup_offline_libs.sh Linux/Unix/macOS için bağımlılık hazırlığı
prepare_local_libs.py Güvenli hazırlık, doğrulama ve yedekleme
README_OFFLINE.md    Taşıma, çalıştırma ve uyumluluk rehberi
baslat.bat           Windows başlatma betiği
baslat.sh            Unix / Linux / macOS başlatma betiği
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
Gerekli görsel şablonlar ve `libs/` paketleri depoya dahildir. `.gitattributes` metin
dosyalarının satır sonlarını düzenler; libs içindeki üçüncü taraf dosyaların içeriğini korur.

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
