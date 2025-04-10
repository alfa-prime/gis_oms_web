// static/js/main.js

import 'alpinejs';
import { prepareSearchPayload, performSearchRequest } from './apiService.js';


// Функция валидации данных формы
function validateSearchForm(formData) {
    if (!formData.last_name.trim()) {
        return 'Фамилия обязательна для заполнения.';
    }
    if (formData.birthday && !/^\d{2}\.\d{2}\.\d{4}$/.test(formData.birthday)) {
        return 'Неверный формат даты рождения (ДД.ММ.ГГГГ).';
    }
    return null; // Ошибок нет
}


document.addEventListener('alpine:init', () => {
    // Alpine уже должен быть доступен глобально из CDN
    if (typeof Alpine === 'undefined') {
         console.error("Alpine не загружен (проверь CDN)!");
         return;
    }
    // Регистрируем компонент для Alpine
    // Имя 'patientSearch' должно совпадать с тем, что в x-data="patientSearch()" в HTML
    Alpine.data('patientSearch', () => ({

        // --- Состояние (переменные) компонента ---
        formData: { // Данные полей формы
            last_name: '',
            first_name: '',
            middle_name: '',
            birthday: ''
        },
        loading: false,    // Флаг: идет ли сейчас поиск?
        error: null,       // Строка с сообщением об ошибке
        results: [],     // Результаты поиска: null=еще не искали, []=не найдено, [...]=найдены госпитализации
        searchPerformed: false, // Флаг, что поиск еще не выполнялся
        showResultsModal: false, // Флаг: показывать ли модальное окно с результатами?
        formSubmitted: false,

         // --- Методы-обертки Alpine ---

         // Метод init вызывается при инициализации компонента Alpine
        init() {
            console.log('Patient Search component initialized');
            const dobInput = document.getElementById('dob-input');
            if (dobInput) {
                flatpickr(dobInput, {
                    // dateFormat: "d.m.Y", // Стандартный российский формат для отображения
                    locale: "ru",         // Включаем русскую локализацию (требует подключения скрипта локали)
                    allowInput: true,     // Разрешить ручной ввод даты
                    altInput: true,       // Показать удобный для пользователя формат (altFormat)
                    altFormat: "d.m.Y",   // Формат для пользователя (ДД.ММ.ГГГГ)
                    dateFormat: "d.m.Y",  // Формат, который будет в value инпута и в модели Alpine (ГГГГ-ММ-ДД)
                                          // Этот формат обычно удобнее для отправки в API
                    onChange: (selectedDates, dateStr, instance) => {
                        // Принудительно обновляем модель Alpine, используя dateStr в формате 'dateFormat' (Y-m-d)
                        this.formData.birthday = dateStr;
                        console.log("Flatpickr date selected:", this.formData.birthday);
                    },
                });
                console.log('Flatpickr initialized for #dob-input');
            } else {
                console.error('#dob-input element not found for Flatpickr');
            }
        },

        // Метод для обработки отправки формы
        async searchPatient() { // Делаем его async, т.к. он ждет performSearchRequest
            console.log("searchPatient called");
            this.formSubmitted = true;
            this.loading = true;
            this.error = null;
            this.results = null;
            this.showResultsModal = false;

            // 1. Валидация
            console.log('Setting formSubmitted to true');
            const validationError = validateSearchForm(this.formData);
            if (validationError) {
                this.error = validationError;
                this.loading = false;
                return;
            }

            // 2. Подготовка данных
            const payload = prepareSearchPayload(this.formData);
            console.log("Payload for API:", JSON.stringify(payload));

            // 3. Выполнение запроса (вызываем нашу отдельную async функцию)
            const response = await performSearchRequest(payload);

            // 4. Обработка результата
            if (response.success) {
                this.results = response.data; // Сохраняем данные (могут быть [])
                if (this.results.length > 0) {
                    this.showResultsModal = true; // Показываем модалку если есть результаты
                    this.error = null;
                } else {
                    // Результатов нет (был 404 или пустой ответ)
                    this.error = "В ЕВМИАС не найдено записей с указанными параметрами."; // Устанавливаем сообщение
                    this.showResultsModal = false;
                }
            } else {
                // Произошла ошибка при запросе
                this.error = response.error || 'Произошла неизвестная ошибка.';
                this.results = []; // Сбрасываем результаты при ошибке
                this.showResultsModal = false;
            }

            // 5. Завершение загрузки
            this.loading = false;
            console.log("Search finished");
        },

        selectEvent(eventId) {
            console.log('Выбрана госпитализация с ID:', eventId);
            this.showResultsModal = false;
            alert(`Выбрана госпитализация с ID: ${eventId}. Следующий шаг: загрузка деталей.`);
            // TODO: Реализовать загрузку деталей
        }
    }));
});

