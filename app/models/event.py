from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field


# Модель персональных данных пациента
class PersonalData(BaseModel):
    id: str = Field(..., alias="Person_id", description="ID пациента в МИС")
    last_name: str = Field(..., alias="Person_Surname", description="Фамилия")
    first_name: str = Field(..., alias="Person_Firname", description="Имя")
    middle_name: str = Field(None, alias="Person_Secname", description="Отчество")
    birthday: str = Field(..., alias="Person_Birthdate", description="Дата рождения в формате DD.MM.YYYY")
    # todo: добавим поле с полом пациента, будем получать его позднее
    gender: Optional[str] = Field(None, alias="Person_Sex", description="Пол")
    death_date: Optional[str] = Field(None, alias="Person_deadDT", description="Дата смерти")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


# --- Модель для данных о конкретной госпитализации ---
class HospitalizationData(BaseModel):
    id: str = Field(..., alias="EvnPS_id", description="ID госпитализации в МИС")
    card_number: str = Field(..., alias="EvnPS_NumCard", description="Номер карты стационарного больного")
    start_date: str = Field(..., alias="EvnPS_setDate", description="Дата начала госпитализации")
    end_date: Optional[str] = Field(None, alias="EvnPS_disDate", description="Дата окончания госпитализации (выписки)")
    is_transit: Optional[str] = Field(None, alias="EvnPS_IsTransit", description="Признак транзитной госпитализации")
    department_name: Optional[str] = Field(None, alias="LpuSection_Name", description="Отделение")
    profile_name: Optional[str] = Field(None, alias="LpuSectionProfile_Name", description="Профиль отделения")
    diagnosis_name: Optional[str] = Field(None, alias="Diag_Name", description="Диагноз (из стартового запроса)")
    bed_days: Optional[str] = Field(None, alias="EvnPS_KoikoDni", description="Количество койко-дней")
    pay_type_name: Optional[str] = Field(None, alias="PayType_Name", description="Тип оплаты (ОМС, ДМС и т.д.)")
    discharge_type_name: Optional[str] = Field(None, alias="LeaveType_Name", description="Тип выписки")
    discharge_type_code: Optional[str] = Field(None, alias="LeaveType_Code", description="Код типа выписки")
    ksg: Optional[str] = Field(None, alias="EvnSection_KSG", description="КСГ")
    ksg_kpg: Optional[str] = Field(None, alias="EvnSection_KSGKPG", description="КСГ/КПГ")
    operation_count: Optional[str] = Field(None, alias="EvnUslugaOperCount", description="Количество операций")
    # --- Поля для данных, которые будем собирать ДОПОЛНИТЕЛЬНО ---
    operations: List[Dict[str, Any]] = Field(default_factory=list, description="Список операций (услуг)")
    diagnoses: List[Dict[str, Any]] = Field(default_factory=list, description="Список диагнозов")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }

# --- Модель для сервисных данных (ids и прочее) ---
class ServiceData(BaseModel):
    event_id: str = Field(..., alias="EvnPS_id", description="ID госпитализации в МИС")
    person_id: str = Field(..., alias="Person_id", description="ID пациента в МИС")
    person_event_id: str = Field(..., alias="PersonEvn_id", description="ID связи пациента с госпитализацией в МИС")
    server_id: str = Field(..., alias="Server_id", description="ID сервера")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }
