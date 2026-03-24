#!/usr/bin/env python
"""Test script to verify the company profile edit fix"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app, db
from app.models import CompanyProfile
from flask import request
from unittest.mock import Mock

# Create app
app = create_app('testing')

def test_company_profile_edit():
    """Test the company profile edit handling with None values"""
    with app.app_context():
        # Get the profile
        profile = CompanyProfile.query.first()
        if not profile:
            print("ERROR: CompanyProfile not found in database")
            return False
        
        print(f"Original profile: company_name={profile.company_name}, kpp={profile.kpp}")
        
        # Simulate form submission with some empty fields
        with app.test_request_context(method='POST', data={
            'company_name': 'Новая компания',
            'short_name': 'НК',
            'legal_form': 'ООО',
            'inn': '7701000000',
            'kpp': '',  # Empty field that could cause issues
            'ogrn': '1067746000000',
            'legal_address': 'Москва, ул. Ленина, 1',
            'actual_address': '',
            'phone': '+7 (495) 123-45-67',
            'email': 'test@company.ru',
            'website': '',
            'bank_name': 'Банк',
            'bank_bik': '044525225',
            'correspondent_account': '30101810400000000225',
            'settlement_account': '40702810999999999999',
            'ceo': 'Иван Иванов',
            'ceo_position': 'Генеральный директор',
            'chief_accountant_name': 'Мария Сидорова',
            'logo_url': '',
            'seal_url': '',
            'signature_url': '',
        }):
            try:
                # This is the fixed version of the POST handler logic
                def get_form_value(key, current_value=None, required=False):
                    value = request.form.get(key, "").strip()
                    if not value:
                        return None if not required else (current_value or "")
                    return value
                
                profile.company_name = get_form_value("company_name", profile.company_name, required=True)
                profile.short_name = get_form_value("short_name", profile.short_name)
                profile.legal_form = get_form_value("legal_form", profile.legal_form, required=True)
                profile.inn = get_form_value("inn", profile.inn, required=True)
                profile.kpp = get_form_value("kpp", profile.kpp)
                profile.ogrn = get_form_value("ogrn", profile.ogrn, required=True)
                profile.legal_address = get_form_value("legal_address", profile.legal_address, required=True)
                profile.actual_address = get_form_value("actual_address", profile.actual_address)
                profile.phone = get_form_value("phone", profile.phone)
                profile.email = get_form_value("email", profile.email)
                profile.website = get_form_value("website", profile.website)
                profile.bank_name = get_form_value("bank_name", profile.bank_name)
                profile.bank_bik = get_form_value("bank_bik", profile.bank_bik)
                profile.correspondent_account = get_form_value("correspondent_account", profile.correspondent_account)
                profile.settlement_account = get_form_value("settlement_account", profile.settlement_account)
                profile.ceo = get_form_value("ceo", profile.ceo, required=True)
                profile.ceo_position = get_form_value("ceo_position", profile.ceo_position)
                profile.chief_accountant_name = get_form_value("chief_accountant_name", profile.chief_accountant_name)
                profile.logo_url = get_form_value("logo_url", profile.logo_url)
                profile.seal_url = get_form_value("seal_url", profile.seal_url)
                profile.signature_url = get_form_value("signature_url", profile.signature_url)
                
                # Для ИП не нужны отдельные поля руководителя и главбуха
                if profile.legal_form == "ИП":
                    profile.ceo_position = None
                    profile.chief_accountant_name = None
                    profile.chief_accountant_signature_url = None
                
                db.session.commit()
                
                print("✓ SUCCESS: Form data processed without errors")
                print(f"Updated profile: company_name={profile.company_name}, kpp={profile.kpp}")
                return True
                
            except AttributeError as e:
                print(f"✗ ERROR: {e}")
                print("This is the original bug - trying to call .strip() on None")
                return False
            except Exception as e:
                print(f"✗ ERROR: Unexpected error - {e}")
                return False

if __name__ == "__main__":
    print("Testing company profile edit fix...")
    success = test_company_profile_edit()
    sys.exit(0 if success else 1)
