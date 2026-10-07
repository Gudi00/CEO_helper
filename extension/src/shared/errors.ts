/**
 * User-facing texts for backend error codes: what happened and what to do.
 * The raw code stays visible in small print so it can be quoted in a report.
 */

import { ApiError } from "./api-client.js";

const MESSAGES: Record<string, string> = {
  OFFLINE: "Сервер не отвечает. Запустите его командой «lms-tool run» и попробуйте снова.",
  INVALID_TOKEN: "Расширение не связано с сервером. Введите код сопряжения из окна сервера.",
  ORIGIN_NOT_PAIRED:
    "Сервер связан с другим расширением. Введите новый код сопряжения («lms-tool pair»).",
  PAIRING_FAILED: "Код не подошёл или устарел. Получите новый командой «lms-tool pair».",
  AI_NOT_CONFIGURED:
    "На сервере не настроена ни одна нейросеть. Проверьте настройки командой «lms-tool doctor» или переключитесь на ручной режим.",
  AI_PROVIDER_FAILED:
    "Нейросеть недоступна или исчерпан лимит запросов. Повторите позже или ответьте вручную.",
  AI_INVALID_RESPONSE: "Нейросеть вернула неразборчивый ответ. Повторите или ответьте вручную.",
  NOT_FOUND: "Сервер не знает эту сессию. Нажмите «Начать» ещё раз.",
  HTTP_422: "Вопрос слишком длинный или необычного формата. Ответьте на него вручную.",
  VERSION_MISMATCH: "Версии расширения и сервера не совпадают. Обновите обе части.",
};

export function errorCode(err: unknown): string {
  if (err instanceof ApiError) return err.status === 0 ? "OFFLINE" : err.code;
  // fetch() rejects with TypeError when nothing listens on the port.
  if (err instanceof TypeError) return "OFFLINE";
  return "UNKNOWN";
}

export function describeError(err: unknown): string {
  const code = errorCode(err);
  const text = MESSAGES[code] ?? "Что-то пошло не так. Повторите попытку.";
  return `${text} (${code})`;
}
