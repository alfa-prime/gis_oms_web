# маппер для обработки справочников НСИ ФОМС

nsi_handbooks_mapper = {
    "F002": {  # страховые компании
        "root_key": "insCompany",
        "filename": "insurance_companies.json",
        "handbook_storage_key": "insurance_companies",
        "key_field": "nam_smop",
    },
    "F032": {
        "root_key": "zap",
        "filename": "medical_organizations.json",
        "handbook_storage_key": "medical_organizations",
        "key_field": "OID_MO",
    },
    "V002": { # профиль медицинской помощи
        "root_key": "zap",
        "filename": "medical_care_profiles.json",
        "handbook_storage_key": "medical_care_profiles",
        "key_field": "PRNAME",
    },
    "V005": {  # Классификатор пола застрахованного
        "root_key": "zap",
        "filename": "gender.json",
        "handbook_storage_key": "gender",
        "key_field": "POLNAME",
    },
    "V006": {  # условия оказания медицинской помощи
        "root_key": "zap",
        "filename": "medical_care_conditions.json",
        "handbook_storage_key": "medical_care_conditions",
        "key_field": "UMPNAME",
    },
    "V014": { # формы оказания медицинской помощи
        "root_key": "zap",
        "filename": "medical_care_forms.json",
        "handbook_storage_key": "medical_care_forms",
        "key_field": "IDFRMMP",
    },
}
