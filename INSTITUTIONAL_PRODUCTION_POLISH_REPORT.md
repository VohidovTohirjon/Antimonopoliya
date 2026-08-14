# Raqobat AI Assistant — institutional-production polish hisoboti

Tekshiruv sanasi: 2026-08-13  
Muhit: real PostgreSQL 16 + pgvector, FastAPI, React/Vite, LibreOffice render

## Halollik bilan readiness ajratmasi

### A. Dastur/arxitektura tayyorligi

Ushbu yakuniy pass doirasidagi oqimlar production darajasida himoyalangan va regression testlangan: RBAC, task lifecycle, dashboard deep-link, generik NHH pipeline, manbaga bog‘langan legal/chat oqimi, hujjat tahlili, qoralama/rasmiy/ichki-dalil eksport ajratmasi va maxfiy material provider siyosati. Bu xulosa butun tashkiliy deployment, infratuzilma monitoringi yoki kelajakdagi barcha hujjatlar uchun mutlaq kafolat emas.

### B. Huquqiy korpus tayyorligi

Production-complete emas. Bazada faqat 1 ta tekshirilgan faol `Qonun` mavjud. Qolgan 6 kategoriya uchun generik upload → parse → legal structure → chunk → embedding → retrieval → citation oqimi regression testda ishladi, lekin haqiqiy rasmiy fayl/URL berilmagani sabab real korpusga soxta kontent qo‘shilmadi.

### C. Tashkilot konfiguratsiyasi tayyorligi

Production-complete emas. OrganizationProfile ekrani va PostgreSQL persistence tayyor, ammo real vakolatli rekvizitlar kiritilmagan. Shuning uchun UI rasmiy eksportni bloklaydi va faqat ochiq `QORALAMA` eksportiga ruxsat beradi.

## Joriy real PostgreSQL ko‘rsatkichlari

| Ko‘rsatkich | Joriy qiymat |
|---|---:|
| Administrator | 1 |
| Rahbar | 1 |
| Xodim | 2 |
| Hujjat | 5 |
| Faol NHH | 1 |
| NHH kategoriyalari | Qonun: 1 |
| Barcha indekslangan chunk | 125 |
| NHH chunk | 115 |
| Hujjat chunk | 10 |
| Topshiriq — yangi | 4 |
| Topshiriq — jarayonda | 3 |
| Topshiriq — bajarildi | 3 |
| Topshiriq — bekor qilindi | 0 |
| Kechikkan topshiriq | 2 |
| Alembic | 0010 (head) |
| Final UAT qoralama xati | 1 sahifa |
| Ichki dalillar varaqasi | alohida 1 sahifa |

Majburiy OrganizationProfile maydonlarining barchasi hozir bo‘sh: tashkilot nomi, manzil, telefon, e-pochta, veb-sayt, chiqish prefiksi, imzolovchi F.I.Sh. va lavozimi. Ixtiyoriy ikkinchi tildagi nom, yuqori turuvchi tashkilot, STIR/INN, letterhead/footer matni, bo‘lim, QR/verifikatsiya URL, barcode matni va logo ham sozlanmagan.

## Asosiy yakuniy tuzatmalar

- Qoralama va rasmiy eksport semantikasi ajratildi; incomplete profil bilan rasmiy eksport `422` qaytaradi.
- Tashqi xatdan xom `[1]`, `[2]` mapping olib tashlandi; formal NHH nomi va modda metama’lumotdan olinadi.
- Ichki dalillar alohida DOCX endpoint va UI action sifatida ajratildi.
- Qisqa javob xati evidence sabab 2 sahifaga cho‘zilmaydi; UAT namuna 1 sahifaga tushdi.
- OrganizationProfile’ga bo‘lim, elektron verifikatsiya URL va barcode matni, shuningdek ikkinchi tildagi rasmiy nom, yuqori turuvchi tashkilot, STIR/INN hamda ixtiyoriy letterhead/footer matni qo‘shildi; migrationlar `0009` va `0010` real PostgreSQLga qo‘llandi.
- Rahbar dashboardiga PostgreSQLdagi topshiriqlardan hisoblanadigan xodimlar ish yuklamasi: jami, faol, bajarilgan, kechikkan va bajarilish foizi qo‘shildi.
- Local/dev seed uchun yangi yaratiladigan Rahbar va Xodim hisoblari `12345678` parolidan foydalanadi; mavjud hisob parollari avtomatik almashtirilmaydi.
- Ochiq NHH uchun rasmiy URL majburiy; idoraviy/ichki NHH uchun ixtiyoriy.
- Maxfiy hujjat yoki ichki NHH tashqi providerga standart holatda yuborilmaydi (`ALLOW_EXTERNAL_CONFIDENTIAL_AI=false`).
- Tarixiy AI yozuvlari eksportida NHH kategoriyasi va rasmiy raqami DB’dan backfill qilinadi.
- Browser UAT topgan PDF oylik jadval savoli lokal deterministic ekstraksiyaga o‘tkazildi.
- So‘ralgan aniq modda mavjud bo‘lmasa, boshqa semantik yaqin modda qaytarilishi bloklandi.

## Test natijalari

- Backend: `52 passed in 60.66s`.
- Frontend: `3` test file, `9 passed`.
- Frontend production build: `267` modul, muvaffaqiyatli.
- Barcha 7 NHH kategoriya generik pipeline regressiyasi PASS.
- Maxfiy matn tashqi provider mockiga biror marta ham yetib bormasligi testi PASS.
- Incomplete/complete official export, formal huquqiy nom va external citation stripping testi PASS.

## Browser UAT

- Admin: foydalanuvchi yaratish, rol berish, faolsizlantirish/faollashtirish va o‘chirish; NHH metama’lumotini saqlash; barcha 7 kategoriya; tashkilot sozlamalarini persistence bilan saqlash tekshirildi.
- Rahbar: real dashboard, muammo, kechikkan task va muhim hujjatdan aynan DB recordiga navigation tekshirildi.
- Rahbar: xodimlar yuklamasi kartasi real assignee/task yozuvlaridan hisoblanishi (2 xodim, faol/bajarilgan/kechikkan/progress) browser orqali tekshirildi.
- Xodim: biriktirilgan task ochildi, `yangi → bajarildi` qilindi, Rahbar dashboarddan yo‘qolishi tasdiqlandi va UATdan so‘ng asl `yangi` holatiga qaytarildi.
- Document: mavjud real parserdan o‘tgan PDF/DOCX yozuvlarida PDF savol-javob (`Iyun = 49`), contradiction ikki alohida dalil bilan, response-letter draft va eksport tekshirildi.
- Legal: aniq savol 13-modda bilan; parafraza ayni 13-modda bilan; mavjud bo‘lmagan 99-modda esa manbasiz holat bilan qaytdi va boshqa modda uydirilmadi.

UAT vaqtida Rahbar va Xodimning vaqtinchalik parollari admin oqimi orqali yangilandi; bu xavfsizlik auditi va sessiya versiyasida qayd etilgan. Foydalanuvchi/task/document sonlari UAT tugagach asl operatsion miqdorda qoldi.

## DOCX render

`institutional-response-letter-draft.docx` va alohida `institutional-response-letter-evidence.docx` LibreOffice orqali PNGga render qilindi va har bir sahifa vizual tekshirildi. Tashqi qoralama: 1 sahifa, odatiy font, clipping/overlap yo‘q, formal Qonun nomi bor, ichki `[1]/[2]` yo‘q. Yuqoridagi ochiq marker: `QORALAMA — RASMIY REKVIZITLAR TO‘LDIRILMAGAN; YUBORISH MUMKIN EMAS`. Ichki dalillar: alohida 1 sahifa, citation mapping va rasmiy URL mavjud. Real profil bo‘shligi sabab qoralamada `[sana]`, `[Lavozim]`, `[F.I.Sh.]` ochiq qolishi talabga muvofiq; ayni holatda rasmiy eksport mavjud emas.

## Qolgan cheklovlar

- Qonundan boshqa Prezident farmoni, Prezident qarori, Vazirlar Mahkamasi qarori, Nizom, Buyruq va Idoraviy/ichki hujjatning tekshirilgan real nusxalari hali korpusga kiritilmagan.
- Vakolatli tashkilot real rekvizitlari, logo va imzolovchi kiritilmaguncha recipient-ready rasmiy xat chiqarilmaydi.
- Tashqi provider availability va free-tier limitlari servisga bog‘liq; grounded/extractive fallback saqlangan.
- Kengaytirilgan production deployment uchun TLS/reverse proxy, secret manager, backup/restore, monitoring/alerting va tashkilotning maxfiylik bo‘yicha yozma siyosati alohida operatsion mas’uliyat bo‘lib qoladi.
