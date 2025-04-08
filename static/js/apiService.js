// static/js/apiService.js

/**
 * Подготавливает данные для отправки в API поиска.
 * @param {object} formData - Объект с данными формы (last_name, first_name и т.д.).
 * @returns {object} - Объект с данными для JSON payload.
 */
export function prepareSearchPayload(formData) {
    const payload = { last_name: formData.last_name.trim() };
    if (formData.first_name?.trim()) { // Используем optional chaining ?. для краткости
        payload.first_name = formData.first_name.trim();
    }
    if (formData.middle_name?.trim()) {
        payload.middle_name = formData.middle_name.trim();
    }
    if (formData.birthday?.trim()) {
        payload.birthday = formData.birthday.trim();
    }
    return payload;
}

/**
 * Выполняет основной запрос поиска госпитализаций к API.
 * @param {object} payload - Подготовленные данные для поиска.
 * @returns {Promise<object>} - Promise, который разрешается объектом:
 *      { success: true, data: [...] } при успехе (data может быть пустым),
 *      { success: false, error: "сообщение" } при ошибке.
 */
export async function performSearchRequest(payload) {
    console.log("Sending payload:", payload); // Отладка внутри сервиса
    const apiUrl = '/api/evmias-oms/get_patient'; // Вынесем URL в константу

    try {
        const response = await fetch(apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        console.log("API Response Status:", response.status); // Отладка внутри сервиса

        if (response.ok) { // 2xx
            return { success: true, data: await response.json() };
        } else if (response.status === 404) { // 404
            return { success: true, data: [] }; // Считаем успехом, но данных нет
        } else { // Другие ошибки
            let errorDetail = `Ошибка сервера: ${response.status} ${response.statusText}`;
            try {
                const errData = await response.json();
                errorDetail = errData.detail || errorDetail;
            } catch (e) { /* ignore */ }
            return { success: false, error: errorDetail };
        }
    } catch (networkError) {
        console.error('Fetch network error:', networkError);
        return { success: false, error: 'Ошибка сети при выполнении запроса.' };
    }
}

// Можно сюда же добавить в будущем функцию для получения деталей госпитализации
// export async function getHospitalizationDetails(eventId) { ... }