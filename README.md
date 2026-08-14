# Raqobat AI Assistant

Raqobat qo‘mitasi rahbariyati va xodimlari uchun ishlab chiqilgan ichki axborot tizimi.

Tizim hujjatlarni tahlil qilish, normativ-huquqiy hujjatlar bo‘yicha qidiruv, hujjat loyihalarini tayyorlash, topshiriqlarni boshqarish va rahbariyat monitoringini yagona interfeysda birlashtiradi.

## Holati

Loyihaning asosiy funksiyalari yakunlangan va ishlaydigan holatga keltirilgan.

Asosiy texnologiyalar:

- React + TypeScript + Vite
- FastAPI
- PostgreSQL + pgvector
- SQLAlchemy + Alembic
- JWT autentifikatsiya
- BGE-M3 embeddings
- Groq API
- PDF, DOCX va XLSX parsing

## Asosiy imkoniyatlar

### AI yordamchi

AI yordamchi normativ-huquqiy hujjatlar bazasi asosida savollarga javob beradi.

Huquqiy javob bilan birga:

- hujjat nomi;
- modda yoki band;
- rasmiy manba havolasi;
- foydalanilgan matn parchasi

ko‘rsatiladi.

Tizimda yetarli huquqiy asos topilmasa, mavjud bo‘lmagan modda yoki manba yaratilmaydi.

### Hujjatlar va tahlil

Qo‘llab-quvvatlanadigan formatlar:

- PDF
- DOCX
- XLSX

Hujjat yuklangandan so‘ng:

- qisqacha mazmun;
- asosiy bandlar;
- hujjat bo‘yicha savol-javob;
- qarama-qarshiliklarni aniqlash

imkoniyatlari mavjud.

### Normativ-huquqiy hujjatlar bazasi

Administrator NHHlarni fayl va rasmiy manba havolasi bilan tizimga qo‘shadi.

NHH uchun:

- nom;
- kategoriya;
- rasmiy URL;
- fayl;
- indeks holati

saqlanadi.

Administrator hujjatni qo‘shishi, tahrirlashi, qayta indekslashi, faolsizlantirishi yoki o‘chirishi mumkin.

### Hujjat loyihalari

Tizim quyidagi hujjatlarni tayyorlaydi:

- javob xati;
- ma’lumotnoma;
- hisobot;
- qisqa ma’lumot;
- tahliliy xulosa.

Javob xati tashkilotning rasmiy rekvizitlari asosida DOCX ko‘rinishida tayyorlanadi.

Administrator tashkilot profilida:

- tashkilot nomi;
- yuqori turuvchi tashkilot;
- manzil;
- telefon;
- elektron pochta;
- veb-sayt;
- STIR/INN;
- logo yoki gerb;
- chiqish raqami prefiksi;
- imzolovchi ma’lumotlari;
- letterhead va footer ma’lumotlari

kabi rekvizitlarni boshqaradi.

Rekvizitlar to‘liq bo‘lmasa, hujjat qoralama sifatida chiqariladi.

Tashqi rasmiy xat va ichki dalillar varaqasi alohida hujjatlar sifatida shakllantiriladi.

## Topshiriqlar

Rahbar xodimlarga topshiriq biriktirishi va ularning bajarilishini kuzatishi mumkin.

Topshiriqda:

- nom;
- tavsif;
- mas’ul xodim;
- ustuvorlik;
- muddat;
- holat;
- o‘zgarishlar tarixi

saqlanadi.

Holatlar:

- Yangi
- Jarayonda
- Bajarildi

Muddatidan o‘tgan topshiriqlar avtomatik aniqlanadi.

Xodim o‘ziga biriktirilgan topshiriqlarning holatini yangilashi mumkin.

## Rollar

### Administrator

Administrator tizimni boshqaradi.

Imkoniyatlari:

- foydalanuvchi yaratish;
- foydalanuvchini tahrirlash;
- rolni o‘zgartirish;
- foydalanuvchini faolsizlantirish va o‘chirish;
- NHH bazasini boshqarish;
- tashkilot profilini sozlash;
- AI tarixini ko‘rish;
- audit jurnalini ko‘rish;
- tizim diagnostikasini ko‘rish.

### Rahbar

Rahbar ish jarayonlari va topshiriqlar monitoringi bilan ishlaydi.

Imkoniyatlari:

- boshqaruv paneli;
- AI yordamchi;
- hujjatlar;
- hujjat loyihalari;
- topshiriq yaratish;
- xodimga topshiriq biriktirish;
- kechikkan topshiriqlarni kuzatish;
- muhim hujjatlarni ko‘rish.

Dashboarddagi hujjat va topshiriqlar real yozuvlarga bog‘langan va bosilganda tegishli obyekt ochiladi.

### Xodim

Xodim kundalik ish jarayonlari bilan ishlaydi.

Imkoniyatlari:

- AI yordamchi;
- hujjat yuklash;
- hujjat tahlili;
- hujjat loyihalari;
- o‘z topshiriqlarini ko‘rish;
- topshiriq holatini yangilash;
- o‘z AI tarixini ko‘rish.

Administrator funksiyalari Rahbar va Xodim uchun yopiq.

## Maxfiylik va xavfsizlik

Maxfiy deb belgilangan hujjatlarni faqat hujjat egasi va Administrator ko‘ra oladi.

Ruxsatlar faqat interfeysda emas, backend API darajasida ham tekshiriladi.

Tizimda:

- JWT autentifikatsiya;
- bcrypt parol hashing;
- backend RBAC;
- hujjatlar uchun access control;
- audit tarixi;
- API kalitlarini server tomonda saqlash;
- fayl formatlarini serverda tekshirish;
- huquqiy javoblarni manbalar bilan bog‘lash

amalga oshirilgan.

Maxfiy va ichki hujjatlarni tashqi AI xizmatiga yuborish standart holatda o‘chirilgan.

## Loyiha tuzilishi

~~~text
Antimonopoliya/
├── backend/
│   ├── app/
│   ├── alembic/
│   ├── scripts/
│   └── tests/
├── frontend/
│   └── src/
├── sample-data/
├── docker-compose.yml
├── .env.example
└── README.md
~~~

## Ishga tushirish

### 1. Environment

~~~bash
cp .env.example .env
~~~

`.env` ichida kamida quyidagi qiymatlar sozlanadi:

~~~env
DATABASE_URL=
SECRET_KEY=
GROQ_API_KEY=
GROQ_MODELS=
DATA_DIR=
CORS_ORIGINS=
~~~

Haqiqiy `.env` Git repositoryga kiritilmaydi.

### 2. PostgreSQL

~~~bash
docker compose up -d db
~~~

### 3. Backend

Loyiha ildizida virtual environment yaratish:

~~~bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
~~~

Migratsiyalar:

~~~bash
cd backend
alembic upgrade head
~~~

Backendni ishga tushirish:

~~~bash
uvicorn app.main:app --reload --port 8000
~~~

Backend:

~~~text
http://localhost:8000
~~~

API hujjatlari:

~~~text
http://localhost:8000/api/docs
~~~

### 4. Frontend

Boshqa terminalda:

~~~bash
cd frontend
npm install
npm run dev
~~~

Frontend:

~~~text
http://localhost:5173
~~~

## Lokal administrator

Development/lokal muhit uchun administrator:

~~~text
Login: admin
Parol: 12345678
~~~

Kerak bo‘lsa administratorni CLI orqali yaratish yoki parolini yangilash mumkin:

~~~bash
cd backend

python -m app.cli \
  --username admin \
  --password '12345678' \
  --full-name 'Tizim administratori'
~~~

`12345678` faqat lokal/development muhiti uchun mo‘ljallangan. Production muhitida alohida kuchli parol ishlatilishi kerak.

## Testlar

Backend:

~~~bash
source .venv/bin/activate
cd backend
pytest -q
~~~

Frontend:

~~~bash
cd frontend
npm test -- --run
npm run build
~~~

Joriy migratsiya:

~~~bash
cd backend
alembic current
~~~

Loyihada autentifikatsiya, RBAC, huquqiy qidiruv, NHH, document QA, hujjat tahlili, DOCX eksport va boshqa asosiy workflowlar uchun regression testlar mavjud.

## Development namuna ma’lumotlari

Lokal muhit uchun namuna ma’lumotlarini yaratish:

~~~bash
source .venv/bin/activate
cd backend

python scripts/seed_operational_data.py \
  --confirm-development \
  --admin-username admin
~~~

Ushbu seed production muhitida avtomatik ishga tushmaydi.

`sample-data/` katalogida tizim funksiyalarini tekshirish uchun PDF, DOCX va XLSX namunalar mavjud.

## NHH va huquqiy qidiruv

Huquqiy qidiruv indekslangan NHH korpusi asosida ishlaydi.

Savolga mos manba topilganda tizim javob bilan birga hujjat, modda/band, manba havolasi va foydalanilgan parchani ko‘rsatadi.

Lotin yozuvidagi savollar Kirill yozuvidagi rasmiy hujjatlar bilan ham moslashtiriladi.

Tanilgan huquqiy mavzularda asosiy routing va faktlarni aniqlash tashqi generativ model mavjudligiga to‘liq bog‘liq emas.

Tashqi AI xizmati vaqtincha ishlamasa, manbaga asoslangan lokal/fallback oqimlar mavjud.

## Rasmiy DOCX eksport

Javob xati ikki asosiy holatda chiqariladi:

- Qoralama DOCX
- Rasmiy DOCX

Rasmiy DOCX faqat zarur tashkilot rekvizitlari, sana, chiqish raqami va adresat ma’lumotlari mavjud bo‘lganda yaratiladi.

Recipientga yuboriladigan rasmiy xatda ichki RAG citation identifikatorlari ko‘rsatilmaydi.

Ichki dalillar alohida DOCX sifatida saqlanadi.

Letterhead tashkilot profilidagi ma’lumotlardan generatsiya qilinadi va kod ichida tashkilot rekvizitlari hardcode qilinmaydi.

## Productionga o‘tkazish

Production muhitida quyidagilarni tashkilotning haqiqiy ma’lumotlari bilan sozlash kerak:

- tashkilot rekvizitlari;
- rasmiy logo yoki gerb;
- rasmiy NHH korpusi;
- PostgreSQL ulanish ma’lumotlari;
- `SECRET_KEY`;
- Groq API kaliti;
- CORS sozlamalari;
- foydalanuvchilarning xavfsiz parollari;
- server va fayl saqlash infratuzilmasi.

## Yakuniy holat

Loyihada quyidagi asosiy ish jarayonlari tayyor:

- login va autentifikatsiya;
- Administrator, Rahbar va Xodim rollari;
- backend RBAC;
- Administrator paneli;
- Rahbar dashboardi;
- Xodim ish maydoni;
- foydalanuvchilar boshqaruvi;
- hujjat yuklash va parsing;
- hujjat tahlili;
- hujjat bo‘yicha savol-javob;
- qarama-qarshiliklarni aniqlash;
- NHH boshqaruvi;
- huquqiy RAG qidiruvi;
- manbaga asoslangan AI javoblar;
- hujjat loyihalari;
- rasmiy DOCX eksport;
- tashkilot profili va letterhead;
- topshiriqlar boshqaruvi;
- task history;
- AI tarixi;
- audit jurnali;
- maxfiy hujjatlar uchun ruxsat nazorati.

Loyiha ishlab chiqish bosqichi yakunlangan va tashkilotning haqiqiy production ma’lumotlari bilan konfiguratsiya qilishga tayyor.
