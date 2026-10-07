> **Not / Note** — Bu dosya çalışma sırasında tutulan, kronolojik **Türkçe orijinal notlardır**. Konuya göre derlenmiş ve düzeltilmiş İngilizce sürüm için `docs/*.md` dosyalarına bakın.
> Bazı ifadeler sonradan düzeltilmiştir (ör. "27 adımlı ses tablosu" bir yanlış okumaydı; MCU'daki `0x19` varsayılanı yalnızca ~2 sn geçerlidir).
> Atıf yapılan `firmware/backup/` ve oturum `scratchpad` dosyaları (cihaz dökümleri) **telifli içerik oldukları için yayınlanmamıştır**; yalnızca SHA-256 değerleri verilmiştir.
> Kullanıcının BT adresi `XX:XX:XX:XX:XX:XX` ile anonimleştirilmiştir.
>
> *This is the original chronological working log in Turkish. See `docs/*.md` for the organised English documentation; some statements here were later corrected. The referenced dump files are not published (proprietary); only their SHA-256 hashes are given.*

# G560 firmware analizi (2026-10-07)

Yalnızca salt-okunur analiz; cihaza firmware YAZILMADI.

## Kaynaklar (resmi Logitech indirmeleri)

| Paket | URL | SHA-256 |
|---|---|---|
| Eski güncelleme aracı 122.3.23 (Windows, ana işlemci) | `https://download01.logi.com/web/ftp/pub/techsupport/gaming/G560Update_122.3.23.exe` | `ce22b30517f8bc76ffc60d7b6ff5e5f1e1b17a287dba6770dc05dbf58cc3235f` |
| Bluetooth güncelleyici 1.0.13 (zip) | `https://download01.logi.com/web/ftp/pub/techsupport/gaming/Logitech_G_G560_Gaming_Speaker_Updater_1.0.13.zip` | `ead6716a66f26778d292b3069c4d7a8c7ce5aa74b193be02fd4c34bfff74bb25` |

İndirilenleri çalıştırma; her biri kendi boş klasöründe. Cihaz firmware'i 122.3.23 (HID++ `U1 22.03 build 0x23`) ile bu paket eşleşiyor.

## Bulgular

**Ana işlemci paketi (G560Update_122.3.23.exe)** — exe içinde iki `FIRMWARE` kaynağı (`pe_extract.py` çıkarır):
- `10000`: 45.909 bayt, düz metin **S37** (Conexant ses çipi EEPROM imajı; 598 S3 kaydı, tüm kontrol toplamları geçerli, 18.455 bayt, aralıklar 0x2–0x8b, 0x10c–0x3f6, 0x3fa–0x531, 0xb50–0x4eb9). İçinde VID/PID (`6D04 780A`) ve USB dizeleri ("Logitech", "G560 Gaming Speaker") var. `s37_decode.py` ikiliye çevirir.
- `10001`: 34.497 bayt, `Muse_DfuImg`, U-Boot benzeri 64 bayt başlık + 34.433 bayt veri, **yükleme/giriş 0x08004000** (Cortex-M flash adresi), düz Thumb kodu (entropi 6,7). Başlık/veri bütünlüğü **CRC-16/XMODEM** (başlıkta crc alanı sıfırlanarak) — kriptografik imza yok (en azından bu katmanda). `uimg.py` doğrular.
- Güncelleyici (Win32 + Conexant "CAPE" kütüphanesi) CX20562 ailesi için I2C/UART/ROM bootloader'ları ve "LayoutSignature/Device signature/Bad Checksum" kontrolleri içeriyor.

**Bluetooth paketi (1.0.13)** — `MUSE/firmware.bin` (719 KB) **şifreli** (entropi 7,996; okunabilir metin yok). Kullanıcının BT adresi `XX:XX:XX:XX:XX:XX` **MUSECSR** aralığında (`C0:28:8D:7C:5B:F1`–`7E:AD:B0`); MUSECSR için pakette firmware dosyası yok (config'de yorum satırı), yani kullanıcının BT modülü (CSR) firmware'i bu pakette değil. btlib.dll içinde RFCOMM üzerinden `run_dfu_*` / `nvkey` akışları geçiyor.

## Ses varsayılanı araması (statik analiz, ilk geçiş)

- Conexant EEPROM imajı: ilk bölge (0x2–0x8b) VID/PID + USB dizeleri; 0x10c–0x531 yapılandırma/DSP tabloları (tekrarlayan `02 ff 7f` = Q15 birim kazanç); 0xb50–0x4eb9 (17 KB) **65C02 yama kodu + tablolar** (kanıt: `a2 06 a9 00 9d f9 15` = LDX/LDA/STA, `e6 40 d0 02 e6 41` = 16-bit INC, `20 92 7e` = JSR ROM). Capstone 5 `MOS65XX` ile çözülebilir. Tablo işaretçileri imaj ofsetleri; CPU adresi ↔ imaj ofseti eşlemesi (yama/ROM) bilinmiyor.
- ~~"27 basamak, −74,6…−3 dB" tablosu~~ → **yanlış okuma** (3. tur): gerçek tablo 51 girişli, iki ayrı bayt dizisi (düşük bayt @imaj 0x1a8b, yüksek bayt @0x1abe); bunları 16 bit LE gibi birleştirmek sahte bir tablo üretmişti. Doğru değerler "Conexant imajı çözümlemesi"nde. Tablo **122.2.22 ↔ 122.3.23 arasında aynı** (yalnız 7 bayt kayık), sürüm notundaki "master ses eğrisi" değişikliği CX'te değil, **MCU yükselteç tablolarında** (aşağıda).
- İki sürüm arası fark: çoğu `+7` adres kayması; gerçek içerik farkları: 0x3fa'da 4 bayt, ~0x1e02'de 20 bayt ve ~0x1f29'da 31 bayt yeni 65C02 kodu (durum değişkenleri `$15F9+x`'e yazıyor), küçük işaretçi tabloları. Sürüm notu: "kulaklık çıkarılınca sürekli sessiz" düzeltmesi + master ses eğrisi + subwoofer seviyesi.
- Cortex-M imajı (`Muse_DfuImg`): gerçek vektör tablosu (SP 0x200006e0, reset 0x0800c52d), STM32 benzeri periferikler; HID++ özelliklerinin bir kısmı ve ses/LED mantığı burada — 2. turda disassemble edildi (aşağıda).
- ~~Varsayılan ses seviyesi henüz bulunamadı~~ → **bulundu, MCU imajında** (aşağıda "MCU imajı çözümlemesi").

## MCU imajı (Muse_DfuImg, fw_10001) çözümlemesi — 2. tur (2026-10-07)

Hâlâ salt-okunur; cihaza hiçbir şey yazılmadı. Araçlar: `uimg.py` (CRC-16/XMODEM doğrulaması düzeltildi: eski sürüm CRC-32 deniyordu, yanlışlıkla "GEÇERSİZ" diyordu; her iki sürümde baş + veri CRC-16 geçerli), Capstone ile Thumb-2 disassembly (`mcu_dis.py`; girdi `uimg.py fw_10001.bin cikti.raw` ile çıkarılan ham gövde).

Sürümler: **122.3.23** = 2021-03-18 tarihli, gövde 34.433 B; **122.2.22** = 2018-10-08, 34.051 B. Taban/giriş 0x08004000, vektör tablosu 60 giriş (16 sistem + 45 IRQ).

**Kesin (kodda doğrudan görülen):**
- Çevre birimleri: I2C1 (master, DMA ch6/7, 96 yuvalı işlem kuyruğu @0x200006e0), I2C2 (**slave**, halka tamponlu, olay/hata kesmeleri 0x08005710/0x080056b0), GPIO, ADC, TIM3–7, DMA1/2, EXTI, IWDG, flash denetleyicisi. **USART/SPI/USB yok.** Kalıcı ayar: CRC-16 korumalı EEPROM okuyucusu `0x08005484(buf, adres, uzunluk)`.
- **HID++ dağıtıcısı** `0x080081ac`: istek `[cihazIdx=0xFF][özellikIdx][fonk<<4|swId][param…]`; özellik tablosu `0x0800c394` (10 giriş). MCU'nun sahip olduğu özellikler: idx4=`0x8070` (16 fonk, fn3 `setZoneEffect`=0x08004c85), idx7=`0x8320` (1 fonk), idx8=`0x8040` (3 fonk), idx9=`0x8305` (2 fonk). idx 0–3,5,6 boş (standart özellikler IRoot/IFeatureSet vb. başka yerde — büyük olasılıkla Conexant tarafı). Kayıt biçimi: `{id:u16, bayrak:u8 (bit5=0x20 → 0x20001c03 bayrağı gerekir), nfonk:u8, …, fonk_tablosu*}`.
- Mesaj pompası `0x08005ad8`: kanal 7/8 gelen HID++ (0x11 uzun / 0x10 kısa), kanal 4/5/6 çıkış (yanıt/hata/bildirim), kanal 0/1/2 durum raporları. Kanal tablosu `0x2000034c` (8 B/giriş, 10 kanal).
- **Ses mantığı MCU'da.** İki yükselteç benzeri I2C aygıtı `0x34` ve `0x36` (8 bit adres), ses = yazmaç 7. İki 52 girişli tablo: `0x0800ac8c` (→0x36) ve `0x0800acc0` (→0x34); indeks 0=`0xFE` (sessiz) … 51=`0x00` (en yüksek). `0x34` değeri = `tablo2[idx] − 2·düzeltme[altSeviye/5]` (0…0xFE'ye kırpılır) — `0x34` büyük olasılıkla subwoofer.
- **Açılış varsayılan ses seviyesi:** uygulama başlatma fonksiyonu `0x080074ba` → `0x080075a4` çağırıyor; orada `movs r0,#0x19` ile `0x20001bf8` (master ses indeksi) = **25** (0–51 aralığı; `0x2019`, gövde ofseti `0x35ae`, DFU dosya ofseti `0x35ee`). Ses kalıcı saklanmıyor, her açılışta 25 — **ama CX açılıştan hemen sonra kendi değerini yollayıp bunu ezmiş olabilir (Conexant bölümüne bak).** Host ses komutu `0x0800ac16` (bayt3 < 0x33 ise indeksi değiştirir) → `0x0800af30` → iki yükseltece yazar.
- **Subwoofer seviyesi varsayılanı:** `0x0800aea8`: EEPROM ayarı adres `0x88` okunamazsa `0x46` = **70** (0–100).
- LED sürücüleri: `0x78` ve `0x7E` adreslerinde iki özdeş aygıt; yazmaç kullanımı (0x25 güncelle, 0x4F sıfırla, 0x00 kapatma) IS31FL3236 tipi 36 kanallı sürücüyle uyumlu.

- **Sürüm farkı (master ses eğrisi + subwoofer):** iki 52 girişli yükselteç tablosu 122.2.22'de başka değerlerde (`0x36` tablosu @0x0800ad80, `0x34` tablosu @0x0800adb4): ör. `0x36` idx1 `0xAE`→`0xA3`, `0x34` idx1 `0xC3`→`0x9F` (3.23'te düşük indekslerde farklı adım/seviye; yön yorumu yazmaç 7'nin anlamına bağlı, doğrulanmadı). Varsayılan master indeks her iki sürümde de 25.

**Çıkarım / doğrulanmadı (hipotez):**
- MCU = STM32L1xx (çevre birimi adresleri L1 düzeni), 16 KB önyükleyici altında (0x08004000 taban). Tahmin.
- 0x34/0x36 yükselteç, 0x78/0x7E IS31FL3236: yalnızca yazmaç kullanımından çıkarım, veri sayfasıyla doğrulanmadı.
- Açılış animasyonunun yeri henüz bulunamadı (LED yürütmesi 0x8070 fonksiyonlarında olmalı).

## Conexant imajı (fw_10000, CX20562, 65C02) çözümlemesi — 3. tur (2026-10-07)

Hâlâ salt-okunur. Araç: `cx_dis.py` (girdi: `s37_decode.py fw_10000.bin cikti.raw`). Kapsam: yalnız **yama** (`0xb50–0x4eb9`, 17 KB); CX'in **ROM'u pakette yok**, bu yüzden ROM çağrıları (`JSR $7df2/$7ce9/$dbbe…`) ve BT/UART/USB düşük seviye kodu görülemiyor.

**Kesin:**
- **CPU adresi = imaj ofseti + 0x927** (kod uzayı). `0xb5c`'de 3 baytlık **kanca tablosu** (`4c lo hi` = JMP, `60 60 60` = boş): ROM, olay başına yamaya bu tablodan dallanıyor (32 dolu kanca). Değişken/yazmaç adresleri (`$15F9`, `$1333`…) ayrı veri uzayında.
- CPU **65C02'nin genişletilmiş bir türevi**: `D2 maske lo hi` = bayrak bitlerini SET, `C2 maske lo hi` = CLR, `F2 maske lo hi rel` = bit testi+dallan. Capstone bunları `CMP (zp)`/`NOP`/`SBC (zp)` diye yanlış çözer. `D2 01 21 16` = `$1621` bayrağının bit 0'ı = "I2C işlemi başlat" isteği.
- **CX → MCU I2C protokolü (kesin):** CX, I2C **master**; MCU I2C2 **slave**, 7-bit adres `0x77` (8-bit yaz `0xEE`, oku `0xEF`), 100 kHz. CX işlem bloğu: `$1333` kontrol (düşük 6 bit = yük uzunluğu), `$1334` adres (bit0 = oku/yaz), `$1335…` veri; bit-bang ROM'da (`$7df2` start, `$7ce9` bayt). MCU ayrıştırıcısı `0x0800a18a` ile uzunluklar birebir: `D6`→22 B `BB…`, `C4`→4 B `CC…`, `93/D3`→19 B `FF…`(HID++ uzun, MCU başına 0x11 ekleyip 20 B yapar). Okuma yanıtı `0xFF` ile başlar (HID++), MCU GPIOC.8 ile "hazır" der.
- Mesaj kataloğu (CX'in gönderdikleri, her iki sürümde aynı): `CC 00 01 <ses idx>` (ses), `BB 05 02 00` (sürüm sorgusu → MCU `bb 05 02 00 'U' '1' … 22 03 … 23` döner = HID++'daki "U1 22.03 build 0x23"), `BB 05 04 01/00` (mod bayrağı: CX `$1417` kaynağı `$164b` ile farklıysa; ≥5 ise 1), `BB 05 01 …`, `BB 05 05 …`, `BB 03 01 80`, HID++ `93/D3`.
- **Ses akışı:** host/USB ses → CX DSP kazancı (`$12cd:$12cc`, 1/256 dB, işaretli 16 bit) → `0x236c` ters arama → indeks 1…50 → `CC 00 01 idx` → MCU `0x0800ac16` → yükselteç tabloları. İlk 5 yoklamada değer değişmese bile yeniden gönderir (`$1637` sayacı). CX tarafı indeksi 0x32 (50) ile sınırlar; MCU tablosu 51'e kadar (51 CX'ten gelmez).
- **CX 51 girişli ses eğrisi** (düşük bayt @0x1a8b, yüksek @0x1abe; 1/256 dB): idx0=`0xca00` (−54,0 dB), idx10=`0xe5a7` (−26,35), idx25=`0xf206` (−13,98), idx50=`0xfc00` (−4,0). **122.2.22 ile aynı.**
- **Yapılandırma bloğu @0x11a (iki sürümde aynı):** (min, maks, çözünürlük, mevcut) dörtlüleri: grup1 = `ca00, fc00, 0100, e5a7` (−54, −4, 1 dB, **mevcut −26,35 dB = eğri idx 10**), grup2 = `ce00, 0500, 0100, fb00`, grup3 = `e200, 0500, 0100, 0000`.

**Güçlü çıkarım (doğrulanmadı):** grup1'in "mevcut" değeri `0xe5a7`, eğrideki tam bir giriş olduğundan **CX'in açılış ses değeri = idx 10**. CX bunu MCU'ya ilk yoklamalarda `CC 00 01 0a` ile yollayacağı için **MCU'daki 25 (`0x19`) açılışta kısa süre geçerli, sonra CX'in 10'u onu ezer**. **Ölçüm (2026-10-07, `g560_volume.swift get` + CoreAudio dB okuması, yalnız okuma):** aygıtın bildirdiği aralık **−54,0…−4,0 dB** (CX yapılandırmasındaki min/maks ile birebir → grup1'in USB ses aralığı olduğu doğrulandı). Mevcut değer **−19,0 dB (scalar 0,49)**; bu **ne idx 10 (−26,35) ne MCU 25 (−13,98)** ve eğri tablosunda da yok (en yakın idx 17 = −19,34). −19,0 yuvarlak (1 dB çözünürlük) → büyük olasılıkla **macOS'un geri yüklediği son ses**, cihaz varsayılanı değil. macOS scalar↔dB eşlemesi doğrusal değil ((−19+54)/50 = 0,70 ≠ 0,49), bu yüzden önceki "≈0,55" tahmini zaten geçersizdi. **Sonuç: macOS bağlıyken cihazın açılış varsayılanı bu yolla gözlenemez; hipotez ne doğrulandı ne çürütüldü.** Varsayılanın önemli olduğu durum zaten USB'siz (yalnız BT/aux) kullanım; orada macOS araya girmez ama okuma kanalı da yoktur.

**BT kontrol kanalı için sonuç:** Yama kodunda **hiç UART/BT yazmacı yok** — BT↔CX bağlantısı ROM'da. MCU'da UART yok. BT modülü (CSR, "MUSECSR" sürüm 204, kullanıcının BT adresi bu kümede) ayrı; pakette firmware'i yok. Güncelleyicinin **RFCOMM seri kanalı** (`path, baud, handshake`) + CSR `nvkey`/`run_dfu_*` akışı var → BT modülünde bir seri/RFCOMM kanalı mevcut, ama sadece güncelleme için mi yoksa kontrol komutları da taşıyor mu bilinmiyor. CX/MCU imajlarını değiştirerek **yeni bir BT kanalı eklenemez** (BT radyosu CSR'da); eklenebilecek tek şey CX/MCU'nun zaten aldığı bilgiyi (ör. ses komutu) başka yola iletmesi.

## BT tarafı: btlib.dll + SDP — 4. tur (2026-10-07)

Hâlâ salt-okunur. SDP sorgusu kullanıcı onayıyla yapıldı (yalnız SDP okuma istekleri; veri kanalı açılmadı, hiçbir şey yazılmadı). Araçlar: `sdp_dump.py` (IOBluetooth), `pe_func.py` (x86-64 fonksiyon disassembly).

**btlib.1562.{32,64}.dll (Airoha MUSE için):**
- İhracatlar yalnız 5 tane: `GetBattery`, `GetVersion`, `UpdateFirmware`, `GetSupportedHardware`, `CleanNV`. Serbest kontrol (ses, EQ) yok.
- Aktarım: **Winsock AF_BTH RFCOMM soketi** (`socket(0x20, SOCK_STREAM, 3)`; COM port değil). `SOCKADDR_BTH`: BD adresi (`%02X:…` ayrıştırılır), **serviceClassId = `00000000-0000-0000-0099-AABBCCDDEEFF`**, port = `0xFFFFFFFF` (kanalı Windows SDP ile GUID'den bulur). "baud=115200/handshake" yalnız günlükte kalan artık parametre.
- Protokol: **Airoha RACE**, komut kimliği 16 bit, yanıt türü 0x5D (bildirim) / 0x5B (yanıt). Kullanılanlar: `0x0CD6` pil, `0x1C07` FOTA sürüm, `0x0A01` NVkey tam anahtar yaz (`CleanNV`), `0x1C00` bölüm bilgisi, `0x1C0A`/`0x1C01`/`0x1C06`/`0x1C02` FOTA işlem/silme/bütünlük/durum. Ses/EQ komutu yok (RACE'in kendisi NVkey yazabilir, bu kütüphane bunu yalnız `CleanNV` için kullanıyor).
- `updater.exe` .NET (ad alanı `Wonderboom_FW_update.BtLib` — Ultimate Ears altyapısı); `IsAirohaDevice` ile Airoha/CSR ayrımı yapar. `MUSE` = Airoha (OUI `0C:FC:83`, `firmware.bin` 1.1.1.20), `MUSECSR` = CSR (sürüm 201/203/204, **firmware dosyası yok**, güncelleme akışı yok).

**SDP (kullanıcının hoparlörü `XX:XX:XX:XX:XX:XX`, MUSECSR aralığı):**
- Düz sorgu (public browse group), durum 0: **tek kayıt** = A2DP Audio Sink (`0x110B`, AVDTP PSM 0x19 v1.2, profil `0x110D` v1.2, SupportedFeatures=1). **AVRCP (0x110C/0x110E), HFP/HSP, SPP (0x1101) ve üretici UUID'si yok.** Sonuç: macOS'un BT üzerinden hoparlör sesini (AVRCP mutlak ses) ayarlayacağı standart bir kanal yok.
- UUID filtreli sorgular (`performSDPQuery:uuids:`) ~20 sn'de zaman aşımına düştü — **var olduğu bilinen `0x110B` için de**, yani yöntem bu cihazda güvenilmez (cihazın SDP sunucusu ServiceSearch istek türünü işlemiyor olabilir; kanıtlanmadı). Bu yüzden Airoha RACE UUID'sinin (yukarıdaki GUID) var olup olmadığı **bilinmiyor**. Ham SDP kanalı (L2CAP PSM 1) macOS'ta kullanıcı uygulamasına kapalı (`IOReturn 0xE00002BC`).
- `bluetoothd` günlüğü ve `/Library/Preferences/com.apple.Bluetooth.plist` (441 B) SDP verisi vermedi.

**RFCOMM kanal taraması (kullanıcı onayıyla, 2026-10-07):** `rfcomm_scan.py` ile kanal 1–30 için `openRFCOMMChannelSync` denendi; hiçbir veri gönderilmedi. **30 kanalın hepsi aynı hatayı (`0xE00002BC`) tam 3,1 sn'de verdi, hiçbiri açılmadı**; hoparlör bağlı kaldı. Aynı hata kodu ham SDP kanalı (PSM 1, var olduğu kesin) için de döndüğünden macOS "reddedildi" ile "API izin vermiyor"u ayırt etmiyor; pozitif kontrol (RFCOMM'li bilinen cihaz) yok. Sabit 3,1 sn de kanala özgü bir ret değil, sabit bir iç zaman aşımı gibi. Yani: **RFCOMM servisi bulunamadı, ama yokluğu kanıtlanmış da sayılmaz** (bu yöntemle kanıtlanamaz).

**Sonuç:** Kullanıcının donanımı CSR (MUSECSR) olduğundan Airoha RACE kanalının bu cihazda bulunması beklenmez; bulunduğu kanıtlanmadı da. Standart BT servisleri yalnız A2DP. Yani BT'den kontrol için bilinen/belgeli hiçbir yol yok. Kalan belirsizlik: RACE UUID'sinin gizli RFCOMM servisi olarak var olup olmadığı (yalnız RFCOMM kanal taramasıyla, yani bir veri kanalı açarak sınanabilir — onay gerektirir).

## Web araştırması — 5. tur (2026-10-07)

Kaynaklar: [fwupd `synaptics-cxaudio` eklentisi](https://github.com/fwupd/fwupd/tree/main/plugins/synaptics-cxaudio) (`fu-synaptics-cxaudio-common.h`, `fu-synaptics-cxaudio.rs`, `-device.c`, `-firmware.c`), [IgorsLab G560 incelemesi/sökümü](https://www.igorslab.de/en/audio-measurement-sound-rgb-logitech/), [Linux `tas571x.c`](https://github.com/torvalds/linux/blob/master/sound/soc/codecs/tas571x.c), [Logitech G560 Updater 1.0.13 sayfası](https://support.logi.com/hc/en-us/articles/35695571999639-G560-Gaming-Speaker-Updater). G560'a özel tersine mühendislik yazısı/GitHub projesi bulunamadı (arama: HID++ 0x8070, CX20562, G560 firmware).

**Donanım doğrulamaları (sökümden):** MCU = **STM32L100** (ST, Cortex-M3; aydınlatmayı sürer — STM32L1xx hipotezi doğrulandı). Yükselteçler = **iki TI TAS5731M** (sınıf-D, biri 2×30 W stereo, biri 60 W mono köprü — `0x34/0x36` yükselteç çıkarımı doğrulandı). Conexant = **CX20701** ("BT modülünün mavi OEM kartı"nda) — notlardaki "CX20562" etiketi güncelleyici dizelerinden gelmişti; cihazdaki çip büyük olasılıkla CX2070x ailesi (fwupd cihaz türleri: CX20562 / CX2070x / 2077x / 2076x / 2085x / 2089x / 2098x / 2198x). Söküm yazısında BT çipi adlandırılmamış (CSR çıkarımı hâlâ kanıtsız); LED sürücüsü adlandırılmamış (STM32'nin 4 bağımsız RGB kanalı sürdüğü yazılmış → IS31FL3236 hipotezim şüpheli).

**TAS5731M yazmaçları** (TAS571x ailesi, Linux sürücüsüyle çapraz doğrulama; TAS5731M'e özel veri sayfası okunmadı): `0x06` yumuşak sessiz, `0x07` ana ses, `0x1B` osilatör ayarı (başlatmada 0 yazılıyor) — MCU'nun yazdıkları bunlarla uyuşuyor (`0x00`=`0x6C`, `0x1B`=0, `0x06`=3/0 sessize al/aç). Ana ses 0,5 dB adımlı, **düşük değer = yüksek ses**: `dB = 24 − değer/2` (0x00 = +24 dB, 0x30 = 0 dB, 0xFF = en alt/sessiz; ailede kanıtlı, 5731M için analoji). Bu eşlemeyle MCU tabloları: idx 25 → `0x36`: 0x5E → **−23 dB**, `0x34`: 0x5A → −21 dB; CX'in muhtemel açılışı idx 10 → −38 / −36 dB. Yani iki aday varsayılan arasında ~15 dB var.

**Conexant EEPROM düzeni (fwupd) — bizim fw_10000 imajıyla birebir örtüşüyor:**
- `0x0000`: geçerlilik imzası `'L'` (0x4C) + EEPROM boyut kodu (`boyut = 1 << (kod+8)`); bu iki bayt S37 imajımızda yok (fwupd de "boot bytes" olarak korur).
- `0x0014`: yama bilgisi `{imza 'P'(0x50), adres u16le}` → imajımızda `50 50 0b` = **yama adresi 0x0B50** (yama bölgemizin başlangıcı).
- `0x0020`: özel bilgi: `patch_version_string_address u16le, cpx_patch_version[3], spx_patch_version[4], layout_signature 'S'(0x53), layout_version, application_status, vendor_id, product_id, revision_id, dize adresleri…` → imajımızda `layout_signature='S'`, `layout_version=3`, VID `046d`, PID `0a78`.
- fwupd'un SREC işleme kuralları: yalnız S3 kayıtları; korunan "bad block"lar: `0x00BC` (test işareti, 2 B), `application_status` baytı, boot baytları (0x0000, boyut+1), seri numarası dizesi ve işaretçisi. Son üç kayıttan birinde `"CX" + karakter` cihaz türü imzası var (`'2','4','6'` → CX2070x).
- **Bütünlük:** fwupd imajda CRC/imza doğrulaması yapmıyor (yalnız yapı kontrolleri ve yazarken geri-okuma doğrulaması). Cihaz ROM'unun açılışta ayrıca sağlama toplamı kontrol edip etmediği bilinmiyor (Windows aracında "Bad Checksum"/"LayoutSignature" dizeleri var).

**Conexant HID bellek erişim protokolü (fwupd) ve G560'ta varlığı (kesin, rapor tanımlayıcısından):** G560'ın HID rapor tanımlayıcısında (IORegistry'den, cihaza gitmeden okundu) **kimlik 4 OUT 36 B** ve **kimlik 5 IN 32 B** (+ ikinci çift 6/7) var = fwupd `MEM_WRITEID=0x4` / `MEM_READID=0x5`. Protokol: OUT rapor kimliği 4 → `[0]=0x04, [1]=bayrak (bit4: adres≥64K, bit5: EEPROM, bit6: YAZ), [2]=uzunluk (≤32), [3..4]=adres (BE u16), [5..36]=veri`; okuma: bayrakta bit6 temiz gönderilir, ardından kimlik 5 IN raporu okunur (veri `[1..32]`). Bellek türleri: EEPROM (bit5; 128 KiB'a kadar), CPX RAM, CPX ROM (okunur, yazılamaz). Bilinen CPX RAM adresleri: `0x1000` park (bit7), `0x1001` FW sürümü, `0x1005` çip kimliği, `0x0400` reset (bit6). fwupd yazma sırası: park → (düzen sıfırlama) → 32'şer baytlık S3 kayıtlarını EEPROM'a yaz+geri-oku doğrula → eski yamayı geçersiz kıl → park kaldır. Silme adımı yok.
→ **Sonuç:** macOS'tan CX EEPROM/RAM/ROM'u HID ile okumak ve (istenirse) yazmak teknik olarak mümkün görünüyor. MCU (STM32) güncellemesi ise ayrı: bu protokolle erişilemez (MCU CX'in arkasında I2C slave).

**Logitech 1.0.13 BT güncelleyicisi:** yalnız "Bluetooth özelliğinde optimizasyon ve hata düzeltmeleri", Windows 10/11, 2025-10-17; sayfa "Firmware Update Tool artık desteklenmiyor" uyarısı taşıyor. Donanım sürümü/cihaz tanıma bilgisi sayfada yok.

## Cihazdan HID ile okuma — 6. tur (2026-10-07, kullanıcı onayıyla, YALNIZCA OKUMA)

Araç: `cx_hid_read.py` (cihaza giden tek yol `_send()`; kimlik 0x04, 37 bayt, `bayrak & 0x40 == 0`, veri alanı sıfır değilse **gönderilmeden reddeder**; yazma/park/reset adresi yok; `--dry-run` ile paketler önce gösterildi). Hiçbir yazma isteği gönderilmedi.

1. **CX RAM `0x1000…0x1008`** = `01 02 05 01 01 01 0f 0e 1d` (park yazmacı `0x01` → bit7 temiz, park edilmemiş; FW sürümü baytları `02 05 01 01` → fwupd biçimiyle `05.02.01.01`; `0x1005` çip kimliği ofseti `01`). Çip kimliği için `chip_id_base` yok, yorumlanmadı.
2. **EEPROM ilk 0x40 bayt** imajımızla aynı; ek olarak boot baytları `4c 07` = `'L'` + boyut kodu 7 → **EEPROM 32 KiB** (`1 << (7+8)`).
3. **Tam EEPROM dökümü** (32.768 B, 10 sn; sha256 `787c708a7eb68cb6d09a867849385506c548b39fbbf54a7253fae6a2d47329df`, dosya oturum scratchpad'inde `cx/device_eeprom.bin`):
   - **v323 (122.3.23) imajıyla bayt bayt AYNI** (18.455 B içinde 0 fark); 122.2.22 ile 15.463 B farklı → **cihaz 122.3.23 çalıştırıyor**.
   - İmajda olmayan yalnızca 3 bayt: `0x00–0x01` (`4c 07`, boot baytları) ve **`0x7FFD = 0x08`** (anlamı bilinmiyor; tek başına duran, muhtemelen durum/sayaç baytı). `0x4EBA` sonrası %99,99 `0xFF`.
   - İmajın son kaydı `CX4` @0x4EB7 = fwupd cihaz türü imzası ('4') → **CX2070x yaması** (sökümdeki CX20701 ile uyumlu).
   - Sonuç: yapılandırma bloğu (`0xe5a7` "mevcut" ses, @0x120) **cihazın gerçek EEPROM'unda** duruyor; analizimiz cihazla doğrulandı.

## Cihazdan HID ile okuma — 7. tur: CX RAM ve ROM (2026-10-07, kullanıcı onayıyla, YALNIZCA OKUMA)

Sınırlar (kullanıcıya söz verildi ve uyuldu): RAM'de yalnız `$15A0–$164F` ve `$12CC–$12DF`; `$13xx`, `$1417` ve olası donanım yazmaçlarına dokunulmadı; ROM yalnız `0x7000–0xFFFF`. Hiçbir yazma isteği gönderilmedi.

**Adres uzayı:** HID okuması **ortak** adres uzayını görüyor. `0x2056` (kod) cihazda imajla (`cpu − 0x927`) **birebir aynı** → yama RAM'e yüklenmiş. İstisna: yama başlangıcı — cihazda `0x1477–0x1487` sıfır, kanca tablosu (`4c 9a 16 …`) **`0x1488`**'de başlıyor (imajdan hesaplanan 0x1483 değil; ilk 12 başlık baytı yüklenmiyor, tablonun yeri kayık — yükleyici ayrıntısı bilinmiyor). `0x15F0` civarı imajda kod değil boşluk: orası RAM'de **canlı değişkenler**.

**Canlı değerler (ses):**
- `$15F0 = 0x11` (17) = macOS'un geri yüklediği −19,0 dB'nin (`0xED00`) CX ters aramasındaki indeksi → ters arama modeli ölçümle doğrulandı.
- `$12CC–$12CF = 00 ed 00 ed` (canlı kazanç −19,0 dB, 2 kanal); **`$12D0–$12D7 = a7 e5` ×4** (= `0xE5A7` yapılandırma "mevcut" değerinin RAM kopyaları, host değiştirse de duruyor); `$12D8–$12DB = 00 fb` ×2 (grup2 "mevcut" 0xFB00); `$12DC = fc fc 01 00`.
- `$1637 = 5` (yeniden gönderme sayacı üst sınırı, koddaki `cpx #5`), `$1636 = 0x13` (son HID++ çerçeve uzunluğu 19), `$164B = 5` (son gönderilen mod ≥5 → `BB 05 04 01`).
→ **Güçlü kanıt (kesin değil):** cihazın başlangıç sesi, EEPROM `@0x120` = `0xE5A7` (idx 10, −26,35 dB); host SET_CUR ile canlı kazancı değiştiriyor, başlangıç kopyası RAM'de kalıyor. Hâlâ gözlenmeyen: açılışta CX'in bunu MCU'ya gerçekten `idx 10` olarak yollayıp MCU'nun 25'ini ezdiği (zamansal). Doğrudan test: hoparlörü açıp USB yeniden bağlarken `$12CC`'yi hızlı yoklamak (host geri yüklemeden önceki ilk değer 0xE5A7 mi?) — kullanıcı eylemi gerektirir.

**CX ROM dökümü `0x7000–0xFFFF` (36.864 B, sha256 `26fb5cbb5926596ddc5d7130a3ce43a9758d79f939c7cd47fabc8e9b447f8073`, scratchpad `cx/device_rom_7000_ffff.bin`; her an 10 sn'de yeniden alınabilir):**
- Vektörler: **RESET = `0x7000`**, NMI = `0x70F5`, IRQ = `0x7003` → ROM `0x7000`'da başlıyor.
- Dizeler: `(C) CONEXANT`, `CHAN_V05.02.01.01` (= RAM'den okuduğumuz FW sürümü `05.02.01.01` ✓), `Download initiated ..`, `Upload completed - power cycle device`, `Upload error - Try again`, `AEC Tuning- ESC to exit`, `DSP LOCKUP`; USB varsayılan dizeleri `Conexant`, `CONEXANT USB AUDIO`, `Communication Audio` (EEPROM bunları "Logitech"/"G560 Gaming Speaker" ile ezer) → ROM'da **UART konsolu/indirme yolu** var. **BT, AVRCP, ses protokolü ya da 'Logitech' ile ilgili dize yok.**
- **HID rapor tanımlayıcısı EEPROM'da** (`0x494`'ten; Telephony `0x4F5`, HID++ `0x516`); ROM'da yalnız varsayılan Consumer/Telephony parçası (`0xEF20`, `0xEF98`). Yani rapor kimlikleri 4–7 ve HID++ (0x11) koleksiyonu EEPROM'dan geliyor (özelleştirilebilir).
- ROM yama kancalarını **40 yerden** `JSR $14xx` ile çağırıyor (kanca tablosu 0x1488'den; örn. ROM `0x716E→$1497`, `0x7871→$1488`).
- ROM da yamadaki genişletilmiş komutları kullanıyor; tam disassembly için bu ek komut kümesinin (`B2/C2/D2/E2/F2…`: 3–5 bayt, mutlak adres+maske+göreli atlama) çözülmesi gerekiyor — **yapılmadı**; Capstone bu komutlarda senkron kaybediyor.

**BT açısından sonuç (güncel):** CX'in ROM'unda da yamasında da BT'ye özgü hiçbir şey yok; CX20701 sökümde "BT modülünün OEM kartında" ve bir "audio cross mixer". En olası mimari: BT ses yolu analog/I2S ses olarak CX'e giriyor, **kontrol bağlantısı yok** (SDP'de AVRCP olmaması ve MCU/CX'te BT dizeleri olmaması ile tutarlı). Yani BT'den kontrol için CX/MCU tarafında bir kanca yok.

## Açılış sesi deneyi — 8. tur (2026-10-07, kullanıcı onayıyla, YALNIZCA OKUMA)

Araç: `cx_boot_watch.py` (kaybolma/belirme izler; belirdikten sonra 40 sn hızlı yoklar; pencereler `$12CC–$12D3`, `$15F0`, `$1636–$1637`; yazma yok). Kullanıcı hoparlörün **güç kablosunu** çekip geri taktı (USB Mac'te takılı kaldı). Cihaz USB'den kayboldu ve yeniden belirdi → CX soğuk açıldı. Kayıt: scratchpad `boot_watch_final.log`.

| t (sn) | olay |
|---|---|
| 58,3 | cihaz KAYBOLDU |
| 84,034 | cihaz BELİRDİ |
| **84,072** | **ilk okuma: canlı kazanç `E5A7/E5A7`**, `idx=0xFF`, çerçeve uzunluğu 0, sayaç 0 |
| 84,169 / 84,201 | sol / sağ kanal `ED00`'a değişti (macOS geri yüklemesi; belirmeden +0,135 / +0,167 sn) |
| 86,227 | `$15F0 = 0x11 (17)`, çerçeve uzunluğu `0x04` (`CC 00 01 idx` gönderimi) |
| 86,385…86,964 | sayaç 1→5 (aynı değer toplam 6 kez, ~130–160 ms arayla) |
| 88,482 | çerçeve uzunluğu `0x13` (HID++ trafiği) |

**Sonuçlar:**
- **Cihazın güç-açılış kazancı `0xE5A7` (−26,35 dB, eğri idx 10) — doğrulandı** (host müdahale etmeden önceki ilk okuma). EEPROM `@0x120` yapılandırma değeriyle aynı.
- macOS bunu belirmeden ~0,13 sn sonra eziyor → `g560_volume.swift get` ile varsayılan hiçbir zaman gözlenemezdi.
- CX ses indeksini ilk kez ~2,2 sn sonra hesaplayıp MCU'ya yolluyor (`$15F0` önce `0xFF`). Bu denemede kazanç o ana kadar `ED00` olduğundan **`10` hiç gönderilmedi, doğrudan `17`**. Gönderim sayısı yamadaki `cpx #5` sınırıyla tutarlı (6 gönderim).
- **MCU'daki `25` (`0x19`) yalnızca CX'in ilk mesajına kadar (~2 sn) geçerli** → varsayılanı değiştirmek için hedef MCU değil. USB host'suz (yalnız BT/aux) kullanımda etkili varsayılan, koddaki ters aramadan, **idx 10** olmalı (CX'in `10`'u MCU'ya gönderdiği bu deneyde GÖZLENMEDİ, macOS araya girdi; USB okumasıyla gözlenemez).
- Varsayılanı değiştirmek için olası hedef: EEPROM `@0x120–0x121` (`a7 e5`). RAM'deki dört `E5A7` kopyasının da buradan türediği muhtemel ama doğrulanmadı; yeni değer eğri tablosunda tam bir giriş olmalı (ters arama "≤" bulur). **Yazma yapılmadı.** fwupd yazma sırası (park → 32 B yaz+geri-oku doğrula → unpark) ve kurtarma riskleri ayrı karar.

## Risk ve kurtarma araştırması — 9. tur (2026-10-07; yazma YAPILMADI)

**Yedekler (projede, `firmware/backup/`):** `g560_cx_eeprom_fw122.3.23_20261007.bin` (32 KiB, sha256 `787c708a…29df`, cihazdan HID ile okundu, 122.3.23 imajıyla bayt bayt aynı) ve `g560_cx_rom_7000-ffff_20261007.bin` (ROM, sha256 `26fb5cbb…8073`).

**Web:** CX2070x'e özel bir kurtarma belgesi, G560 "brick" raporu veya resmi Logitech kurtarma prosedürü **bulunamadı**. Logitech 122.2.22 aracı talimatı: güncelleme sırasında USB'yi çekme/tuşlara basma; araç "artık desteklenmiyor". Aşağıdaki kurtarma yolları dolaylı kanıta dayanır.

**Kanıtlar (yerel):**
- ROM varsayılan USB kimliği **`0572:1410`** (Conexant, "CONEXANT USB AUDIO") @ROM 0xED47. EEPROM geçersizse cihaz (ROM sağlamsa) büyük olasılıkla bu kimlikle görünür.
- **ROM'un varsayılan HID tanımlayıcısı (0xEF20) bellek erişim raporlarını (kimlik 4/5/6/7) zaten içeriyor** → geçersiz EEPROM durumunda da aynı HID yoluyla yeniden yazma mümkün olmalı (doğrulanmadı: ROM bu durumda HID'i gerçekten sunar mı?). fwupd'un "EEPROM is missing or blank" mesajı, boş EEPROM'lu aygıtla HID konuşulabildiği ima ediyor (kuvvetli ipucu, kanıt değil).
- **Satıcı yazma disiplini:** Windows aracı `invalidating header` → blokları yaz+doğrula → `validating header` ve `write magic failed`, `verification failed`, CX2070x için `forcing delay after write operation` (yazmadan sonra gecikme). Aynı disiplin S37 kayıt sırasında görünüyor: ilk kayıt `0x14 ← 0x00` (yama imzasını geçersiz kıl), son kayıtlar `0x20`, `0x25`, `0x4EB7 ('CX4')`, en son `0x14 ← 'P'` (geçerli kıl). Geçerlilik işaretleri: `'L'`@0x00, `'P'`@0x14, `'S'`@0x29, `CX4`; **EEPROM içeriği için CRC/sağlama toplamı kanıtı yok** (fwupd ve satıcı aracında S37 kayıt sağlama toplamı dışında yok; ROM'un açılışta ayrıca doğrulayıp doğrulamadığı bilinmiyor).
- Windows aracının dört kurtarma/yükleme yolu: `I2C bootloader`, `UART bootloader`, `ROM bootloader`, `Other Reno bootloader` (+ `Blanking EEPROM contents`, `EEPROM not detected/is valid`). ROM'da UART indirme yolu da var (`Download initiated ..`).
- fwupd yazma sırası: park (`$1000` bit7) → 32 B parçaları EEPROM'a yaz+geri-oku doğrula → eski yamayı geçersiz kıl (yalnız tam imajda) → unpark. EEPROM bellek sınırı 32 KiB (`'L'` boyut kodu 7).

**Önerilen en küçük değişiklik (YAPILMADI):** EEPROM `@0x120–0x121` (`a7 e5` → yeni eğri girişi), **2 bayt**, tek parça. Tam imaj yazılmaz; `'L'`, `'P'`, `'S'`, `0xBC`, seri no, `0x7FFD` ve yama bölgesi (0xB50+) **asla** yazılmaz.

**Önlemler:** yazmadan önce tam EEPROM'u yeniden dök ve hash'i yedekle karşılaştır; **etkisiz yazma testi** (aynı `a7 e5`'i geri yaz → yazma yolu, yazma koruması, gecikme doğrulanır, içerik değişmez); park/unpark `try/finally`; yazmadan sonra ≥20–50 ms bekle, geri oku; sonda tam döküm farkı **tam 2 bayt** olmalı; güç döngüsü sonrası cihaz `046d:0a78` olarak gelmeli ve `cx_boot_watch.py` ilk kazancı doğrulamalı.

**Kurtarma basamakları (hafiften ağıra):** (1) güç döngüsü (park RAM durumudur); (2) orijinal 2 baytı aynı yolla geri yaz; (3) cihaz ROM kimliğiyle (`0572:1410`) gelirse yedek EEPROM'u HID ile geri yaz (en kritik varsayım doğrulanmadı); (4) donanım: CX kartındaki EEPROM'a harici programlayıcı (kasa açma, sızdırmazlık/yapıştırıcı mühürleri; EEPROM'un yeri/WP durumu bilinmiyor) veya Windows aracının UART/I2C bootloader yolu; (5) Logitech destek/garanti (araç desteksiz, garanti riski).

## Açık sorular / riskler

- Açılış animasyonu nerede? (LED mantığı: 0x8070 fonksiyonları 0x0800c300 tablosunda, ayrıntılı çözülmedi.)
- Açılış sesi: gerçekten CX'in idx 10'u mu geçerli? macOS okuma testi işe yaramadı (macOS son sesi geri yüklüyor). Gözlem için USB dinleyici (donanım sniffer), Linux/Windows host (geri yükleme davranışı farklı) ya da CX ROM'u gerekir. Değiştirmek için CX yapılandırma baytları (`0xe5a7`, imaj 0x120) mı yoksa MCU `0x19` mu hedeflenmeli? CX imajının S37 kontrol toplamları dışında bir bütünlük kontrolü ("LayoutSignature/Bad Checksum" dizeleri güncelleyicide var) bilinmiyor.
- HID++ standart özellikleri (IRoot/FeatureSet/FWVersion/DeviceName, idx 0–3,5,6) CX'te mi ROM'da mı? CX'in HID++ yönlendirme kodu (93/D3 gönderimleri) tam çözülmedi.
- RACE UUID'li gizli RFCOMM servisi kullanıcının cihazında var mı? SDP ve kanal 1–30 taraması bulamadı ama ikisi de kanıtlayıcı değil; kesin cevap için macOS dışı bir BT ucu (Linux/Windows `sdptool`/`bluetoothctl`, ya da HCI sniffer) gerekir.
- Kullanıcının BT çipi gerçekten CSR mi? Yalnız adres aralığı/yapılandırma etiketinden çıkarım; çip kimliği (LMP manufacturer/subversion) okunmadı.
- Cihaz tarafı önyükleyici imza istiyor mu? Yükleme protokolü (CX: CAPE/HID; MCU: ?) çözülmedi.
- Güncelleyici Windows'a özel; macOS'ta yazmak için protokolü çözmek ya da Windows VM + USB aktarımı gerekir.
- Yanlış imaj = brick riski. Önyükleyici bölgesi (0x08000000–0x08003FFF) dokunulmaz görünüyor, kurtarma yolu olabilir ama doğrulanmadı.
- BT kontrol kanalı eklemek bu imajlarla mümkün değil: BT çipinin firmware'i ayrı (şifreli/yok).
