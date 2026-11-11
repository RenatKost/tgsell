# Блог TgSell (`/blog`)

## Як це працює
- Статті — markdown-файли `content/blog/<slug>.md` (UTF-8) із frontmatter.
- FastAPI (`backend/app/routers/blog.py`) віддає повний HTML поверх Vite `index.html`: `/blog` (список) і `/blog/<slug>` (стаття). Текст статті є у відповіді без JS; React потім показує ті самі дані (JSON bootstrap + `GET /api/blog`, `GET /api/blog/<slug>`).
- Draft, невідомий/невалідний slug, вкладені шляхи — справжній HTTP 404 з `noindex`. `/blog/` і `/blog/<slug>/` → 308 на канонічний шлях.
- SEO: title, description, canonical `https://tgsell.me/blog[/slug]`, OpenGraph (`og:type` article для статті), JSON-LD `Article` (без вигаданого автора/dateModified). Опубліковані статті потрапляють у `sitemap.xml` з `lastmod` = `date`.
- Markdown рендериться на сервері: raw HTML вимкнено, зображення вимкнено, посилання лише http(s), локальні `/…` і `#…`; зовнішні — `rel="noopener noreferrer"`.
- `Dockerfile.railway` копіює `content/blog/` у `/app/content/blog`. Змінні Railway не потрібні.

## Frontmatter (усі поля обов’язкові, інших полів не можна)
```yaml
---
title: "Заголовок"          # ≤ 200 символів, plain text
description: "Опис"         # ≤ 500 символів
slug: yak-prodaty-telegram-kanal  # [a-z0-9-], ≤ 120, = ім’я файла
lang: uk
status: draft               # draft | published
date: 2026-11-08            # YYYY-MM-DD, редакційна дата публікації
---

# Заголовок                 # рівно один h1, перший блок, = title
```

## Публікація
- Нова стаття додається як `status: draft` (на сайті не видно, URL дає 404).
- Публікація — лише за рішенням CEO: змінити `status` на `published`.
- Посилання `https://tgsell.me/blog/<slug>` у published статті мають вести на published статтю; інакше тест `test_real_content_valid_and_published_together` падає (взаємопов’язані статті публікуються разом).
- Службові файли (README.md, QA.md, sources.md, topics.md) у `content/blog` не кладемо.
- Без внутрішньої методології (кількість лотів, джерела даних, періоди, курси).
