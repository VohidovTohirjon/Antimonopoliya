# Raqobat AI Assistant

Raqobat qo‘mitasi rahbariyati va xodimlari uchun hujjat tahlili, huquqiy RAG qidiruvi, rasmiy hujjat loyihalari va topshiriqlar nazoratini bitta o‘zbekcha interfeysda birlashtirgan ichki axborot tizimi.

## Arxitektura

- `frontend/` — React, TypeScript va Vite asosidagi responsive interfeys.
- `backend/` — FastAPI REST API, JWT autentifikatsiya va qat’iy backend RBAC.
- PostgreSQL + pgvector — foydalanuvchilar, hujjatlar, NHH, vektorlar, tarix, topshiriqlar va audit.
- BGE-M3 — o‘zbekcha va huquqiy matnlarga mos alohida embedding modeli.
- LLM — bitta OpenAI-mos provayder abstraksiyasi: production'da o‘z serveringizdagi vLLM (`openai/gpt-oss-20b`), ixtiyoriy ravishda Groq. Kalitlar faqat serverda.
- Fayllar — backend nazoratidagi `DATA_DIR` ichida saqlanadi; yuklash va AI qidiruvi ruxsat bilan cheklanadi.

Jarayon: fayl → turini tekshirish → parsing → strukturali chunklar → embedding → pgvector. Savol → AI orchestrator intent tekshiruvi → ruxsat filtri → gibrid qidiruv → mavzu va relevance filtri → article/overlap deduplikatsiyasi → barqaror dalil tartibi → backend bergan citation raqamlari → cheklangan kontekst → Groq (`temperature=0`) → hujjat/modda/raqam/sana/citation/iqtibos grounding validatsiyasi → faqat haqiqatan ishlatilgan manbalar.

Grounding tekshiruvi o‘tmasa tizim ko‘pi bilan bir marta cheklangan tuzatish so‘raydi. Ikkinchi urinish ham o‘tmasa generativ matn foydalanuvchiga chiqarilmaydi: faqat bazadan olingan, citation bilan bog‘langan asl parchalar aniq fallback yorlig‘i ostida ko‘rsatiladi. Shu sabab ilova “hallucination imkonsiz” deb da’vo qilmaydi; kafolat shuki, dalilda yo‘q huquqiy identifikator va citation tasdiqlangan huquqiy javob sifatida qabul qilinmaydi.

Foydalanuvchi tanlagan rejim — bu shartnoma, taxmin emas. `mode="general"` tanlansa savol matnida “qonun”, “modda” yoki “konstitutsiya” bo‘lsa ham so‘rov hech qachon huquqiy RAG ga o‘tkazilmaydi: aynan bitta oddiy LLM javobi qaytadi, qidiruvsiz va manbasiz. `mode="legal"` NHH korpusidan qidiradi va faqat tasdiqlangan manba asosida javob beradi; yetarli dalil bo‘lmasa boshqa qonunni manba sifatida ko‘rsatmasdan “yetarli huquqiy asos topilmadi” deb javob beradi. Avtomatik intent aniqlash faqat alohida `mode="auto"` rejimida ishlaydi.

## Talablar

- Python 3.11 yoki 3.12
- Node.js 20+
- Docker va Docker Compose (PostgreSQL/pgvector uchun tavsiya etiladi)
- Lokal vLLM (OpenAI-mos endpoint) yoki Groq API kaliti
- BGE-M3 ni birinchi ishga tushirishda yuklash uchun internet, so‘ng model lokal keshdan ishlaydi

## Sozlash

```bash
cp .env.example .env
```

`.env` ichida kamida quyidagilarni to‘ldiring:

```env
SECRET_KEY=kamida-32-belgili-tasodifiy-maxfiy-qiymat
GROQ_API_KEY=groq-api-kalitingiz
GROQ_MODEL=
GROQ_MODELS=openai/gpt-oss-120b,qwen/qwen3.6-27b,openai/gpt-oss-20b,groq/compound,groq/compound-mini
```

## LLM provayder

Ilova bir vaqtning o‘zida bitta OpenAI-mos `chat/completions` endpointi bilan ishlaydi. vLLM va Groq faqat base URL, kalit, model puli va bir nechta so‘rov nuansi bilan farq qiladi, shuning uchun ikkalasi ham bitta `OpenAICompatibleProvider` klassi orqali ishlaydi (`app/services/llm.py`). RAG, grounding, citation va validatsiya qatlamlari qaysi provayder javob berganini bilmaydi.

`LLM_PROVIDER=local` bo‘lganda lokal server **asosiy** hisoblanadi. Groq faqat `LLM_FALLBACK_ENABLED=true` bo‘lgandagina va faqat lokal server xato qaytargandan keyin ishlatiladi — avtomatik emas.

Lokal serverga moslashuv nuanslari provayder profilida saqlanadi: vLLM `max_tokens` kutadi (Groq `max_completion_tokens`), Groq’ning `include_reasoning`/`reasoning_effort` kalitlari lokal serverga yuborilmaydi, va agar server strict `json_schema` formatini rad etsa, so‘rov bir marta oddiy `json_object` rejimida qayta yuboriladi (bitta modelli serverda failover uchun sherik yo‘q).

### Kechikishni kamaytirish qoidalari

Har bir so‘rov turi o‘z completion budjetiga ega — qisqa chat javobi ko‘p sahifali rasmiy loyiha bilan bir xil decode budjetini band qilmaydi. gpt-oss uchun `reasoning_effort=low` yuboriladi va fikrlash matni foydalanuvchiga hech qachon ko‘rsatilmaydi (faqat `content` o‘qiladi).

Grounding validatsiyasidan o‘tmagan javob endi ikki xil ko‘riladi. Uydirilgan modda, citation, raqam, sana, iqtibos yoki hujjat identifikatori — bu **faktik** xato: ikkinchi generatsiya qilinmaydi, darhol tekshirilgan ekstraktiv javobga o‘tiladi (tezroq ham, xavfsizroq ham). Faqat format/sxema darajasidagi xato (citation qo‘yilmagan, blok tuzilmasi buzilgan) bitta tuzatish chaqirig‘iga arziydi.

Umumiy savol vektor qidiruv, huquqiy filtr, modda deduplikatsiyasi va groundingni umuman ishga tushirmaydi — huquqiy niyat aniqlangandagina RAG yo‘liga o‘tiladi. Deterministik yo‘llar (arifmetika, aniq hujjat faktlari, 40% kabi qonuniy chegaralar) LLMsiz ishlaydi.

`GROQ_MODELS` vergul bilan ajratilgan priority ro‘yxatidir. Birinchi model 429 rate-limit qaytarsa, backend `retry-after` muddatiga uni cooldown holatiga qo‘yib, shu so‘rovning o‘zida keyingi modelga o‘tadi. Muddat tugagach yuqori priority model avtomatik qayta ishlatiladi. Eski `GROQ_MODEL` qiymati berilsa, u ro‘yxatning boshiga qo‘yiladi. `GROQ_API_KEY` frontendga uzatilmaydi. Ishlab chiqarishda `DATABASE_URL`, PostgreSQL paroli, `DATA_DIR` va `CORS_ORIGINS` ham xavfsiz muhitga moslashtirilishi shart.

Asosiy o‘zgaruvchilar:

| O‘zgaruvchi | Vazifasi |
|---|---|
| `DATABASE_URL` | PostgreSQL ulanish satri |
| `SECRET_KEY` | JWT imzolash kaliti, kamida 32 belgi |
| `LLM_PROVIDER` | `local` (o‘z vLLM serveringiz) yoki `groq`. Standart: `groq` |
| `LLM_FALLBACK_ENABLED` | Zaxira provayderni yoqadi. Standart `false` — zaxira hech qachon avtomatik ishlatilmaydi |
| `LLM_FORCE_UNAVAILABLE` | Diagnostika uchun barcha provayderlarni o‘chiradi |
| `LOCAL_LLM_BASE_URL` | Lokal OpenAI-mos endpoint, `/v1` bilan tugaydi |
| `LOCAL_LLM_API_KEY` | vLLM `--api-key` bilan ishga tushirilgan bo‘lsa; aks holda bo‘sh |
| `LOCAL_LLM_MODEL` | Asosiy lokal model, masalan `openai/gpt-oss-20b` |
| `LOCAL_LLM_MODELS` | Ixtiyoriy qo‘shimcha modellar, vergul bilan |
| `LOCAL_LLM_TIMEOUT_SECONDS` | Lokal server uchun timeout; standart `120` |
| `LOCAL_LLM_MAX_TOKENS` | Lokal completion budjeti; standart `3200` |
| `LOCAL_LLM_STRICT_SCHEMA` | `json_schema` structured output ishlatiladimi; standart `true` |
| `LOCAL_LLM_REASONING_EFFORT` | gpt-oss fikrlash chuqurligi; standart `low`. Sifat yetmasa `medium` |
| `LLM_MAX_TOKENS_GENERAL` | Umumiy chat budjeti; standart `512` |
| `LLM_MAX_TOKENS_LEGAL` | Huquqiy javob budjeti; standart `1024` |
| `LLM_MAX_TOKENS_DOCUMENT` | Hujjat tahlili budjeti; standart `1024` |
| `LLM_MAX_TOKENS_DRAFTING` | Rasmiy loyiha/DOCX budjeti; standart `3200` |
| `GROQ_API_KEY` | Serverdagi Groq API kaliti |
| `GROQ_MODEL` | Ixtiyoriy eski bitta-model override; berilsa eng yuqori priority bo‘ladi |
| `GROQ_MODELS` | 5 ta Groq model/system priority ro‘yxati va avtomatik failover |
| `GROQ_FORCE_UNAVAILABLE` | Faqat UAT/diagnostika uchun provayderni majburan o‘chirish; standart `false` |
| `GROQ_MAX_TOKENS` | Javob/DOCX loyihasi uzilib qolmasligi uchun completion budjeti; standart `3200` |
| `EMBEDDING_MODEL` | Standart: `BAAI/bge-m3` |
| `EMBEDDING_BACKEND` | Ishlab chiqarishda `sentence_transformers` |
| `EMBEDDING_DIMENSIONS` | BGE-M3 uchun `1024`; migratsiya bilan bir xil bo‘lishi kerak |
| `EMBEDDING_WARMUP_ON_STARTUP` | Modelni server startida bloklamasdan fon rejimida tayyorlash |
| `RETRIEVAL_MIN_SCORE` | Yetarli dalil bo‘lmagan qidiruvni rad etish chegarasi; standart `0.48` |
| `RETRIEVAL_CANDIDATE_LIMIT` | Semantik + kalit so‘zli gibrid saralash uchun nomzodlar soni |
| `DATA_DIR` | Himoyalangan fayllar katalogi |
| `CORS_ORIGINS` | Ruxsat etilgan frontend manzillari, vergul bilan |
| `LOCAL_SEED_PASSWORD` | **Faqat development.** Lokal seed *yangi* yaratadigan hisoblar paroli; standart `12345678`. Mavjud hisob paroliga hech qachon tegmaydi. Productionda o‘rnatilmasin |
| `VITE_API_URL` | Frontend foydalanadigan backend manzili |

## PostgreSQL va pgvector

Docker Desktop yoki Docker daemon ishlayotganida:

```bash
docker compose up -d db
```

Compose `pgvector/pgvector:pg16` tasviridan foydalanadi va `vector` kengaytmasini migratsiya yaratadi. Mavjud PostgreSQL ishlatilsa, foydalanuvchi `CREATE EXTENSION vector` huquqiga ega bo‘lishi kerak.

## Backend

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
alembic upgrade head
python -m app.cli --username admin --password 'mustahkam-parol' --full-name 'Tizim administratori'
uvicorn app.main:app --reload --port 8000
```

API hujjatlari: `http://localhost:8000/api/docs`.

Server ochilishi embedding modelining yuklanishini kutmaydi: health, login va reload darhol ishlaydi, model fon rejimida tayyorlanadi. Oddiy AI sahifasida faqat “tayyor/tayyorlanmoqda” holati ko‘rsatiladi; model, provider va indeks diagnostikasi faqat Administrator panelida. Birinchi o‘rnatishda model katta bo‘lgani uchun yuklash davom etishi mumkin, ammo sayt qotib qolmaydi.

Administrator CLI buyrug‘i parolni bcrypt bilan xeshlab saqlaydi va bir xil loginni takroran yaratmaydi. Ochiq ro‘yxatdan o‘tish yo‘q.

CLI buyrug‘i faqat administratorni birinchi marta yaratish yoki uning nom/parolini ataylab yangilash kerak bo‘lganda bajariladi. Oddiy backend startida uni qayta yozish shart emas.

## Frontend

Boshqa terminalda, loyiha ildizidan:

```bash
cd frontend
npm install
npm run dev
```

Interfeys: `http://localhost:5173`. Port band bo‘lsa Vite boshqa portga yashirin o‘tmaydi; avval eski frontend jarayonini to‘xtating. Production build:

```bash
cd frontend
npm run build
```

## Testlar

Testlar tashqi Groq chaqirig‘ini deterministik adapter bilan almashtiradi va SQLite + hash embeddingdan faqat izolatsiyalangan test muhiti sifatida foydalanadi. Ishlab chiqarish konfiguratsiyasi PostgreSQL/pgvector + BGE-M3 bo‘lib qoladi.

```bash
source .venv/bin/activate
cd backend
pip install -r requirements-dev.txt
pytest -q
```

Frontend regression testlari va production build:

```bash
cd frontend
npm test
npm run build
```

Migratsiyaning PostgreSQL SQL natijasini tekshirish:

```bash
cd backend
alembic upgrade head --sql
```

Ishlayotgan serverdagi rol chegaralarini tekshirish (faqat o‘qiydi, token chop etmaydi). Parollar hech qachon skriptga qattiq yozilmaydi:

```bash
cd backend
RBAC_CHECK_XODIM_PASSWORD=... RBAC_CHECK_RAHBAR_PASSWORD=... python scripts/check_rbac_api.py --base-url http://127.0.0.1:8000
```

Huquqiy qidiruv marshrutlarini deterministik tekshirish (ustun mavqe → 13-modda, suiiste’mol → 18-modda, kelishuvlar → 19-modda, savdolar → 29-modda):

```bash
cd backend
python scripts/check_retrieval.py --username admin
```

## Qo‘llab-quvvatlanadigan hujjatlar

- PDF — sahifalar bo‘yicha matn ajratiladi.
- DOCX — paragraflar va jadvallar o‘qiladi.
- XLSX — varaqlar va mazmunli katak qatorlari o‘qiladi.

Backend faqat kengaytmaga ishonmaydi: PDF sarlavhasi va Office ZIP ichki tuzilmasi tekshiriladi. Bo‘sh, buzilgan, turi mos kelmagan yoki hajm chegarasidan oshgan fayl rad etiladi.

## Rollar

- **Administrator** — barcha talab qilingan funksiyalar, foydalanuvchilar va rollar ko‘rinishi, NHH yuklash/metadata/qayta indekslash/o‘chirish, AI tarixi va audit.
- **Rahbar** — dashboard, AI chat, hujjat tahlili, hisobot/ma’lumotnoma, topshiriq yaratish va monitoring.
- **Xodim** — AI chat, hujjat yuklash va tahlil, hujjat loyihalari, o‘z topshiriqlari va o‘z AI tarixi.

Rollar backend endpointlarida tekshiriladi. Oddiy hujjat ichki jamoa uchun umumiy ko‘rinadi; “Maxfiy hujjat” belgisi qo‘yilgan faylni esa faqat egasi va administrator ko‘ra, yuklay va tahlil qila oladi. RAG qidiruvi ham ayni ruxsat filtrini SQL darajasida qo‘llaydi, shuning uchun boshqa xodimning maxfiy chunklari kontekstga kirmaydi.

## Amaliy oqim

1. Administrator NHH faylini nomi, turi va manba havolasi bilan yuklaydi.
2. Rahbar yoki xodim PDF/DOCX/XLSX fayl yuklaydi.
3. Hujjat sahifasida qisqacha mazmun, asosiy bandlar, savol-javob yoki qarama-qarshilik tahlilini tanlaydi.
4. AI yordamchida huquqiy savol beradi; javob bilan hujjat nomi, modda/band, havola va foydalanilgan parcha ko‘rinadi.
5. Hujjat loyihalari bo‘limida javob xati, hisobot, ma’lumotnoma, qisqa ma’lumot yoki tahliliy xulosa tayyorlaydi.
6. Natijani haqiqiy DOCX fayl sifatida yuklaydi; operatsiya AI tarixida saqlanadi.

Javob xati uchun eksport ikki qatlamga ajratilgan:

- `Qoralama DOCX` — to‘ldirilmagan rasmiy maydonlarni ochiq placeholder va `QORALAMA` belgisi bilan beradi;
- `Rasmiy DOCX` — faqat tashkilot rekvizitlari, qabul qiluvchi, sana va chiqish raqami to‘liq bo‘lganda ochiladi;
- `Ichki dalillar` — citation, NHH, modda/band va rasmiy URL mappingini alohida xizmat hujjatida saqlaydi.

Tashqi xatda `[1]`, `[2]` kabi ichki RAG belgilari chiqarilmaydi. Huquqiy norma NHH metama’lumotidan formal nom bilan yoziladi. Tashkilot nomi, ikkinchi tildagi nom, yuqori turuvchi tashkilot, bo‘lim, manzil, aloqa, STIR/INN, logo, chiqish prefiksi, imzolovchi hamda ixtiyoriy letterhead/footer, verifikatsiya/barcode qiymatlari Administrator panelidagi `Tashkilot profili`dan olinadi; eksport kodida hardcode qilinmaydi.

NHH bazasida yetarli mos manba bo‘lmasa, huquqiy javob yoki javob xati uchun tizim asos topilmaganini aytadi va soxta manba yaratmaydi.

Huquqiy qidiruv Lotin yozuvidagi savollar bilan Kirill yozuvidagi rasmiy NHH matnlarini ham gibrid (semantik + kalit so‘z) usulida moslashtiradi. NHH bazasi bo‘sh bo‘lsa, tizim modelni behuda ishga tushirmaydi va administratorga hujjat yuklash bo‘yicha aniq ko‘rsatma beradi.

Groq sozlanmagan yoki vaqtincha javob bermagan holatda huquqiy qidiruv ishlashda davom etadi. Tanilgan huquqiy mavzular uchun routing, to‘liq modda dalili, tuzilmali faktlar, raqamli mezonlar va citationlar provayderdan mustaqil tayyorlanadi. Umumiy savollar va qo‘shimcha generativ imkoniyatlar uchun amaldagi Groq kaliti hamda model nomi talab qilinadi. `GROQ_FORCE_UNAVAILABLE=true` faqat UAT/diagnostika jarayonida shu chegarani tekshirish uchun mo‘ljallangan.

Maxfiy hujjat va `Idoraviy (ichki) hujjat` matni server tomonda tashqi AI adapteriga uzatilmaydi. Standart siyosat `ALLOW_EXTERNAL_CONFIDENTIAL_AI=false`; bunday material deterministic/extractive lokal oqimda qayta ishlanadi yoki lokal imkoniyat yetarli bo‘lmasa aniq qo‘llab-quvvatlanmagan holat qaytariladi. Ushbu bayroq faqat tashkilotning hujjatlashtirilgan, vakolatli qarori bilan yoqilishi kerak. Ochiq NHH uchun tasdiqlangan rasmiy URL majburiy, ichki NHH uchun esa tashqi URL ixtiyoriy.

Provider xatolari bir xil `502`ga yashirilmaydi: rate limit `429`, timeout `504`, autentifikatsiya/model yoki vaqtinchalik upstream nosozligi foydalanuvchiga xavfsiz va aniq xizmat xabari bilan qaytariladi. Bo‘sh, noto‘g‘ri formatdagi yoki token chegarasida uzilgan completion muvaffaqiyat hisoblanmaydi. `openai/gpt-oss-*` modellari uchun reasoning past darajada va foydalanuvchi javobidan alohida boshqariladi.

Huquqiy javob va javob xatidagi `[1]`, `[2]` kabi raqamlar model tomonidan erkin belgilanmaydi. Backend manbalarni oldindan deduplikatsiya qilib raqamlaydi va modelga faqat shu raqamlarni beradi. Mavjud bo‘lmagan raqam javobni groundingdan yiqitadi; u shunchaki matndan o‘chirilib, qolgan gap tasdiqlanmaydi. Frontend faqat yakuniy javobda citation qilingan manbalarni ayni backend raqami bilan ko‘rsatadi. AI javobi va tarix xavfsiz Markdown/GFM rendererida ko‘rsatiladi; xom HTML bajarilmaydi.

## Production deploy (bitta VM)

To'liq qadamma-qadam yo'riqnoma: **[deploy/README.md](deploy/README.md)**.

```bash
cp .env.production.example .env   # va qiymatlarni to'ldiring
./deploy/deploy.sh
```

`APP_ENV=production` bo'lganda backend ishga tushishdan oldin konfiguratsiyani
tekshiradi: `LLM_PROVIDER` aniq ko'rsatilmagan bo'lsa yoki lokal provayder uchun
`LOCAL_LLM_BASE_URL`/`LOCAL_LLM_MODEL` bo'sh bo'lsa, **ishga tushmaydi**. Bu
tasodifan tashqi provayderga o'tib ketishning oldini oladi.

## Rasmiy huquqiy korpus

`legal-corpus/` katalogida rasmiy NHH fayllari va `manifest.json` saqlanadi.
Korpus admin UI bilan bir xil parsing/indekslash yo'lidan import qilinadi:

```bash
cd backend && python scripts/import_nhh.py --admin-username admin
```

```bash
cd backend && python scripts/import_nhh.py --status
```

`--status` hujjatlar soni, parchalar soni va faol/indekslangan hujjatlar sonini
ko'rsatadi. Buyruq idempotent: mavjud hujjat qayta import qilinmaydi
(`--reindex` bilan majburan qayta indekslash mumkin).

## Operatsion namuna ma’lumotlari

Seed faqat aniq development bayrog‘i bilan ishlaydi va production startida avtomatik chaqirilmaydi:

```bash
source .venv/bin/activate
cd backend
python scripts/seed_operational_data.py --confirm-development --admin-username admin
```

Seed **faqat o‘zi yaratadigan** yangi hisoblarga parol beradi. Parol manbai, ustuvorlik tartibida:

1. `--seed-password <parol>` argumenti;
2. `LOCAL_SEED_PASSWORD` muhit o‘zgaruvchisi;
3. standart qiymat — `12345678`.

Fresh local/dev seed hisoblari (standart parol bilan):

- `rahbar_analitika` / `12345678`
- `xodim_huquq` / `12345678`

**FAQAT DEVELOPMENT UCHUN.** Bu sodda parol faqat `--confirm-development` bilan ataylab ishga tushiriladigan lokal namuna uchun. Allaqachon mavjud hisobning parol hashi seed qayta bajarilganda ham, migratsiya paytida ham hech qachon o‘zgartirilmaydi — administrator qo‘ygan parol saqlanib qoladi (buni `test_institutional_letter.py` regressiya testlari qulflab qo‘yadi). Productionda `LOCAL_SEED_PASSWORD` ni umuman o‘rnatmang va bu hisoblardan foydalanmang; foydalanuvchilarni Administrator paneli orqali tashkilot siyosatiga mos vaqtinchalik parol bilan yarating va secretlarni boshqariladigan muhitda saqlang.

U real parser va indekslash oqimi orqali `sample-data/` dagi murojaat DOCX, ikki sahifali tahliliy PDF, qarama-qarshi muddatli bayonnoma DOCX va statistik XLSXni yuklaydi. Shuningdek, uchta rol bo‘yicha ish oqimini tekshirish uchun ichki hisoblar va yangi/jarayonda/bajarilgan/kechikkan holatlardagi topshiriqlar yaratadi. Ularning kelib chiqishi UI sarlavhasida emas, faqat ichki `seed_key` metama’lumotida saqlanadi. Buyruq idempotent: takroriy ishga tushirish dublikat yaratmaydi.

Faqat operatsion namuna hujjat va topshiriqlarni tozalash:

```bash
cd backend
python scripts/seed_operational_data.py --confirm-development --admin-username admin --reset --reset-only
```

Namuna ma’lumotlarini qayta yaratish uchun `--reset` bayrog‘ini `--reset-only`siz ishlating.

Groq rate-limit yoki vaqtinchalik nosozlik sabab javob xatini generatsiya qila olmasa, endpoint xato bilan to‘xtab qolmaydi: murojaat va tekshirilgan NHH parchalaridan aniq ogohlantirishli, mas’ul xodim tahriri talab qilinadigan DOCX loyiha tayyorlaydi.

Lex.uz sahifasi skanerlangan PDF bersa, oldindan saqlangan rasmiy HTML sahifani matnli DOCXga aylantirish mumkin:

```bash
python backend/scripts/lexuz_html_to_docx.py lexuz.html qonun.docx --source-url https://lex.uz/docs/6518381
```

Konvertor tarmoqqa chiqmaydi; u faqat berilgan lokal HTML nusxani o‘qiydi. Hosil bo‘lgan DOCX Administrator paneli orqali manba havolasi bilan yuklanadi.
