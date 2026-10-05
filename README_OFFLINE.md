# Offline Installation

Arar, üçüncü taraf paketleri proje içindeki `libs/` klasöründen yükler.
Bu klasör dolu olarak projeyle birlikte taşınır. Hedef bilgisayarda internet,
`pip install`, sanal ortam veya sistem ortamına kurulmuş üçüncü taraf paket gerekmez.

## Requirements

- **CPython 3.12.x, Windows x64**, Tkinter/Tcl/Tk içeren normal bir Python kurulumu.
- Hazırlanmış `libs/` ve mevcut `assets/` klasörleri dahil proje dosyalarının tamamı.
- Kaynak PDF’ler ve çıktı klasörleri yerel diskte olmalıdır.

Mevcut paketler **Python 3.12.14, Windows AMD64 / 64 bit** ile hazırlanıp sınandı.
Python çalışma ortamı ve Tkinter standart kütüphanesi `libs/` içine dahil edilmez.
Standart Python kurulumu bunları sağlar; yalnızca embeddable Python ZIP’i yeterli değildir.

| requirements.txt paketi | Import adı | Hazırlanan sürüm | Görevi |
| --- | --- | --- | --- |
| Pillow | PIL | 12.3.0 | Görseller ve Tkinter önizlemesi |
| numpy | numpy | 2.3.5 | Barkod ve mühür görüntü hesaplamaları |
| pypdf | pypdf | 6.10.0 | Orijinal PDF sayfalarını birleştirme |
| pypdfium2 | pypdfium2, pypdfium2_raw | 5.13.0 | PDF sayfalarını görüntüleme |

Bu sürümlerin Python 3.12 üzerinde ek zorunlu üçüncü taraf bağımlılığı yoktur.
`pathlib`, `json`, `socket`, `threading`, `tkinter` gibi standart modüller requirements’a eklenmez.

## Preparing Local Dependencies

İnternetten ilk paket hazırlığı **yalnızca geliştirme bilgisayarında** uygulanır.
Mevcut `libs/` hazırsa ek işlem gerekmez. Başlatıcılar eksik paketler için yalnızca
yerel wheel dosyalarını veya mevcut kurulu paketleri otomatik kullanabilir.

İnterneti olan bilgisayarda, CPython 3.12 ile:

```bat
setup_offline_libs.bat
```

Linux/Unix/macOS üzerinde aynı hazırlık için:

```sh
./setup_offline_libs.sh
```

Çalıştırma izni korunmamış bir kopyada `sh setup_offline_libs.sh` da kullanılabilir.
Betik CPython 3.11 veya üzerini otomatik bulur ve aynı `prepare_local_libs.py`
mekanizmasını kullanır. Paketler hazırlığın yapıldığı işletim sistemi ve mimariye göre kurulur.

Betik `python -m pip install -r requirements.txt -t ...` mantığıyla paketleri
proje içindeki geçici bir klasöre kurar; kaynak koddan derleme yerine hazır binary
wheel dosyalarını ister. İzole bir Python işleminde import, görüntü, NumPy hesaplama
ve PDF render kontrollerinden geçerse klasörü `libs/` olarak yerleştirir.
Mevcut ortamla uyumlu dolu bir `libs/` klasörünü varsayılan olarak değiştirmez.
Başka işletim sistemi, mimari veya Python sürümünden taşınmış bir bundle varsa
yeni kopyayı doğruladıktan sonra eskisini yedekleyerek otomatik değiştirir.

Paketler aynı Python ortamında zaten kuruluysa **hiçbir indirme yapmadan**:

```bat
setup_offline_libs.bat --from-installed
```

Bu seçenek kesin sürümleri kontrol eder ve paketlerin kayıtlı dosyalarını, DLL/PYD
dosyalarını, lisanslarını ve paket metadata’sını kopyalar. Kopyaların dosya içeriklerini
doğrular. Dış ortamı işaret eden, uygulamanın kullanmadığı konsol başlatıcılarını ve
Python bytecode önbelleklerini taşımaz; paket dosya kayıtlarını yeni kopyaya göre yazar.
Bu projedeki mevcut `libs/` bu yöntemle hazırlanmıştır.

Yerel wheel arşivinden, ağ kullanmadan hazırlamak için:

```bat
setup_offline_libs.bat --wheelhouse wheelhouse
```

Linux/Unix için eşdeğer çevrimdışı seçenekler ve güvenli güncelleme:

```sh
./setup_offline_libs.sh --from-installed
./setup_offline_libs.sh --wheelhouse wheelhouse
./setup_offline_libs.sh --replace --wheelhouse wheelhouse
```

Tüm seçenekler, boşluk içeren yollar dahil Python hazırlık scriptine aktarılır.
Gerekirse `ARAR_PYTHON=/uygun/python3.12 ./setup_offline_libs.sh --from-installed`
ile yorumlayıcı seçilebilir. İnternetsiz hazırlıkta ilgili Unix platformuna uygun
kurulu paketler veya wheel dosyaları gerekir; Windows paketleri kullanılamaz.

Bu seçenek pip’e `--no-index` ve `--find-links` verir. Wheel klasöründe Python 3.12,
hazırlığın yapıldığı işletim sistemi/mimari için uyumlu dosyalar bulunmalıdır.
Pip yalnızca wheel/çevrimiçi kurulum seçilen hazırlık adımında gereklidir.

Birden fazla Python varsa PowerShell’de uygun hazırlık yorumlayıcısını seçebilirsiniz:

```powershell
$env:ARAR_PYTHON = (Get-Command python).Source
.\setup_offline_libs.bat --from-installed
```

Alternatif olarak seçtiğiniz Python ile doğrudan `prepare_local_libs.py` çalıştırabilirsiniz.
Script yolları bulunduğu proje klasöründen hesaplar; başka çalışma dizininden çağrılabilir.

## Project Structure

```text
Arar/
├── main.py
├── local_dependencies.py       Merkezi bağımlılık yükleme ve uyumluluk kontrolü
├── libs/
│   ├── PIL/
│   ├── numpy/
│   ├── numpy.libs/             NumPy'nin yerel DLL dosyaları
│   ├── pypdf/
│   ├── pypdfium2/
│   ├── pypdfium2_raw/          pdfium.dll dahil
│   ├── *.dist-info/            Sürüm bilgileri ve lisanslar
│   └── arar_bundle.json        Python/platform/mimari ve paket sürümleri
├── arar/
├── assets/
├── tests/
├── requirements.txt
├── setup_offline_libs.bat
├── setup_offline_libs.sh
├── prepare_local_libs.py
└── README_OFFLINE.md
```

Mevcut ayarlar `.arar/settings.json` dosyasında kalır. Bu geçiş ayrı bir `config/`
klasörü oluşturmaz; uygulamanın ayar, dosya işleme ve arayüz davranışını korur.
`libs/` Git tarafından dışlanmaz. Lisanslar da paketin parçasıdır.
`__pycache__`, `.pyc`, hazırlık klasörleri ve eski paket yedekleri dışlanır.

## Running Offline

Projenin tamamını USB/harici disk ile hedef bilgisayara kopyalayın. Terminalde
proje klasöründen yalnızca:

```bat
python main.py
```

Tek adımlı önerilen açılış: Windows’ta **baslat.bat** dosyasına çift tıklayın;
Unix’te **baslat.sh** dosyasını çalıştırın (`sh baslat.sh` da kullanılabilir).
Unix başlatıcı CPython 3.11 veya üzerini otomatik arar; Windows başlatıcı hazır
Windows bundle için CPython 3.12’yi tercih eder. Seçilen Python’un Tkinter desteği
ayrı kontrol edilir. Başlatıcı
`prepare_local_libs.py --launch` çağırır. Hazır yerel paketler doğrulanınca uygulamayı açar.
Windows’ta hazırlık bitince uygulama konsolsuz açılır.

Eksik veya uyumsuz `libs/` için başlatıcı önce yerel `wheelhouse/` klasörünü,
bu kaynak yoksa aynı sürümlerdeki mevcut kurulu paketleri kullanarak otomatik hazırlık
yapar. Eski klasör korunur. Wheel kullanırken pip yalnızca `--no-index` ile yerel
dosyalara erişir; açılışta internet kullanılmaz. Hazır `libs/` varsa pip gerekmez.
Hiçbir yerel kaynak bulunamazsa anlaşılır hata gösterir; internetten indirme yapmaz.

Windows’ta mevcut bundle için CPython 3.12 x64 gerekir. Unix’te ilgili işletim
sistemi/mimari için yerel paketler veya uygun wheel dosyaları bulunmalıdır;
Windows DLL’leri Unix’te kullanılamaz. Uyumlu Python başlatıcıyı çalıştırmak için,
Tkinter/Tcl/Tk ise uygulama ve paket doğrulaması için gereklidir; işletim sistemi
kurulumları otomatik indirilmez.

`main.py` ve `arar` paketinin giriş noktası aynı `local_dependencies.py` mekanizmasını
kullanır. `libs/` import yolunun başına eklenir; kritik paketlerin gerçekten bu klasörden
geldiği kontrol edilir. Eksik yerel paket varsa sistemdeki kopyaya sessizce geçilmez.

Sistem site-packages klasörünü devre dışı bırakarak da çalıştırabilirsiniz:

```bat
python -S main.py
```

Tüm testler (Tkinter arayüz testleri dahil):

```powershell
$env:ARAR_UI_TESTS = '1'
python -S -m unittest discover -s tests -v
Remove-Item Env:ARAR_UI_TESTS
```

## Updating Dependencies

Geliştirme bilgisayarında requirements’taki kesin sürümleri bilinçli olarak güncelleyin:

```bat
setup_offline_libs.bat --replace
```

Kurulu paketleri kullanacaksanız `--replace --from-installed`, yerel wheel arşivi
kullanacaksanız `--replace --wheelhouse wheelhouse` seçeneklerini birlikte verin.
Yeni paketler **önce doğrulanır**. Başarılıysa eski klasör `libs.backup-...` adıyla
korunur. İndirme, kurulum veya doğrulama başarısız olursa mevcut `libs/` değiştirilmez.
Güncelleme öncesinde çalışan Arar pencerelerini kapatın; Windows açık DLL dosyalarını
kilitleyebilir. Güncellenmiş projeyi hedef bilgisayara yeniden taşıyın.

## Python Version Compatibility

Hazırlık scripti CPython **3.11 veya üzerini** kabul eder. Seçilen Python sürümü ve
platform için requirements’taki sürümlerin uyumlu binary wheel dosyaları bulunmalıdır;
uygun wheel bulunamazsa kurulum bunu bildirir. Mevcut kopya CPython 3.12 Windows x64
ile sınanmıştır. Bu bundle Windows x64 içindir; Windows ARM64, 32 bit Python,
Python 3.11/3.13 veya Linux/macOS üzerinde bu binary dosyalar kullanılamaz.
Bu ortamlar için uygun yorumlayıcıyla ayrı paket hazırlığı ve test gerekir.

Pillow ve NumPy `.pyd` dosyaları Python minor sürümüne bağlıdır. `numpy.libs/`
OpenBLAS ve yardımcı DLL’leri içerir. PDFium DLL’i `pypdfium2_raw/` içindedir.
`arar_bundle.json` farklı Python/platform/mimariyi native import öncesinde reddeder.
Manifest olmadan elle hazırlanmış bir libs kopyasında bu ek kontrol yapılamaz;
dağıtım için hazırlık scriptini kullanın.

## Troubleshooting

- **Yerel bağımlılık klasörü bulunamadı / paketler eksik:** `libs/` boş veya eksik
  kopyalanmıştır. Geliştirme bilgisayarında hazırlayın ve tüm klasörü yeniden taşıyın.
  Uygulama eksik paketleri otomatik indirmez.
- **Paketler bu Python ile uyumlu değil:** `python --version` ve Python mimarisini
  kontrol edin. Bu kopya için CPython 3.12 x64 kullanın.
- **DLL load failed:** Önce bütün `libs/` dosyalarının taşındığını ve Python mimarisini
  kontrol edin. Normal Windows/Python çalışma zamanı veya Visual C++ çalışma zamanı
  eksikse ilgili çevrimdışı kurulum ortamını kullanın. Python ve işletim sistemi DLL’leri
  bu paket kopyasının kapsamı dışındadır.
- **No module named tkinter / TclError:** Tcl/Tk içeren normal bir Python kurulumu gerekir.
- **Python bulundu, ancak Tkinter/Tcl/Tk yüklenemedi:** Python sürümü ile Tkinter
  desteği ayrı kontrol edilir. Tkinter bir pip paketi değildir; seçilen yorumlayıcıya
  uygun sistem Tcl/Tk desteği kurulmalıdır. İnternetsiz Linux’ta dağıtıma/sürüme uygun
  sistem kurulum paketleri yerel ortamdan sağlanmalıdır. `libs/` hazırlığı bunu indirmez.
- **libs zaten dolu:** Yenileme bilinçli olarak engellenmiştir; geliştirme bilgisayarında
  `--replace` ile eski klasör yedeği korunarak güncelleyin.
- **Kayıt klasörü bulunamıyor:** Projeyle eski `.arar` ayarlarını taşıdıysanız yeni bilgisayarda
  mevcut bir yerel kayıt klasörü seçin. Ayarlar hâlâ mevcut sistemde tutulur.

Uygulama font, model, tokenizer veya ağırlık dosyası indirmez. Barkod ve mühür tespiti
yerel kodu ve `assets/` şablonlarını kullanır. Fontlar işletim sistemindendir.
Ağ engeli normal `main.py` açılışında korunur. Başlatıcıların otomatik hazırlığı
yerel kaynaklarla sınırlıdır; çevrimiçi kurulum yalnızca açıkça çağrılan geliştirme
kurulum scriptinde bulunur. Parola korumalı PDF desteği ve pypdf’in opsiyonel şifreleme
paketleri bu sürüme dahil değildir.
