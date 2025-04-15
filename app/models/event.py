from typing import Optional, List, Dict, Any

from pydantic import BaseModel, Field, model_validator


# --- Вспомогательные модели для группировки ---

class PersonalData(BaseModel):
    """Личные данные пациента."""
    id: str = Field(..., alias="Person_id", description="ID пациента в МИС")
    last_name: str = Field(..., alias="Person_Surname", description="Фамилия")
    first_name: str = Field(..., alias="Person_Firname", description="Имя")
    middle_name: Optional[str] = Field(None, alias="Person_Secname", description="Отчество")
    birthday: Optional[str] = Field(None, alias="Person_Birthday", description="Дата рождения в формате DD.MM.YYYY")
    gender_name: Optional[str] = Field(None, alias="Sex_Name", description="Пол (loadPersonDatat)")
    death_date: Optional[str] = Field(None, alias="Person_deadDT", description="Дата смерти")
    death_time: Optional[str] = Field(None, alias="Person_deadTime", description="Время смерти")
    address_registration: Optional[str] = Field(None, alias="Person_RAddress", description="Адрес регистрации")
    address_actual: Optional[str] = Field(None, alias="Person_PAddress", description="Адрес фактический")
    phone_number: Optional[str] = Field(None, alias="Person_Phone", description="Номер телефона")
    snils: Optional[str] = Field(None, alias="Person_Snils", description="СНИЛС")
    job_name: Optional[str] = Field(None, alias="Person_Job", description="Работа")
    social_status_name: Optional[str] = Field(None, alias="SocStatus_Name", description="Социальный статус")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class HospitalizationData(BaseModel):
    """Основные данные госпитализации"""
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

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


class ServiceData(BaseModel):
    """Сервисные идентификаторы."""
    event_id: str = Field(..., alias="EvnPS_id", description="ID госпитализации в МИС")
    person_id: str = Field(..., alias="Person_id", description="ID пациента в МИС")
    person_event_id: str = Field(..., alias="PersonEvn_id", description="ID связи пациента с госпитализацией в МИС")
    server_id: str = Field(..., alias="Server_id", description="ID сервера")
    server_pid: Optional[str] = Field(None, alias="Server_pid", description="pid сервера (из loadPersonData)")
    sex_id: Optional[str] = Field(None, alias="Sex_id", description="ID пола (из loadPersonData [1-м; 2-ж; 3-неопр.])")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore"
    }


# --- Основная модель Event ---
class Event(BaseModel):
    """
    Объединенная модель для хранения всех данных, связанных с одной госпитализацией пациента,
    сгруппированных по логическим блокам.
    """
    personal: PersonalData = Field(description="Личные данные пациента")
    hospitalization: HospitalizationData = Field(description="Основные данные госпитализации")
    service: ServiceData = Field(description="Сервисные данные")

    # --- Поля для данных, которые будем собирать ДОПОЛНИТЕЛЬНО ---
    operations: List[Dict[str, Any]] = Field(default_factory=list, description="Список операций (услуг)")
    diagnoses: List[Dict[str, Any]] = Field(default_factory=list, description="Список диагнозов")

    @model_validator(mode='before') # noqa
    @classmethod
    def group_flat_data(cls, data: Any) -> Dict[str, Any]:
        """
        Преобразует плоский словарь данных (из JSON ответа ЕВМИАС)
        во вложенную структуру, ожидаемую моделью Event, перед стандартной валидацией.
        """
        if not isinstance(data, dict):
            raise ValueError("Input data for Event must be a dictionary")

        # Создаем словарь, где ключи - имена полей Event (personal, hospitalization, service),
        # а значения - это исходный словарь data. Pydantic сам разберется
        # с алиасами внутри вложенных моделей PersonalData, HospitalizationCoreData, ServiceData.
        grouped_data = {
            "personal": data.copy(),  # Копируем, чтобы избежать мутаций, если data используется где-то еще
            "hospitalization": data.copy(),
            "service": data.copy(),
            # Переносим поля для доп. данных, если они вдруг уже есть во входных данных
            "operations": data.get("operations", []),
            "diagnoses": data.get("diagnoses", [])
        }
        return grouped_data
