# Schema Integration Testing Guide

## Architecture Overview

The schema integration connects MDM (Master Data Management) with other modules through a dynamic schema system. Changes in MDM automatically propagate to all dependent modules without code changes.

```
┌─────────────────────────────────────────────────────────┐
│  MDM Module (Single Source of Truth)                   │
│  ├─ DataModel table (customers, products, etc.)        │
│  └─ DataModelField table (field definitions)           │
└────────────────┬──────────────────────────────────────┘
                 │
         ┌───────┴──────────┐
         │                  │
         ▼                  ▼
    ┌─────────────┐    ┌──────────────┐
    │  API Layer  │    │ Util Layer   │
    │ /api/schema │    │schema_utils  │
    │   endpoints │    │  functions   │
    └─────────────┘    └──────────────┘
         │                  │
         │ HTTP fetch       │ Direct import
         │                  │
         └──────────┬───────┘
                    │
         ┌──────────┴──────────┐
         │                     │
    ┌────▼─────────┐   ┌──────▼──────────┐
    │ Sales Module │   │ Warehouse/      │
    │ (Integrated) │   │ Finance Modules │
    │              │   │ (To integrate)  │
    └──────────────┘   └─────────────────┘
```

## Test Scenarios

### Scenario 1: API Endpoint Returns Current Schema

**What to test:** The MDM API returns schema with all current field definitions

**Steps:**
1. Start the Flask app: `python run.py`
2. Open browser and navigate to: http://localhost:5000/mdm/api/schema/customers
3. Verify response JSON includes:
   - `entity_key`: "customers"
   - `label`: "Клиенты"
   - `fields`: array with all customer fields

**Expected Result:**
```json
{
  "entity_key": "customers",
  "label": "Клиенты",
  "description": "Справочник клиентов",
  "fields": [
    {
      "name": "name",
      "label": "ФИО / наименование",
      "type": "string",
      "required": true,
      "visible": true,
      "max_length": 255,
      "help_text": "Полное имя или наименование",
      "order": 10
    },
    {
      "name": "phone",
      "label": "Телефон",
      "type": "string",
      "required": false,
      "visible": true,
      "max_length": 20,
      "help_text": "Контактный номер",
      "order": 20
    },
    // ... more fields
  ]
}
```

✅ **Pass Criteria:** JSON response contains all expected fields with correct metadata

---

### Scenario 2: Sales Customer Creation Uses Dynamic Fields

**What to test:** Creating a customer uses fields from the schema, not hardcoded values

**Setup:**
1. Make sure app is running
2. Open the Sales Demo module
3. Try to create a new sales order with a new customer

**Steps (via API):**
```bash
curl -X POST http://localhost:5000/sales/api/customers \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your_session_cookie>" \
  -d {
    "name": "Иван Петров",
    "phone": "+7-999-123-4567",
    "email": "ivan@example.com",
    "customer_inn": "1234567890",
    "type": "individual",
    "is_active": true
  }
```

**Expected Result:** 
- HTTP 200 response
- JSON includes all visible schema fields:
  ```json
  {
    "id": 123,
    "name": "Иван Петров",
    "phone": "+7-999-123-4567",
    "email": "ivan@example.com",
    "customer_inn": "1234567890",
    // ... all other visible fields
  }
  ```

✅ **Pass Criteria:** Response includes all schema-visible fields, not just hardcoded ones

---

### Scenario 3: Schema Change Propagates to Sales

**What to test:** When MDM schema changes, sales module automatically uses new definition

**Steps:**

**Part A: Add a new field to customer schema**
1. Go to MDM: http://localhost:5000/mdm/
2. Click "Клиенты" → "Схема данных"
3. Click "Добавить поле" button
4. Create field:
   - Technical Name: "website"
   - Display Name (Label): "Веб-сайт"
   - Type: string
   - Required: No
   - Visible: Yes
   - Max Length: 255
5. Save

**Part B: Verify API includes new field**
1. Fetch schema: http://localhost:5000/mdm/api/schema/customers
2. Verify response includes "website" field

**Part C: Create customer with new field**
```bash
curl -X POST http://localhost:5000/sales/api/customers \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your_session_cookie>" \
  -d {
    "name": "Website Test Company",
    "website": "https://example.com",
    "phone": "+7-999-999-9999"
  }
```

**Part D: Verify new field in response**
- Response includes: `"website": "https://example.com"`
- Query database: `SELECT website FROM customer WHERE id = <new_id>` shows value

✅ **Pass Criteria:** New schema field immediately available in sales without code changes

---

### Scenario 4: Remove Field from Schema

**What to test:** Removing visibility of a field prevents it from being used

**Steps:**

**Part A: Hide a field**
1. Go to MDM: Клиенты → Схема данных
2. Find "registration_address" field
3. Click Edit
4. Uncheck "Visible" checkbox
5. Save

**Part B: Verify API doesn't include hidden field**
```bash
curl http://localhost:5000/mdm/api/schema/customers
curl http://localhost:5000/mdm/api/schema/customers/visible
```
- First endpoint should have field but might include visibility flag = false
- Second endpoint should not include the field at all

**Part C: Create customer without hidden field**
```bash
curl -X POST http://localhost:5000/sales/api/customers \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your_session_cookie>" \
  -d {
    "name": "Test Customer",
    "phone": "+7-999-999-9999",
    "registration_address": "This should be ignored"
  }
```

**Part D: Verify field not in response**
- Response should not include "registration_address"

✅ **Pass Criteria:** Hidden fields are not included in sales operations

---

### Scenario 5: Type Validation Works

**What to test:** Field type definitions are enforced during creation

**Setup:** Ensure schema has:
- "birth_date" field: type = "date"
- "customer_inn" field: type = "string"

**Test Case 5A: Invalid date format**
```bash
curl -X POST http://localhost:5000/sales/api/customers \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your_session_cookie>" \
  -d {
    "name": "Date Test",
    "birth_date": "invalid-date"
  }
```
**Expected:** Either converts to null or rejects gracefully

**Test Case 5B: Required field missing**
```bash
curl -X POST http://localhost:5000/sales/api/customers \
  -H "Content-Type: application/json" \
  -H "Cookie: session=<your_session_cookie>" \
  -d {
    "phone": "+7-999-999-9999"
  }
```
**Expected:** HTTP 400 error: "name обязательно" (name is required)

✅ **Pass Criteria:** Type conversion and validation work according to schema

---

### Scenario 6: Search Results Use Dynamic Fields

**What to test:** Customer search returns all visible schema fields

**Steps:**

1. Create a customer with multiple fields filled
2. Search for customer:
```bash
curl "http://localhost:5000/sales/api/customers?q=Петров" \
  -H "Cookie: session=<your_session_cookie>"
```

**Expected Result:**
```json
[
  {
    "id": 123,
    "name": "Иван Петров",
    "phone": "+7-999-123-4567",
    "email": "ivan@example.com",
    // ... all other visible schema fields
  }
]
```

✅ **Pass Criteria:** Response includes all visible schema fields, not just hardcoded ones

---

## Testing Workflow

### Quick Integration Test (5 minutes)
1. ✅ Start app
2. ✅ Fetch schema: `/mdm/api/schema/customers`
3. ✅ Create customer with all visible fields
4. ✅ Verify response includes all fields

### Full Integration Test (15 minutes)
1. ✅ Run Quick Integration Test
2. ✅ Add new field to customer schema
3. ✅ Verify API includes new field
4. ✅ Create customer with new field
5. ✅ Verify response includes new field
6. ✅ Hide a field in schema
7. ✅ Verify API doesn't include hidden field

### Comprehensive Test (30 minutes)
1. ✅ Run Full Integration Test
2. ✅ Test required field validation
3. ✅ Test type conversion (date, integer, etc.)
4. ✅ Test customer search with dynamic fields
5. ✅ Verify database integrity

## Debugging Tips

### Schema not appearing in API
1. Check MDM database has DataModel entry: 
   ```python
   from app.models import DataModel
   DataModel.query.filter_by(key='customers').first()
   ```

2. Check fields are associated:
   ```python
   model = DataModel.query.filter_by(key='customers').first()
   print(model.fields.all())
   ```

### Sales not using dynamic fields
1. Check import: `from app.schema_utils import get_visible_fields`
2. Check function returns fields: 
   ```python
   from app.schema_utils import get_visible_fields
   fields = get_visible_fields('customers')
   print([f.name for f in fields])
   ```

### Type conversion issues
1. Check field data_type: 
   ```python
   field = get_field_by_name('customers', 'birth_date')
   print(field.data_type)
   ```

2. Verify Customer model has attribute:
   ```python
   from app.models import Customer
   print(hasattr(Customer, 'birth_date'))
   ```

## Next Steps

### For Warehouse Module
1. Import schema_utils in warehouse_demo/routes.py
2. Update Product API endpoints to use get_visible_fields('products')
3. Follow same pattern as sales integration

### For Finance Module  
1. Import schema_utils in finance/routes.py
2. Update payment/invoice endpoints to use schema
3. Ensure all entities (Product, Customer, Supplier) use dynamic fields

### For Frontend Enhancement
1. Fetch schema on form load: `fetch('/mdm/api/schema/customers')`
2. Generate form fields dynamically using template macros
3. Validate on client-side using field definitions

---

## Success Criteria

✅ Schema API endpoints return current definitions
✅ Sales customer creation uses dynamic fields from schema
✅ Adding schema field immediately makes it available in sales
✅ Removing schema field immediately stops using it in sales
✅ Type validation works according to field definitions
✅ Search results include all visible schema fields
✅ No hardcoded field lists in sales_demo/routes.py
✅ All changes are instant without app restart
