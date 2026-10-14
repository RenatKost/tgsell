# CatFee: аренда энергии для выплат escrow — инструкция

Зачем: перевод USDT с escrow стоит 65–131k энергии. Без энергии сеть сжигает ~7–17 TRX за выплату
(платит master-кошелёк). Аренда на 1 час у CatFee стоит ~1.2 TRX (65k) / ~2.3 TRX (131k).
Без ключей всё работает как раньше (сжигание TRX). При любой ошибке CatFee (нет баланса, сбой API,
таймаут) выплата автоматически идёт по старой схеме — деньги не зависают.

## 1. Регистрация
1. Откройте https://catfee.io → Sign up (email или Telegram). Включите 2FA (User Center → Security).
2. Тестовая сеть (по желанию): отдельный аккаунт на https://nile.catfee.io, тестовые TRX —
   https://nileex.io/join/getJoinPage. Ключи mainnet и Nile НЕ взаимозаменяемы.

## 2. API-ключ
1. catfee.io → User Center → API → API Settings.
2. Скопируйте **API Key** и **API Secret** (Secret никому не пересылайте, не кладите в чат/код).
3. IP Whitelist: можно оставить пустым (у Railway нет фиксированного исходящего IP без
   статического egress). Если включите Static Outbound IP в Railway — впишите его сюда.

## 3. Пополнение баланса
1. User Center → Recharge: личный адрес для пополнения (TRX). Переведите TRX с биржи/кошелька.
2. Сколько: одна выплата ≈ 1.2–2.5 TRX. Рекомендуем **50 TRX** (~20–40 выплат);
   минимум для старта — 15–20 TRX.
3. Когда баланса хватает меньше чем на ~5 выплат, бот пришлёт админу алерт «🐱 Мало коштів на CatFee»;
   баланс виден в админке: Гроші → карточка «⛽ Газ master-гаманця» → строка CatFee.

## 4. Railway Variables (проект tgsell → сервис tgsell → Variables)
| Переменная | Значение |
|---|---|
| `CATFEE_API_KEY` | API Key из шага 2 |
| `CATFEE_API_SECRET` | API Secret из шага 2 |
| `CATFEE_BASE_URL` | не задавать (mainnet → https://api.catfee.io автоматически) |

После сохранения Railway перезапустит сервис. Проверка: в админке строка CatFee показывает баланс;
в логах выплаты `[CATFEE] order …` и `energy_source=catfee`.

## 5. Master-кошелёк
TRX на master по-прежнему нужен: ~1.2 TRX на активацию/bandwidth escrow за выплату
(остаток возвращается sweep) и как резерв на случай отката к сжиганию. Держите ≥ 30 TRX.

## 6. Отключить
Удалите `CATFEE_API_KEY` (или `CATFEE_API_SECRET`) в Railway Variables — вернётся схема сжигания TRX.

## 7. Тест на Nile (необязательно)
```
cd backend
CATFEE_API_KEY=<nile key> CATFEE_API_SECRET=<nile secret> python scripts/catfee_nile_check.py
CATFEE_API_KEY=... CATFEE_API_SECRET=... python scripts/catfee_nile_check.py --order <активированный Nile-адрес>
```
Скрипт жёстко работает только с nile.catfee.io / nile.trongrid.io.
