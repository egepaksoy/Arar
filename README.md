# Arar

Python ile geliştirilmiş, tamamen çevrimdışı çalışan Türkçe PDF ayırma uygulaması.
Belge tarayıcısının bilgisayara kaydettiği PDF’lerdeki **Receiving Report No** barkodunu
ve mühürleri inceleyerek kapak ve devam sayfalarını gruplar, ayrı PDF’ler oluşturur.

## Özellikler

- Yerel PDF’leri içe aktarma, seçili dosyayı kaldırma ve çalışma alanındaki dosyaları temizleme.
- Ayarlardan seçilen klasör ve alt klasörlerindeki örnek PDF’leri açma.
- Sayfa önizlemesi, %25–%400 yakınlaştırma, Ctrl + fare tekerleği ve sürükleyerek gezinme.
- Önce OCR ile Receiving Report No yazısını bulma, altında dar ve gerekirse geniş alanda Code 39 / Code 128 barkodunu okuma. Yazı bulunamazsa yerel görsel şablonla arama.
- Mavi, siyah, soluk/renksiz ve birden fazla mühür türü için kapak değerlendirmesi.
- **Analiz sürerken tamamlanan sayfaları inceleme ve kullanıcı kararı verme.** Arka plandaki sonuçlar manuel kararları değiştirmez.
- İşlenen sayfalarda yeşil tik, kullanıcı incelemesi gerekenlerde kırmızı işaret.
- Sırayla gruplama veya art arda kapaklara ortak devam sayfalarını ekleme.
- Eklenip kaldırılabilen birden fazla yerel PDF klasörünü izleme, otomatik analiz ve kalıcı onay sırası.
- İnceleme gerekmeyen otomatik taramaları ayara bağlı arşivleme, tarama listesinden tek tek veya topluca kaldırma.
- Kapak işaretleme onay sorusunu ayarlardan açma veya kapatma.
- PDF analizi tamamlandığında ayarlardan açılıp kapatılabilen “Tarama bitti” bildirimi.
- Barkod adıyla PDF kaydı, çakışan isimlere numara ekleme ve JSON işlem raporu.
- Kullanıcı onayından sonra ana arşiv altında tarih/saat klasörüne kayıt.

## Gereksinimler

- Hazırlanan `libs/` kopyası için CPython 3.12.x, Windows x64.
- Tkinter içeren bir Python kurulumu ve masaüstü oturumu.
- Projeyle birlikte taşınan dolu `libs/` klasörü (Pillow, NumPy, pypdf, pypdfium2 ve tesserocr) ve `assets/tessdata/eng.traineddata` OCR dil modeli.

Windows için `baslat.bat`, Unix / Linux / macOS için `baslat.sh` bulunur.
Windows binary paketleri diğer işletim sistemlerinde çalışmaz; bu platformlar için ayrı libs hazırlığı gerekir.
EXE veya Python çalışma ortamı depoya dahil değildir.

## Çevrimdışı kurulum ve çalıştırma

Windows 10/11 x64 için Python dahil tek dosyalı kurulum paketi hazırlanabilir.
`dist/Arar-Setup-2026.10.30.5-win-x64.exe` dosyasını hedef bilgisayara taşıyıp **Kur**
düğmesine basın. Python, Tkinter, yerel kütüphaneler ve mühür şablonları pakettedir;
pip veya internet gerekmez. Yönetici yetkisi istemeden kullanıcı hesabına kurulur,
Başlat menüsü ve isteğe bağlı masaüstü kısayolu oluşturur. Tarayıcı sürücüleri ayrıca kurulur.

Paketi yerel Windows x64 CPython 3.12 ortamıyla yeniden üretmek için:

```powershell
python -S -B packaging/build_windows.py --python-home "C:\Python312" --version 2026.10.30.5
```

Derleme mevcut yerel `libs/` ve çalışma ortamını kullanır; paket indirmez.
Windows'un yerleşik .NET Framework C# derleyicisi gerekir. Oluşan EXE içinden çalışma
ortamı tekrar çıkarılıp Tkinter, SQLite, PDF okuma/çizimi ve ağ engeli doğrulanır.
Yanındaki `.sha256` dosyası dağıtım kopyasının bütünlüğünü kontrol etmek içindir.
EXE kod imzalı değildir. Kurulum/güncellemeden önce Arar pencerelerini kapatın.
Windows uygulama listesinden kaldırma, ayarları ve arşiv belgelerini korur.
Kaldırıcı UTF-8 BOM ve UTF-8 konsol kodlaması kullanır; Windows PowerShell 5.1'de
Türkçe metinler ve Türkçe karakterli kullanıcı/klasör adları desteklenir.

### Ubuntu / Debian çevrimdışı paketi

Ubuntu 22.04+ veya Debian 12+ üzerinde **x86_64 (Intel/AMD 64 bit)** ve masaüstü
oturumu için `dist/Arar-Setup-2026.10.24.2-linux-x86_64-glibc2.35.run` kullanılır:

```sh
sh Arar-Setup-2026.10.24.2-linux-x86_64-glibc2.35.run
```

Python 3.11, Tcl/Tk, NumPy, Pillow, PDF kütüphaneleri ve gerekli sistem kütüphaneleri
pakettedir. Hedefte Python veya pip kurulumu, paket indirme ya da `sudo` gerekmez.
İşletim sisteminin glibc 2.35+ ve grafik masaüstü sağlaması gerekir.
Paket macOS, BSD, ARM64 veya musl tabanlı Alpine için değildir; bunlar için ayrı
çalışma ortamı ve paket gerekir. Windows ve Linux paketlerinin binary dosyaları ayrıdır.

Varsayılan kurulum `~/.local/share/arar/` altına yapılır; XDG_DATA_HOME tanımlıysa
o konum kullanılır. Uygulama menüsüne kısayol ve `~/.local/bin/arar` komutu eklenir.
`~/.local/share/arar/arar.sh` ile de açılabilir. Kaldırmak için aynı konumdaki
`kaldir.sh` çalıştırılır. Güncelleme ve kaldırma mevcut ayarları ve belgeleri korur;
uygulama açıkken dosyaları değiştirme engellenir.

İsteğe bağlı özel konum ve menü kısayolu olmadan kurulum:

```sh
sh Arar-Setup-2026.10.24.2-linux-x86_64-glibc2.35.run --prefix "$HOME/Uygulamalar/Arar" --no-shortcuts
```

Linux paketini yeniden üretmek için aynı mimaride Ubuntu/Debian üzerinde CPython
3.11+, Tcl/Tk, pip ve bir masaüstü oturumu gerekir. `requirements.txt` sürümlerinin
bu Python/Linux için wheel dosyalarını yerel bir klasörde sağlayın:

```sh
python3.11 packaging/build_unix.py --wheelhouse /yerel/wheelhouse
```

Derleme `--no-index` kullanır; internetten paket indirmez. Standart kütüphane,
Tcl/Tk, yerel paylaşılan kütüphaneler ve lisans metinleri pakete alınır. Paket açılışı,
kurulum/güncelleme, Türkçe yollar ve belgeleri koruyan kaldırma akışı doğrulanır.
Her iki paket için `.sha256` dosyası da üretilir.

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
5. Tüm sayfalar bir belgeye bağlandığında **Onayla ve kaydet** düğmesine basın.
   Çıktılar ayarlardaki ana arşiv klasörüne tarih/saat altında kaydedilir.

## Otomatik tarama ve arşiv

**Ayarlar → Otomatik tarama → Giriş klasörleri** bölümünde **Klasör ekle** ile
istediğiniz sayıda yerel klasör ekleyin. Liste **1., 2., 3. …** olarak numaralanır;
**Değiştir** seçili klasörün konumunu değiştirir, **Seçileni kaldır** seçili satırları
ayar listesinden kaldırır. Klasörler ve içlerindeki PDF’ler diskten silinmez.
**Ana arşiv klasörü** konumunu da seçin. En az bir giriş klasörü yeterlidir.
**Otomatik klasör izlemeyi aç** seçeneğini etkinleştirip ayarları kaydedin.
Varsayılan olarak izleme kapalıdır; arşiv konumu proje içindeki `Arşiv/` klasörüdür.
Giriş ve arşiv klasörleri birbirinden ayrı yerel konumlar olmalıdır; ağ yolları kabul edilmez.
Aynı giriş klasörü iki kez eklenemez. Değişiklikler kaydedilince uygulanır.

Yeni taramalar liste sırasına göre **Tarama_1**, **Tarama_2**, **Tarama_3** … etiketiyle
alınır ve arşivlenir; cihaz adı kullanılmaz. Klasör kaldırıldığında listedeki numaralar
yenilenir ve sonraki taramalarda yeni sıra kullanılır. Önceden alınan işlemlerin
numaralı etiketi korunur. Eski Canon/Kodak klasör seçimleri ilk açılışta otomatik olarak
bu listeye taşınır; eski cihaz etiketli bekleyen işlemler de numaralı etikete geçirilir.
Mevcut arşiv klasörleri yeniden adlandırılmaz.

Tarayıcıyı USB üzerinden kendi yazılımıyla kullanın. Canon CaptureOnTouch / Kodak
Smart Touch profilinde **renkli, çok sayfalı PDF**, benzersiz dosya adı ve seçilen giriş
klasörüne kayıt ayarlayın. Arar cihazı sürmez; bilgisayara kaydedilmiş PDF’leri işler.
Tarayıcı yazılımı ve cihaz sürücüleri ayrıca kurulu olmalıdır.

Uygulama açıkken klasörün doğrudan içindeki `.pdf` / `.PDF` dosyaları izlenir;
alt klasörler aranmaz. İlk etkinleştirmede klasörde zaten bulunan PDF’ler de alınır.
Dosya boyutu ve değişiklik zamanı en az üç saniye sabit kalınca yerel çalışma kopyası
oluşturulur; PDF sonlandırıcısı ve sayfalarının okunabilirliği kontrol edilir.
Yazım sürüyorsa veya PDF açılamıyorsa tekrar beklenir; durum izleme satırında görünür.
Arşivdeki sonuçlar girişe taşınmamalıdır.

Mühür/barkod analizi arka planda sırayla yapılır. Yeni taramalar mevcut incelemenin
sayfalarını veya kararlarını değiştirmez. Üstteki tarama listesinden **Taramayı incele**
ile onay bekleyen bir işlemi açın. İlk uygun işlem, çalışma alanı boşsa otomatik açılır.
Elle eklenmiş PDF’ler varsa önce o çalışma alanını kaydedin veya temizleyin.
Otomatik işlem açıkken başka kaynak ekleme kapalıdır; **Dosyaları temizle** incelemeyi
kapatır, işlemi ve kararlarını tarama sırasından silmez. Otomatik analiz tamamlanınca
popup açılmaz; durum tarama listesinde gösterilir.

**Listeden kaldır** seçili otomatik taramayı, **Listeyi temizle** listedeki işlemleri
kaldırır. Analizi tamamlanmış ve onay bekleyen dosyalar da kaldırılabilir. Açık işlem
kaldırılırsa inceleme alanı kapanır. Devam eden analiz kaldırıldığında sonucu geri
eklenmez; o işlem otomatik kaydedilmez. Arşive kayıt başlamışsa o kayıt bitene kadar
listeden kaldırılamaz. Kaynak PDF’ler ve mevcut arşiv çıktıları silinmez. Kaldırılan
aynı dosya yeniden açılışta tekrar sıraya alınmaz; gerekirse **PDF ekle** ile elle açın.

**Ayarlar → Otomatik tarama → İnceleme gerekmeyen otomatik taramaları kaydet**
varsayılan olarak kapalıdır. Açıldığında yeni tamamlanan otomatik analizde tüm sayfalar
işlenmiş ve belgelere atanmışsa sonuç otomatik arşivlenir. İnceleme, hata, kapaksız
sayfa veya işlenmemiş sayfa varsa otomatik kayıt yapılmaz; işlem onayınızı bekler.
Kayıt hatası da inceleme sırasında gösterilir; tekrar tekrar otomatik denenmez.
Önceden onay bekleyen işler ve elle başlatılan analizler bu seçenekle geriye dönük
kaydedilmez. Değişiklik sonraki otomatik analizler için geçerlidir.

Otomatik kayıt kapalıyken **Onayla ve kaydet** düğmesi kullanıcı onayıdır; öncesinde
çıktılar arşivlenmez. Kararsız veya bir belgeye bağlanmamış sayfalar varsa kayıt kapalıdır.
Her kaynak PDF için, kayıt zamanına göre ayrı bir işlem klasörü oluşur:

```text
Arşiv/
  2026-10-21/
    14-32-08_Tarama_1_001/
      THAEK12026124.pdf
      Arar_islem_raporu.json
      Arar_onay.json
    14-32-08_Tarama_2_001/
      THAEK12026130.pdf
```

Elle eklenen kaynaklarda cihaz etiketi `Manuel` olur. Aynı saniyede aynı etiketle
kayıt yapılırsa `_002`, `_003` ile devam edilir; mevcut dosyaların üzerine yazılmaz.
İşlem raporu sayfa gruplarını, onay kaydı kaynak PDF’yi, kaydedilen dosyaları ve
kayıt türünün otomatik mi kullanıcı onayı mı olduğunu içerir.

Tarama geçmişi, çalışma kopyaları ve onay bekleyen sayfa kararları `.arar/scans/`
altında yerel olarak tutulur. Uygulama yeniden açıldığında bekleyen işlemler geri gelir;
kesilen otomatik analiz yeniden sıraya alınır. Aynı kaynak yolu, boyutu ve değişiklik
zamanına sahip dosya tekrar alınmaz; değişen dosya yeni işlem sayılır. Tamamlanan
kayıt onay kaydından da doğrulanarak yeniden açılışta ikinci kez işlenmez.
Kaynak PDF silinmez; başarılı kayıttan sonra uygulamanın çalışma kopyası temizlenir.
Bekleyen işler varken `.arar/` klasörünü silmeyin.

İzlemeyi kapatmak yeni alımı ve sıradaki otomatik analizleri durdurur; başlamış analiz
tamamlanır ve mevcut incelemeler kullanılabilir. İzleme uygulama kapalıyken çalışmaz.
İlk sayfada hem Receiving Report barkodu hem mühür yoksa o dosyanın analizi durur;
dosya açıldığında hata gösterilir. Diğer taramalar sırada işlenebilir.

## Sayfa kararları ve ayarlar

**Ayarlar → İşlem ayarları → Barkod incelemesi** bölümündeki
**Receiving Report olmadan başka barkod bulunursa incelemeye al** seçeneği
varsayılan olarak açıktır. Kapatıldığında bu sayfalar devam sayfası adayı olur.
Analiz sırasında “Devam edilsin mi?” veya otomatik kapak onayı penceresi açılmaz.
Yalnızca PDF’nin ilk sayfasında hem Receiving Report barkodu hem de herhangi bir
mühür bulunamazsa hata gösterilir ve analiz durdurulur; sonraki sayfalar işlenmez.
Diğer incelemeler sağdaki panelden yapılır; analiz bu kararları beklemeden devam eder.
Önceden verilen manuel kapak onayı korunur.

**Ayarlar → Mühür kararları** bölümünde karışık (mavi + siyah/soluk) ve yalnızca
renksiz (siyah/soluk) mühürler için iki aşamada ayrı inceleme seçenekleri bulunur:

- Araya devam sayfası girmeden önce: iki inceleme seçeneği de varsayılan olarak açıktır.
- Araya devam sayfası girdikten sonra: iki inceleme seçeneği de varsayılan olarak kapalıdır;
  ilgili Receiving Report sayfası otomatik devam sayfası olur.

Seçenekler açıkken sayfa sağdaki panelde inceleme bekler; onay penceresi açılmaz
ve sonraki sayfalar işlenmeye devam eder. Konum her kaynak PDF için ayrı değerlendirilir.
İlk sayfada hem barkod hem mühür bulunamaması kontrolü bu seçeneklerden bağımsızdır.

**Ayarlar → Mühür kararları → Soluk mavi mühürleri mavi olarak işle** seçeneği
varsayılan olarak kapalıdır. Açıldığında mavi renk içeren soluk mühürler de mavi
olarak değerlendirilir; siyah ve gri mühürler maviye çevrilmez. Hem PDF içinde ayrı
görsel olan mühürlerde hem de taranmış sayfalarda geçerlidir. Mühür şeklinin mevcut
eşleşme eşiğini geçmesi gerekir. Receiving Report barkodu ile yalnızca bu mühürler
varsa sayfa kapak olabilir; ayrıca siyah mühür varsa karışık mühür kuralları uygulanır.
Seçim kaydedilir. Değişiklikten sonra analizi yeniden başlatın.

Yalnızca mavi mühür tespit edilen Receiving Report sayfaları kapaktır. 3. maddeye
uygun **ortak devam sayfaları** gruplaması varsayılandır: art arda gelen kapakların
ardındaki belgeler her kapağın PDF’sine eklenir. Eski ayarlardaki sıralı gruplama,
bu kurallara geçişte bir kez ortak gruplamaya alınır; sonrasında ayarlardan açıkça
yapılan gruplama seçimi korunur.

**Örnekleri aç** için **Ayarlar → Örnek dosyalar → Klasör seç** ile yerel bir
klasör seçip ayarları kaydedin. Alt klasörler de aranır. Klasör seçilmemişse ayarlara
yönlendiren bilgi, klasör açılamıyorsa hata, PDF yoksa klasörü kontrol etme uyarısı gösterilir.

Analizi yeniden başlatmak önceki otomatik sonuçları, önizleme önbelleğini ve ilerlemeyi
sıfırlar; sayfa listesi başa döner. Manuel kararlar korunur. **İnceleme bekliyor** sayacı
yalnızca kullanıcı kararı gereken sayfaları sayar. Kapak kararı bekleyen devam sayfaları
bu sayaca eklenmez; kapak kararı verilene kadar kayıt işlemi bekler.

**Dosyaları temizle**, eklenmiş dosyaları ve oturumdaki kararları çalışma alanından kaldırır.
Kaynak dosyalar diskte kalır. Dosya kaldırma ve temizleme, aktif işlem bittikten sonra kullanılabilir.
Analizi durdurmak için **Durdur** düğmesini kullanabilirsiniz.

**Kaynak dosyalar** listesinde Ctrl ile ayrı dosyaları, Shift ile bir aralığı seçip
**Seçilenleri kaldır** düğmesiyle birlikte kaldırabilirsiniz. Kaynak PDF’ler diskten silinmez.

**Sayfalar** tablosundaki **Sayfa**, **Durum** ve **Barkod** başlıklarına tıklayın.
İlk tıklama artan, ikinci tıklama azalan sıralama yapar; yön başlıkta gösterilir.
Sayfa numaraları sayısal, durumlar alfabetik, barkodların sayı bölümleri sayısal olarak
sıralanır. Bu işlem yalnızca liste görünümünü değiştirir; PDF sayfa sırası ve gruplama
korunur. Analizi yeniden başlatınca liste kaynak sırasına döner.

**Ayarlar → İşlem ayarları → Kapak işaretleme → Kapak olarak işaretlerken onay sor** seçeneği
varsayılan olarak açıktır. Kapatıp **Ayarları kaydet** düğmesine bastığınızda
manuel kapak işaretleme onay sorusu gösterilmez. Seçiminiz sonraki açılışlarda korunur;
kapak numarası girme gerekliliği devam eder.

**Ayarlar → İşlem ayarları → Tamamlanma bildirimi → Tarama bittiğinde uyarı göster** seçeneği
varsayılan olarak açıktır. Elle eklenen PDF’lerde başlatılan analiz tamamlandığında
bildirim gösterir; durdurulan analizde veya otomatik tarama sırasındaki işlerde
gösterilmez. Otomatik kayıt sonunda da popup açılmaz. Seçiminiz kaydedilir.

Çevrimdışı kullanım ve sorun giderme: [README_OFFLINE.md](README_OFFLINE.md).

**Ayarlar → Mühür doğruluğu → Mühür eşleşme eşiği** bölümünde PDF içindeki mühürler
ve taranmış sayfalardaki mühürler için 50–99 arasında değer seçebilirsiniz.
Varsayılanlar sırasıyla **85 ve 74**’tür. Düşük değer daha fazla adayı kabul eder;
yüksek değer daha güçlü benzerlik arar. Bunlar doğruluk yüzdesi değildir.
Ayarları kaydedip analizi yeniden başlatın. Mühür renginin ve sayfanın dosya içindeki
konumunun değerlendirilmesi ayrıca devam eder.

**PDF içindeki mühürler**, PDF’de ayrı bir görsel olarak bulunan mühürlerdir.
**Taranmış sayfalardaki mühürler**, sayfanın tamamı tek görüntü olduğunda sayfa içinde
aranan mühürlerdir. İkisi de PDF olabilir; yöntem PDF’nin yapısına göre otomatik seçilir.
Bu fark ve eşiklerin etkisi ayarlar ekranında açıklanır.

**Varsayılana dön** tüm ayarları ekranda başlangıç değerlerine getirir; örnek klasörü
seçimi temizlenir ve kayıt klasörü varsayılan `Çıktı` konumuna döner.
**Ayarları kaydet** ile kalıcı olur. Kaydetmeden pencereyi kapatırsanız mevcut ayarlar korunur.

**Ayarlar → Mühür doğruluğu → Mühür bulunamazsa kullanıcı incelemesine al** seçeneği
varsayılan olarak açıktır. Kapatılırsa Receiving Report bulunan ama mühür bulunmayan
sayfalar devam sayfası adayı olur. Siyah/soluk/karışık mühürler **Mühür kararları**
sekmesindeki konum kurallarıyla değerlendirilir. İlk sayfada hem barkod hem mühür
bulunamaması kontrolü devam eder.
Ayar kaydedilir; değişiklikten sonra analizi yeniden başlatın.

## Çevrimdışı çalışma

Uygulamada web sunucusu, bulut hizmeti, telemetri veya güncelleme kontrolü bulunmaz.
Başlangıçta Python soket oluşturma, bağlantı açma, dinleme ve DNS çözümleme engellenir.
URL, UNC ağ yolu, eşlenmiş ağ sürücüsü ve ağ hedefi olan dosya bağlantıları kabul edilmez.

PDF’ler farklı kaynak dosyalar arasında otomatik birleştirilmez. Belirsiz veya
gruplandırılmamış sayfalar sessizce atılmaz. Kaynak dosya analizden sonra değiştirilirse
kayıt engellenir. Kayıt sırasında mevcut PDF’lerin üzerine yazılmaz.

## Tanımanın kapsamı

Başlık önce yerel Tesseract OCR motoruyla yazı olarak aranır. Receiving Report No
yazısı bulunduğunda altındaki dar alanda barkod okunur; sonuç alınamazsa alan
genişletilir. Başlıkla yatay hizası uyuşmayan komşu ürün barkodları kabul edilmez.
Başlık bulunduğu hâlde barkod okunamazsa sayfa incelemeye alınır; başka bir
barkod veya örnekteki numara otomatik atanmaz. Birden fazla farklı numara da
kullanıcı incelemesi gerektirir. Başlık hiçbir yönde bulunamazsa `assets` içindeki
görsel başlık örneğiyle önceki doğrulama yöntemi kullanılır. Bu yedek yöntemde de
numara örnekten kopyalanmaz, belgedeki barkoddan çözülür.
OCR motoru ve İngilizce dil modeli kurulumla taşınır; çalışma sırasında indirme
veya bulut servisi kullanılmaz. Mühür şablonları bir kez hazırlanır; bütün sayfa
OpenCV `matchTemplate` ile aynı 77 şablon/boyut kombinasyonunda aranır. Aday bölge
elemesi yapılmaz. Tepe eşleşmenin puanı eşik karşılaştırmasından önce çift
hassasiyetle tekrar hesaplanır. Renk sınıflandırması ve mühür karar kuralları korunur.
PDFium erişimi kilit altında kalır; OCR, barkod ve mühür hesaplamaları bağımsız
görüntü kopyalarında kilit dışında çalışır. Önizleme bu hesaplamaları beklemez.
Tam sayfa taramalarda barkod okuma ve 90 derece yön düzeltme desteklenir.
Yalnızca mavi mühür bulunursa kapak, diğer mühürlerde konuma ve ayarlara göre karar
verilir. Farklı mühür tasarımları, yazı tipleri,
eğik veya düşük kaliteli taramalar manuel inceleme gerektirebilir.

Doğrudan tarayıcı cihazı bağlantısı ve parola korumalı PDF açma bu sürümün
kapsamında değildir. OCR yalnızca Receiving Report No başlığını bulmak için
kullanılır; tüm belge metnini dışa aktarmaz. Ayarlar yerel `.arar`
klasörüne kaydedilir; sayfa kararları oturum içinde tutulur.

## Testler

```powershell
python -S -m unittest discover -s tests -v
```

Temel testler gruplama, barkod doğrulama, PDF kaydı, değişmiş kaynakları reddetme
ve ağ engelini kontrol eder. Test PDF’leri geçici klasörlerde oluşturulur.

Sağlanan belge örnekleri depoya dahil değildir. Bunları kendi bilgisayarınızda
`Örnek/Kolay` altına koyarsanız belge örneklerine bağlı entegrasyon testleri de çalışır;
bulunmazlarsa ilgili testler açıkça atlanır. Örnek PDF’leri **PDF ekle** düğmesiyle seçebilirsiniz.

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
