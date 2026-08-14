# Raqobat AI Assistant — production-readiness yakuniy hisoboti

> **Superseded:** institutional polish’dan keyingi joriy va halol readiness holati
> `INSTITUTIONAL_PRODUCTION_POLISH_REPORT.md`da. Quyidagi hujjat oldingi auditning tarixiy
> snapshoti bo‘lib, undagi test sonlari, migration head va 2-sahifali eksport holati endi joriy emas.

**Tekshiruv sanasi:** 2026-08-13  
**Muhit:** lokal real PostgreSQL 16 + pgvector, FastAPI, React/Vite  
**Asos:** 6 sahifali texnik topshiriq va final UAT talablari

## 1. Topilgan ildiz muammolar

- Administrator sahifasi Rahbar dashboardiga o‘xshab qolgan, tizim boshqaruvi ikkilamchi edi.
- Dashboarddagi eski yozuvlar UI’da `[DEMO]`/`demo_` bilan ko‘rinardi va tasklar chuqur ochilmasdi.
- Topshiriqda to‘liq lifecycle, ustuvorlik, bog‘langan hujjat va tarix yo‘q edi.
- Oddiy AI chat texnik embedding/chunk/provider ma’lumotini ko‘rsatardi.
- Huquqiy deterministic javoblarning ayrim qismi ma’lum moddalarga ortiqcha bog‘langan edi.
- NHH metama’lumotlari va indexing holatlari yetarlicha boy emasdi.
- Rasmiy DOCX tashqi xat va ichki traceability qatlamini aniq ajratmasdi.
- Tashkilot rekvizitlari uchun konfiguratsiya yo‘q edi.

## 2. Arxitektura o‘zgarishlari

- Huquqiy pipeline generik `legal document → article/section → chunk → retrieval → evidence → grounded answer` oqimiga o‘tkazildi.
- PostgreSQL uchun ketma-ket `0005`–`0008` migratsiyalar qo‘shildi; production ma’lumotlari saqlangan holda kengaytirildi va eski ko‘rinadigan demo markerlar tozalandi.
- Task event, tashkilot profili, NHH processing holatlari, user last-login va operatsion `seed_key` modellari kiritildi.
- Oddiy readiness va Admin-only diagnostics endpointlari ajratildi.
- Groq uchun priority-ordered 5-model pool, per-model cooldown va shu so‘rov ichida failover ishlaydi.

## 3. Administrator

- Birlamchi landing endi `Administrator nazorat markazi`.
- Foydalanuvchi yaratish, qidirish/filterlash, rol almashtirish, faol/faol emas, parol reset, xavfsiz o‘chirish, oxirgi kirishni ko‘rish ishlaydi.
- Oxirgi administratorni o‘chirish/faolsizlantirish himoyasi backendda mavjud.
- NHH upload, metadata, faollik, safe delete, reindex, processing/index status, rasmiy URL va kategoriya boshqaruvi mavjud.
- Tashkilot rekvizitlari, tasdiqlangan PNG/JPEG logo va rasmiy DOCX shabloni Admin orqali boshqariladi.
- Provider, DB/indexing va processing failure texnikasi faqat diagnostikada ko‘rinadi.

## 4. Rahbar

- Rahbar uchun real analitik dashboard saqlandi va DB ma’lumotlariga ulandi.
- Muammo, kechikkan topshiriq, muhim murojaat va e’tibor talab qiladigan yozuvlar bosiladigan real recordlar.
- Task bosilganda aynan o‘sha task detali, document bosilganda aynan o‘sha hujjat ochiladi.
- Rahbar user/role administratsiyasiga kira olmaydi.

## 5. Xodim

- AI yordamchi, hujjatlar/tahlil, loyihalar, topshiriqlar va o‘z AI tarixi mavjud.
- Xodim faqat o‘ziga tegishli task statusini ruxsat doirasida o‘zgartiradi.
- Administrator endpointiga to‘g‘ridan-to‘g‘ri murojaat `403` qaytaradi.

## 6. NHH bazasi

- Birinchi darajali kategoriyalar: Qonun, Prezident farmoni, Prezident qarori, VM qarori, Nizom, Buyruq, Idoraviy/ichki hujjat.
- Metadata: nom, kategoriya, rasmiy raqam, qabul sanasi, rasmiy URL, source file, active, upload/index vaqt, extraction/index state va processing error.
- Faqat tasdiqlangan davlat hostidagi HTTPS manba qabul qilinadi; Lex.uz afzal.
- Real bazada hozir 1 ta tasdiqlangan faol NHH va 115 ta indekslangan NHH parchasi bor. Tekshirilmagan yangi NHH uydirib qo‘shilmadi.

## 7. AI/RAG

- Intent, Uzbek yozuv normalizatsiyasi, hybrid retrieval, topic filter, article-start preference, deduplication, stable ordering, evidence va citation validation ishlaydi.
- Article-specific `parse_article_13`/`render_article_13`, fixed `40`, `30000` yoki fixed-answer map production kodida yo‘q.
- Raqam, sana, NHH raqami, modda va citation faqat manba bilan tasdiqlansa chiqadi.
- Failing generation uchun foydalanuvchiga validator ichki matni emas, verified source-based fallback qaytadi.
- 5 model priority ro‘yxati: `openai/gpt-oss-120b`, `qwen/qwen3.6-27b`, `openai/gpt-oss-20b`, `groq/compound`, `groq/compound-mini`. `429`, timeout, model/format va upstream holatlarida keyingi modelga o‘tish testlangan.

## 8. Hujjat tahlili

- PDF, DOCX va XLSX real parser hamda index oqimi orqali ishlaydi.
- Qisqacha mazmun, asosiy bandlar, document QA va qarama-qarshiliklar mavjud.
- Arifmetik savollar deterministic hisoblanadi; yo‘q fakt uchun `Bu ma’lumot tanlangan hujjatda topilmadi.` qaytariladi.
- Qarama-qarshi ikki sana alohida verbatim dalil bilan ko‘rsatiladi va tizim ustuvor sanani uydirmaydi.

## 9. Rasmiy xat va DOCX

- A4, Arial, Word paragraph/list/headings, margins, spacing, hyperlink, footer page number va Uzbek metadata bilan haqiqiy DOCX yaratiladi.
- Tashqi birinchi sahifa normal rasmiy loyiha; `AI`, `RAG`, `LLM`, `validator`, `embedding` kabi texnik iboralar unda yo‘q.
- Ikkinchi sahifa aniq `ICHKI TEKSHIRUV VARAQASI` bo‘lib, yuboriladigan xat tarkibiga kirmasligi yozilgan; u manbalar va traceabilityni saqlaydi.
- Tashkilot logosi/emblemasi, nomi, manzil, aloqa, prefix va imzolovchi rekvizitlari konfiguratsiyadan olinadi; bo‘sh qiymatlar uydirilmaydi.
- Javob mazmunida da’vo isbotlangan fakt sifatida emas, shartli huquqiy baholash uslubida beriladi.

## 10. Topshiriq workflow

- Maydonlar: title, description, creator, assignee, status, priority, deadline, created/updated/completed, related document, event history.
- Statuslar: Yangi, Jarayonda, Bajarildi, Bekor qilindi.
- Overdue formulasi backendda: `deadline < now` va status completed/cancelled emas.
- Create/assign/open/update/complete/cancel ketma-ketligi va har o‘zgarish task event hamda auditga yoziladi.

## 11. Dashboard

- Jami hujjat, faol NHH, jami topshiriq va kechikkan sonlari real SQL querylardan olinadi.
- Ro‘yxatlar typed deep-link bilan task/documentga olib boradi.
- Browser UATda kechikkan task bosilib, aynan uning detali va tarixiga o‘tishi tekshirildi.

## 12. Xavfsizlik va RBAC

- Password hashing, token sessiya, backend role checks, confidential document owner/admin filter va RAG SQL permission filter saqlandi.
- API key faqat backend konfiguratsiyasida; frontend payload/statusda secret yo‘q.
- Direct API RBAC UATda Xodimning `/api/users` so‘rovi `403` qaytardi.
- Audit login, user/NHH/document/task/AI/export o‘zgarishlarini yozadi; prompt va secret diagnostika logiga chiqarilmaydi.

## 13. Anti-hardcode audit

- Production kod `parse_article_13`, `render_article_13`, `article == 13`, fixed `40 foiz`, `30000` va fixed test-query answer map bo‘yicha `rg` bilan tekshirildi: topilmadi.
- Oldindan noma’lum sintetik test qonunining 77-moddasi production kodini o‘zgartirmasdan upload/index/retrieve/cite qilindi.
- `[DEMO]` va `demo_` DB yozuvlari migratsiyada tozalandi; eski `demo-data/` binar nusxalari olib tashlandi, operatsion nusxalar `sample-data/`da saqlandi.
- Eski migratsiya tarixidagi `demo_key` nomi schema evolutionni qayta tiklash uchun qoladi; current schema `seed_key` ishlatadi. `seed_demo_data.py` esa eski avtomatlashtirishni buzmaslik uchun ichki compatibility modul sifatida saqlandi; foydalanuvchi hujjatlari va CLI entry point `seed_operational_data.py`dan foydalanadi.

## 14. 25 talab bo‘yicha matritsa

| # | Talab | Holat | Dalil |
|---:|---|---|---|
| 1 | AI chat | PASS | legal/general routing, cancel/retry va readiness UI |
| 2 | Manba hujjat nomi | PASS | source card va citation mapping |
| 3 | Modda/band | PASS | `article_or_clause`/display label |
| 4 | Rasmiy havola | PASS | verified official HTTPS URL va DOCX hyperlink |
| 5 | Foydalanilgan parcha | PASS | qisqa va expand qilinadigan to‘liq excerpt |
| 6 | PDF upload | PASS | parser/index acceptance testi |
| 7 | DOCX upload | PASS | parser/index acceptance testi |
| 8 | XLSX upload | PASS | parser/index acceptance testi |
| 9 | Qisqacha mazmun | PASS | document analysis endpoint/UI |
| 10 | Asosiy bandlar | PASS | document analysis endpoint/UI |
| 11 | Hujjat QA | PASS | exact, short, percentage va absent-fact testlari |
| 12 | Qarama-qarshilik | PASS | ikki alohida verbatim citation, no invented precedence |
| 13 | NHH bazasi | PASS | full metadata, category, CRUD/reindex/status |
| 14 | RAG | PASS | generic hybrid retrieval, stable evidence, grounding |
| 15 | Rasmiy javob xati | PASS | appeal + legal evidence + conditional drafting |
| 16 | Huquqiy asoslar | PASS | verified NHH-only source cards/internal sheet |
| 17 | DOCX eksport | PASS | real structured Word va successful render |
| 18 | Rahbar dashboard | PASS | real counters, record-backed clickable items |
| 19 | Administrator boshqaruvi | PASS | users/NHH/profile/diagnostics/roles/audit |
| 20 | Xodim workflow | PASS | assigned task, status update, own history |
| 21 | RBAC | PASS | menu + backend 403/direct API tests |
| 22 | Audit | PASS | real PostgreSQLda 1,496 audit yozuvi |
| 23 | Maxfiy hujjat | PASS | owner/admin access va RAG permission testlari |
| 24 | AI tarixi | PASS | user/time/mode/status/source/document va RBAC |
| 25 | Yagona integratsiyalashgan oqim | PASS | upload → index → analyze/chat → task/dashboard → draft/export |

## 15. Backend testlari

`pytest -q`: **49 passed** (`54.67s`). Legal exact/synonym/paraphrase/threshold/absent, document QA/arithmetic/contradiction, three-role RBAC, tasks, admin CRUD/logo, NHH, audit, drafting va Groq failover qamrab olingan.

## 16. Frontend testlari

`vitest`: **3 test file, 9 passed**. Production `tsc -b && vite build` ham muvaffaqiyatli; 267 modul build qilindi.

## 17. Browser UAT

- Rahbar dashboard real recordlar bilan ochildi.
- Kechikkan topshiriqdan detailga deep-link tekshirildi.
- Oddiy AI sahifada embedding/chunk/provider texnikasi yo‘qligi tekshirildi.
- Admin loginidan keyin primary Admin landing, 4 foydalanuvchi, qidiruv/rol/actionlar, last-login va diagnostics ko‘rildi.
- UI’da `[DEMO]`/`demo_` ko‘rinmadi.

## 18. PostgreSQL va migratsiya

- Docker `pgvector/pgvector:pg16` container holati: healthy.
- `alembic_version`: **0008 (head)**.
- Real joriy sonlar: 4 user, 5 document, 1 NHH, 115 NHH chunk, 10 task, 10 task event, 157 AI history, 1,496 audit log.

## 19. DOCX render

- `final-uat-response-letter.docx` real API history eksportidan yaratildi.
- LibreOffice render: 2 sahifa; clipping, overlap, broken glyph yoki raw Markdown topilmadi.
- 1-sahifa tashqi rasmiy loyiha, 2-sahifa ichki dalillar varaqasi.

## 20. Qolgan real cheklovlar

- Bazada hozir faqat tekshirilgan **1 ta** NHH bor. Qolgan kategoriya hujjatlari Admin import oqimi orqali haqiqiy rasmiy fayl va URL olingandan keyin qo‘shilishi kerak; hech biri uydirilmadi.
- Tashkilot profili real rekvizitlar bilan to‘ldirilmagani sabab UAT DOCXda ataylab ochiq placeholderlar bor. Vakolatli foydalanuvchi haqiqiy nom, manzil, chiqish prefixi va imzolovchini kiritishi kerak.
- Live huquqiy Groq chaqiruvi bu UATda bajarilmadi: u NHH parchalarini tashqi provayderga uzatadi va alohida maxfiylik roziligi berilmadi. Lokal source-driven pipeline hamda Groq failover/error mapping test doubles bilan to‘liq testlandi.
- Real bazada hozir maxfiy deb belgilangan document soni 0; maxfiylik va permission-filter oqimi izolatsiyalangan acceptance testida PASS.

## Joriy real ma’lumotlar

| Ko‘rsatkich | Soni |
|---|---:|
| Administrator | 1 |
| Rahbar | 1 |
| Xodim | 2 |
| Hujjat | 5 |
| Faol NHH | 1 |
| Indekslangan NHH parchasi | 115 |
| Topshiriq — Yangi | 4 |
| Topshiriq — Jarayonda | 3 |
| Topshiriq — Bajarildi | 3 |
| Topshiriq — Bekor qilindi | 0 |
| Kechikkan | 2 |
