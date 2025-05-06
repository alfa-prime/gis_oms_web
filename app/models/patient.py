from typing import Optional

from pydantic import BaseModel, Field, constr


class PatientSearch(BaseModel):
    last_name: str = Field(
        ...,
        description = "Фамилия пациента",
        examples = ["Бобов"],
    )
    first_name: Optional[str] = Field(
        None,
        description = "Имя пациента",
        examples = ["Игорь"],
    )
    middle_name: Optional[str] = Field(
        None,
        description = "Отчество пациента",
        examples = ["Константинович"],
    )
    birthday: Optional[constr(pattern=r"\d{2}\.\d{2}\.\d{4}")] = Field(
        None,
        description="Дата рождения в формате DD.MM.YYYY",
        examples=["04.02.1961"]

    )


class EventSearch(BaseModel):
    card_number: str = Field(
        ...,
        description = "Номер карты пациента",
        examples = ["2941"],
    )
    last_name: str = Field(
        ...,
        description="Фамилия пациента",
        examples=["Петрова"],
    )
    first_name: Optional[str] = Field(
        None,
        description="Имя пациента",
        examples=["Анна"],
    )
    middle_name: Optional[str] = Field(
        None,
        description="Отчество пациента",
        examples=["Юрьевна"],
    )
    birthday: Optional[constr(pattern=r"\d{2}\.\d{2}\.\d{4}")] = Field(
        None,
        description="Дата рождения в формате DD.MM.YYYY",
        examples=["17.03.1986"]

    )
