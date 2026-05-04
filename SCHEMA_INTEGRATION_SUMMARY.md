# Integration of MDM Schema with Sales Module - Summary

## Changes Made

### 1. **New File: `app/schema_utils.py`**
Core utility module providing functions for accessing and using MDM schema definitions:
- `get_schema_fields(entity_key)` - Retrieve all fields for an entity, ordered by display order
- `get_schema_model(entity_key)` - Get the DataModel object
- `get_visible_fields(entity_key)` - Get only visible fields (for forms)
- `get_required_fields(entity_key)` - Get required fields (for validation)
- `get_field_by_name(entity_key, field_name)` - Get a specific field
- `get_form_fields_as_dict(entity_key)` - Convert to dictionary for template rendering
- `validate_field_value(entity_key, field_name, value)` - Validate individual field values
- `extract_fields_from_form(entity_key, form_data)` - Filter form data to schema-defined fields
- `get_field_html_input_type(data_type)` - Map schema types to HTML input types

**Purpose:** Centralized access point for all modules to interact with MDM schema. Any changes to schema automatically affect all modules using these functions.

### 2. **New File: `templates/components/schema_form.html`**
Reusable form template for dynamic form rendering based on DataModel schema:
- Supports all field types: string, text, integer, float, date, boolean
- Generates appropriate HTML input elements based on field type
- Includes validation attributes (required, maxlength)
- Shows field labels, help text, and required indicators
- Responsive Bootstrap layout

**Usage:** Other modules include this template with context variables: `entity_key`, `fields`, `entity`, `form_action`

### 3. **Updated: `app/data_mdm/routes.py`**
Added new API endpoints for schema retrieval:

#### `GET /mdm/api/schema/<entity_key>`
Returns complete schema definition as JSON:
```json
{
    "entity_key": "customers",
    "label": "Клиенты",
    "description": "...",
    "fields": [
        {
            "name": "name",
            "label": "ФИО / наименование",
            "type": "string",
            "required": true,
            "visible": true,
            "max_length": 255,
            "help_text": "...",
            "order": 10
        },
        ...
    ]
}
```

#### `GET /mdm/api/schema/<entity_key>/visible`
Returns only visible fields (for form rendering):
```json
{
    "entity_key": "customers",
    "fields": [...]
}
```

**Purpose:** Allows other modules to fetch current schema definitions dynamically. Changes in MDM schema are immediately reflected in API responses.

### 4. **Updated: `app/sales_demo/routes.py`**
Integrated schema-based customer operations:

#### Import Addition
```python
from app.schema_utils import get_visible_fields, get_field_by_name
```

#### `POST /api/customers` - Create Customer
- Now reads from MDM schema instead of hardcoding fields
- Dynamically extracts fields based on `get_visible_fields('customers')`
- Performs type conversion (boolean, date, integer, float) based on field definition
- Validates required fields from schema
- Returns response with only schema-defined fields
- **Key Benefit:** Adding/removing customer fields in MDM automatically affects sales customer creation

#### `GET /api/customers` - Search Customers
- Searches by name (as before)
- Returns response with all visible schema fields instead of hardcoded fields
- **Key Benefit:** Adding new fields to MDM schema automatically includes them in search results

### 5. **Updated: `templates/data_mdm/index.html`**
Added hint about schema management to emphasize it as the central control point:
```
💡 Tip: Управляйте структурой данных через Схема данных — все изменения автоматически распространяются на формы в других модулях.
```

## How It Works: Dynamic Form System

### Problem Solved
When MDM schema changed (e.g., add "middle_name" field to customers), sales forms didn't update because they used hardcoded Customer model fields.

### Solution Architecture

1. **Schema Definition Layer**
   - MDM defines all fields via `DataModel` and `DataModelField` tables
   - Fields include metadata: name, label, type, required, visible, max_length, order

2. **Utility Layer**
   - `schema_utils.py` provides single interface for accessing schema
   - Any module can call `get_visible_fields('customers')` to get current field definitions

3. **API Layer**
   - MDM exposes `/api/schema/<entity_key>` endpoints
   - Other modules can fetch schema via HTTP if needed

4. **Form Generation**
   - Templates include reusable `schema_form.html`
   - Dynamically renders inputs based on field definitions
   - Type-aware (date pickers for dates, number inputs for numbers, etc.)

5. **Business Logic Layer**
   - Sales `create_customer()` extracts only schema-defined fields
   - Performs type conversion based on field definition
   - Validates required fields before database insert

### Data Flow Example: Adding a "middle_name" Field to Customers

1. **Admin edits schema in MDM**
   - Adds field: name="middle_name", label="Отчество", type="string", order=15

2. **Field immediately available to sales**
   - `get_visible_fields('customers')` includes the new field
   - Validation knows it's a string field
   - Type conversion handles it correctly

3. **Sales customer creation uses it**
   - `create_customer()` extracts "middle_name" from payload
   - Sets it on Customer model if the model has that attribute
   - Returns it in response

4. **Search returns it**
   - `search_customers()` includes "middle_name" in JSON response

## Testing the Integration

### Test 1: Create Customer with Schema-Defined Fields
```bash
curl -X POST http://localhost:5000/sales/api/customers \
  -H "Content-Type: application/json" \
  -d {
    "name": "Иван Петров",
    "phone": "+7-999-123-4567",
    "email": "ivan@example.com",
    "customer_inn": "1234567890"
  }
```
Expected: Returns customer with all visible schema fields

### Test 2: Fetch Current Schema
```bash
curl http://localhost:5000/mdm/api/schema/customers
```
Expected: Returns JSON with all customer fields as defined in MDM

### Test 3: Add Field to MDM
1. Go to MDM > Клиенты > Схема данных
2. Add new field (e.g., "website", type: string)
3. Sales customer creation now accepts "website" field

### Test 4: Remove Field from MDM
1. Go to MDM > Клиенты > Схема данных
2. Delete a field or set is_visible=false
3. Sales customer creation no longer uses it

## Next Steps for Warehouse and Finance Modules

To extend this to warehouse and finance:

1. **warehouse_demo/routes.py:**
   - Import `schema_utils`
   - Update Product-related endpoints to use `get_visible_fields('products')`
   - Update endpoints that create/serialize warehouse entities

2. **finance/routes.py:**
   - Similar pattern for Product, Customer, Supplier endpoints
   - Use schema for dynamic field handling

3. **Templates:**
   - Update forms to use `schema_form.html` template
   - Pass entity_key and fields from routes

## Key Benefits

✅ **Single Source of Truth**: MDM schema is the definition for all forms
✅ **Immediate Propagation**: Changes in MDM instantly affect all modules
✅ **No Hardcoding**: Eliminates need to update multiple files when schema changes
✅ **Centralized Maintenance**: All schema definitions in one place
✅ **Consistent Behavior**: All modules use same field definitions
✅ **Easy Extension**: New modules automatically work with existing schemas

## File Locations

- Utilities: `mebelgrad_kis/app/schema_utils.py`
- Template: `mebelgrad_kis/templates/components/schema_form.html`
- MDM API: `mebelgrad_kis/app/data_mdm/routes.py` (new endpoints)
- Sales Integration: `mebelgrad_kis/app/sales_demo/routes.py` (updated endpoints)
- MDM UI: `mebelgrad_kis/templates/data_mdm/index.html` (updated hint)
