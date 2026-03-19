# 📦 Полная структура МебельГрад КИС

## 🌳 Дерево файлов

```
mebelgrad_kis/
│
├── 📄 run.py                              # Точка входа приложения
├── 📄 config.py                           # Конфигурация (dev/test/prod)
├── 📄 requirements.txt                    # Зависимости Python
├── 📄 .env.example                        # Пример конфигурации
├── 📄 .gitignore                          # Git правила исключения
│
├── 📚 README.md                           # Полная документация
├── 📚 QUICKSTART.md                       # Быстрый старт
├── 📚 PROJECT_SUMMARY.md                  # Итоговый отчет
├── 📚 STRUCTURE.md                        # Этот файл
│
├── 📁 app/                                # Flask приложение
│   ├── 📄 __init__.py                     # Инициализация (350 строк)
│   ├── 📄 models.py                       # БД модели (320 строк)
│   │
│   ├── 📁 auth/                           # 🔐 Модуль аутентификации
│   │   ├── 📄 __init__.py
│   │   └── 📄 routes.py                   # 2 маршрута (login/logout)
│   │
│   ├── 📁 data_mdm/                       # 📋 Управление данными
│   │   ├── 📄 __init__.py
│   │   └── 📄 routes.py                   # 20+ маршрутов
│   │                                      # - Товары (CRUD)
│   │                                      # - Клиенты (CRUD)
│   │                                      # - Поставщики (CRUD)
│   │                                      # - Сотрудники (CRUD)
│   │                                      # - Остатки (R)
│   │
│   ├── 📁 finance/                        # 💰 Финансы
│   │   ├── 📄 __init__.py
│   │   └── 📄 routes.py                   # 12+ маршрутов
│   │                                      # - Входящие платежи
│   │                                      # - Исходящие платежи
│   │                                      # - Бюджет
│   │                                      # - План-факт анализ
│   │                                      # - Отчетность
│   │                                      # - Экспорт 1С
│   │
│   ├── 📁 sales_demo/                     # 🛍️ Демо: Продажи
│   │   ├── 📄 __init__.py
│   │   └── 📄 routes.py
│   │
│   └── 📁 warehouse_demo/                 # 📦 Демо: Склад
│       ├── 📄 __init__.py
│       └── 📄 routes.py
│
├── 📁 templates/                          # HTML шаблоны (Jinja2)
│   ├── 📄 base.html                       # Базовый шаблон
│   ├── 📄 index.html                      # Главная страница
│   ├── 📄 404.html                        # Ошибка 404
│   ├── 📄 403.html                        # Ошибка 403
│   │
│   ├── 📁 auth/
│   │   └── 📄 login.html                  # Форма входа
│   │
│   ├── 📁 data_mdm/
│   │   ├── 📄 index.html                  # Панель MDM
│   │   ├── 📁 products/
│   │   │   ├── 📄 list.html               # Список товаров
│   │   │   ├── 📄 create.html             # Создание товара
│   │   │   └── 📄 edit.html               # Редактирование товара
│   │   ├── 📁 customers/
│   │   │   ├── 📄 list.html               # Список клиентов
│   │   │   ├── 📄 create.html             # Создание клиента
│   │   │   └── 📄 edit.html               # Редактирование клиента
│   │   ├── 📁 suppliers/
│   │   │   ├── 📄 list.html               # Список поставщиков
│   │   │   ├── 📄 create.html             # Создание поставщика
│   │   │   └── 📄 edit.html               # Редактирование поставщика
│   │   ├── 📁 employees/
│   │   │   ├── 📄 list.html               # Список сотрудников
│   │   │   ├── 📄 create.html             # Создание сотрудника
│   │   │   └── 📄 edit.html               # Редактирование сотрудника
│   │   └── 📁 stock/
│   │       └── 📄 list.html               # Просмотр остатков
│   │
│   ├── 📁 finance/
│   │   ├── 📄 index.html                  # Панель финансов
│   │   ├── 📄 plan_fact.html              # План-факт анализ
│   │   ├── 📄 profitability.html          # Отчет о прибыли
│   │   ├── 📁 payments/
│   │   │   ├── 📄 incoming.html           # Входящие платежи
│   │   │   └── 📄 outgoing.html           # Исходящие платежи
│   │   └── 📁 budget/
│   │       ├── 📄 index.html              # Бюджет
│   │       └── 📄 add.html                # Добавление статьи
│   │
│   └── 📁 demo/
│       ├── 📄 sales_demo.html             # Демо продаж
│       └── 📄 warehouse_demo.html         # Демо склада
│
├── 📁 static/                             # Статические файлы
│   ├── 📁 css/                            # (если будут локальные стили)
│   └── 📁 js/                             # (если будет локальный JS)
│
└── 📁 instance/                           # Flask instance (генерируется)
    └── флаг.db                            # БД (если SQLite)
```

---

## 📊 Статистика файлов

### Python код
```
app/__init__.py              ~350 строк
app/models.py               ~320 строк
app/auth/routes.py          ~50 строк
app/data_mdm/routes.py      ~300 строк
app/finance/routes.py       ~400 строк
app/sales_demo/routes.py    ~10 строк
app/warehouse_demo/routes.py ~10 строк
config.py                   ~40 строк
run.py                      ~15 строк
────────────────────────────────────────
Всего Python:              ~1495 строк
```

### HTML шаблоны
```
base.html                   ~120 строк
index.html                  ~80 строк
Шаблоны аутентификации     ~30 строк
Шаблоны MDM                ~600 строк
Шаблоны финансов           ~500 строк
Шаблоны демо               ~100 строк
────────────────────────────────────────
Всего HTML:               ~1430 строк
```

### Документация
```
README.md                   ~500 строк
QUICKSTART.md              ~150 строк
PROJECT_SUMMARY.md         ~450 строк
STRUCTURE.md               этот файл
────────────────────────────────────────
Всего документации:        ~1100 строк
```

---

## 🗄️ База данных

### Таблицы (12 шт)

```
1. users                    - Пользователи системы
2. products                 - Справочник товаров
3. customers                - Клиенты
4. suppliers                - Поставщики
5. employees                - Сотрудники
6. stock                    - Складские остатки
7. sales_orders             - Заказы клиентов
8. sales_order_items        - Позиции заказов клиентов
9. payments                 - Платежи от клиентов
10. purchase_orders         - Заказы поставщикам
11. purchase_order_items    - Позиции заказов поставщикам
12. budget_items            - Статьи бюджета
```

### Связи между таблицами

```
users
  ├─ N:1 ← (по ролям)
  
customers
  ├─ 1:N → sales_orders
  
suppliers
  ├─ 1:N → purchase_orders
  
products
  ├─ 1:1 → stock
  ├─ 1:N → sales_order_items
  └─ 1:N → purchase_order_items
  
sales_orders
  ├─ N:1 ← customers
  ├─ 1:N → sales_order_items
  └─ 1:N → payments
  
sales_order_items
  ├─ N:1 ← sales_orders
  └─ N:1 ← products
  
purchase_orders
  ├─ N:1 ← suppliers
  └─ 1:N → purchase_order_items
  
purchase_order_items
  ├─ N:1 ← purchase_orders
  └─ N:1 ← products
  
payments
  └─ N:1 ← sales_orders
  
budget_items
  └─ Независимая таблица (период + категория)
```

---

## 🔐 Маршруты и эндпоинты

### Аутентификация (4 маршрута)
```
GET  /                      - Главная страница
GET  /auth/login            - Форма входа
POST /auth/login            - Обработка входа
GET  /auth/logout           - Выход
```

### MDM (25+ маршрутов)
```
GET    /mdm/                         - Панель MDM
GET    /mdm/products                 - Список товаров
POST   /mdm/products/create          - Создание товара
GET    /mdm/products/<id>/edit       - Форма редактирования
POST   /mdm/products/<id>/edit       - Сохранение товара
POST   /mdm/products/<id>/delete     - Удаление товара
GET    /mdm/customers                - Список клиентов
POST   /mdm/customers/create         - Создание клиента
GET    /mdm/customers/<id>/edit      - Редактирование клиента
POST   /mdm/customers/<id>/delete    - Удаление клиента
GET    /mdm/suppliers                - Список поставщиков
POST   /mdm/suppliers/create         - Создание поставщика
GET    /mdm/suppliers/<id>/edit      - Редактирование поставщика
POST   /mdm/suppliers/<id>/delete    - Удаление поставщика
GET    /mdm/employees                - Список сотрудников
POST   /mdm/employees/create         - Создание сотрудника
GET    /mdm/employees/<id>/edit      - Редактирование сотрудника
POST   /mdm/employees/<id>/delete    - Удаление сотрудника
GET    /mdm/stock                    - Просмотр остатков
```

### Финансы (12+ маршрутов)
```
GET    /finance/                        - Финансовый центр
GET    /finance/incoming-payments       - Входящие платежи
GET    /finance/outgoing-payments       - Исходящие платежи
POST   /finance/outgoing-payments/<id>/mark-paid  - Отметить как оплачено
GET    /finance/budget                  - Бюджет
GET    /finance/budget/add              - Добавление статьи
POST   /finance/budget/add              - Сохранение статьи
GET    /finance/plan-fact-analysis      - План-факт анализ
GET    /finance/profitability-report    - Отчет о прибыли
POST   /finance/export-1c               - Экспорт в JSON
```

### Демо (2 маршрута)
```
GET    /sales/                  - Демо продаж
GET    /warehouse/              - Демо склада
```

---

## 🎨 Функции и декораторы

### Декораторы
```
@route()                    - Flask маршруты
@login_required             - Проверка аутентификации
@admin_required             - Проверка роли администратора
@finance_required           - Проверка роли бухгалтера
```

### Основные функции

**auth/routes.py:**
- `login()` - Аутентификация пользователя
- `logout()` - Выход из системы

**data_mdm/routes.py:**
- `products_list()` - Список товаров
- `create_product()` - Создание товара
- `edit_product()` - Редактирование товара
- `delete_product()` - Удаление товара
- `customers_list()` - Список клиентов
- `create_customer()` - Создание клиента
- `edit_customer()` - Редактирование клиента
- `delete_customer()` - Удаление клиента
- `suppliers_list()` - Список поставщиков
- И т.д. (аналогичные для остальных)

**finance/routes.py:**
- `incoming_payments()` - Просмотр входящих платежей
- `outgoing_payments()` - Управление исходящими платежами
- `mark_purchase_order_paid()` - Отметить как оплачено
- `budget()` - Просмотр бюджета
- `add_budget_item()` - Добавление статьи
- `plan_fact_analysis()` - План-фактный анализ
- `profitability_report()` - Отчет о прибыли
- `export_1c()` - Экспорт в 1С

---

## 📋 Тестовые данные

**Автоматически создаются при первом запуске:**

```
Users (2):
├─ admin/admin123           (is_admin=True)
└─ finance/finance123        (is_finance=True)

Products (3):
├─ STOL-001: Стол деревянный   (5500 руб, 10 шт)
├─ STUL-002: Стул мягкий       (2200 руб, 25 шт)
└─ SHKAFF-003: Шкаф книжный    (8800 руб, 5 шт)

Customers (2):
├─ ООО СтройКорп             (юр. лицо)
└─ Иван Петров              (физ. лицо)

Suppliers (2):
├─ ООО МебельИмпорт
└─ АО ДеревоПродукт

Employees (2):
├─ Александр Сидоров       (Администратор)
└─ Мария Кузнецова         (Бухгалтер)

Orders & Payments (4):
├─ PO-2024-001             (заказ поставщику)
├─ SO-2024-001             (заказ клиента)
├─ 1 платеж                (13700 руб)
└─ 3 статьи бюджета        (на текущий месяц)
```

---

## 🚀 Развертывание

### Требования
```
Python 3.10+
PostgreSQL 14+
pip
```

### Шаги установки
```
1. git clone / распаковка проекта
2. python -m venv venv
3. source venv/bin/activate
4. pip install -r requirements.txt
5. Создать .env файл
6. python run.py
```

### Доступ
```
URL: http://localhost:5000
Администратор: admin / admin123
Бухгалтер: finance / finance123
```

---

## 📚 Документация

| Файл | Описание |
|------|---------|
| README.md | Полная документация системы |
| QUICKSTART.md | Быстрый старт за 5 минут |
| PROJECT_SUMMARY.md | Итоговый отчет о проекте |
| STRUCTURE.md | Структура файлов (этот файл) |

---

## ✅ Чеклист для новичков

### Перед запуском
- [ ] Установить Python 3.10+
- [ ] Установить PostgreSQL
- [ ] Клонировать/распаковать проект
- [ ] Создать virtual environment
- [ ] Установить зависимости

### Конфигурация
- [ ] Создать БД `mebelgrad_kis`
- [ ] Копировать `.env.example` → `.env`
- [ ] Отредактировать DATABASE_URL
- [ ] Отредактировать SECRET_KEY

### Первый запуск
- [ ] `python run.py`
- [ ] Открыть `http://localhost:5000`
- [ ] Вход через admin/admin123
- [ ] Проверить MDM модуль
- [ ] Проверить финансовый модуль

### Тестирование
- [ ] Добавить товар
- [ ] Создать клиента
- [ ] Просмотреть платежи
- [ ] Проверить отчеты
- [ ] Экспортировать в 1С

---

**Версия:** 1.0  
**Дата:** 2024-01-01  
**Статус:** ✅ Актуально
