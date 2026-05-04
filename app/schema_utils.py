"""
Utility functions for dynamic form generation based on DataModel schema.
This module is the central point for accessing and rendering data model schemas.
"""

import re
from datetime import datetime

from app.models import DataModel, DataModelField, db


def get_schema_fields(entity_key):
    """
    Retrieve all fields for a given entity schema, ordered by display order.
    
    Args:
        entity_key (str): The key of the data model (e.g., 'customers', 'products')
        
    Returns:
        list: List of DataModelField objects, or empty list if model not found
    """
    model = DataModel.query.filter_by(key=entity_key).first()
    if not model:
        return []
    return model.fields.order_by(DataModelField.order.asc(), DataModelField.label.asc()).all()


def get_schema_model(entity_key):
    """
    Retrieve the DataModel object for a given entity key.
    
    Args:
        entity_key (str): The key of the data model
        
    Returns:
        DataModel or None
    """
    return DataModel.query.filter_by(key=entity_key).first()


def get_visible_fields(entity_key):
    """
    Retrieve only visible fields for an entity (used for form display).
    
    Args:
        entity_key (str): The key of the data model
        
    Returns:
        list: List of visible DataModelField objects
    """
    return [f for f in get_schema_fields(entity_key) if f.is_visible]


def get_required_fields(entity_key):
    """
    Retrieve required fields for an entity (used for validation).
    
    Args:
        entity_key (str): The key of the data model
        
    Returns:
        list: List of required DataModelField objects
    """
    return [f for f in get_schema_fields(entity_key) if f.is_required]


def get_field_by_name(entity_key, field_name):
    """
    Get a specific field from an entity schema.
    
    Args:
        entity_key (str): The key of the data model
        field_name (str): The technical name of the field
        
    Returns:
        DataModelField or None
    """
    model = get_schema_model(entity_key)
    if not model:
        return None
    return DataModelField.query.filter_by(model_id=model.id, name=field_name).first()


def get_form_fields_as_dict(entity_key):
    """
    Convert schema fields to a dictionary for template rendering.
    Used for dynamic form generation in templates.
    
    Args:
        entity_key (str): The key of the data model
        
    Returns:
        dict: Dictionary with field names as keys and field properties as values
    """
    fields = get_visible_fields(entity_key)
    result = {}
    for field in fields:
        result[field.name] = {
            'label': field.label,
            'type': field.data_type,
            'required': field.is_required,
            'max_length': field.max_length,
            'help_text': field.help_text,
            'order': field.order,
        }
    return result


def validate_field_value(entity_key, field_name, value):
    """
    Validate a field value against its schema definition.
    
    Args:
        entity_key (str): The key of the data model
        field_name (str): The technical name of the field
        value: The value to validate
        
    Returns:
        tuple: (is_valid: bool, error_message: str or None)
    """
    field = get_field_by_name(entity_key, field_name)
    if not field:
        return False, f"Field '{field_name}' not found in schema"
    
    if field.is_required and (value is None or str(value).strip() == ''):
        return False, f"Field '{field.label}' is required"
    
    if value and field.max_length and len(str(value)) > field.max_length:
        return False, f"Field '{field.label}' exceeds maximum length of {field.max_length}"
    
    # Type validation
    if value and field.data_type == 'integer':
        try:
            int(value)
        except (ValueError, TypeError):
            return False, f"Field '{field.label}' must be an integer"

    elif value and field.data_type == 'float':
        try:
            float(value)
        except (ValueError, TypeError):
            return False, f"Field '{field.label}' must be a number"

    if value and field.validation_regex:
        try:
            pattern = re.compile(field.validation_regex)
        except re.error:
            return False, f"Неверное регулярное выражение для поля '{field.label}'"
        if not pattern.fullmatch(str(value)):
            return False, f"Поле '{field.label}' не соответствует требуемому формату"

    return True, None


def parse_field_value(raw_value, data_type):
    """
    Convert a raw field value from form input into the typed Python value.
    """
    if raw_value is None:
        return None

    if data_type == 'boolean':
        if isinstance(raw_value, str):
            normalized = raw_value.strip().lower()
            return normalized in ('true', 'on', '1', 'yes')
        return bool(raw_value)

    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        if raw_value == '':
            return None

    if data_type == 'integer':
        try:
            return int(raw_value)
        except (ValueError, TypeError):
            return raw_value

    if data_type == 'float':
        try:
            return float(raw_value)
        except (ValueError, TypeError):
            return raw_value

    if data_type == 'date':
        if isinstance(raw_value, datetime):
            return raw_value
        try:
            return datetime.strptime(raw_value, '%Y-%m-%d')
        except (ValueError, TypeError):
            return raw_value

    return raw_value


def extract_fields_from_form(entity_key, form_data):
    """
    Extract only schema-defined fields from form data.
    Useful for filtering incoming requests to include only fields defined in MDM.
    
    Args:
        entity_key (str): The key of the data model
        form_data (dict): The form data to filter
        
    Returns:
        dict: Dictionary with only schema-defined fields
    """
    fields = get_schema_fields(entity_key)
    result = {}
    for field in fields:
        if field.name in form_data:
            result[field.name] = form_data[field.name]
    return result


def extract_typed_fields_from_form(entity_key, form_data):
    """
    Extract schema-defined fields from form data and convert them to typed values.
    """
    fields = get_schema_fields(entity_key)
    result = {}
    for field in fields:
        if field.name in form_data:
            result[field.name] = parse_field_value(form_data.get(field.name), field.data_type)
        elif field.data_type == 'boolean':
            # Unchecked HTML checkbox fields are omitted from request.form,
            # but their semantic value should still be treated as False.
            result[field.name] = False
    return result


def get_field_html_input_type(data_type):
    """
    Convert schema field type or data type to HTML input type.

    Args:
        data_type (str): The field_type or data_type from schema

    Returns:
        str: HTML input type or widget name
    """
    type_mapping = {
        'string': 'text',
        'text': 'textarea',
        'integer': 'number',
        'float': 'number',
        'date': 'date',
        'boolean': 'checkbox',
        'email': 'email',
        'url': 'url',
        'select': 'select',
        'radio': 'radio',
        'autocomplete': 'text',
        'textarea': 'textarea',
    }
    return type_mapping.get(data_type, 'text')
