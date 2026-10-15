const BASE = "/v1";

/** @param {string} path @param {RequestInit} [options] @param {number} [timeoutMs] */
async function request(path, options = {}, timeoutMs = 240000) {
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...options,
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    if (error instanceof Error && error.name === "TimeoutError")
      throw new Error(
        "The request timed out. The server may still be processing it; check history before retrying.",
      );
    throw new Error("Cannot reach the API. Check that the backend is running.");
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((/** @type {{msg: string}} */ item) => item.msg)
              .join("; ")
          : `Request failed (HTTP ${response.status})`,
    );
  }
  return data;
}

/** @param {string} question @param {import("../types").Mode} [mode] @param {string | null} [clarificationChoice] @returns {Promise<import("../types").QueryResult>} */
export function queryNL(
  question,
  mode = "natural_language",
  clarificationChoice = null,
) {
  return request("/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      mode,
      clarification_choice: clarificationChoice,
    }),
  });
}
/** @returns {Promise<import("../types").Schema>} */
export const getSchema = () => request("/schema", {}, 15000);
/** @param {number} [limit] @returns {Promise<import("../types").HistoryItem[]>} */
export const getHistory = (limit = 20) =>
  request(`/history?limit=${limit}`, {}, 15000);
/** @returns {Promise<import("../types").AppConfig>} */
export const getConfig = () => request("/config", {}, 15000);
export const getReady = () => request("/ready", {}, 15000);
/** @param {string} queryId @param {boolean} isCorrect @param {string | null} [comment] */
export function sendFeedback(queryId, isCorrect, comment = null) {
  return request(
    "/feedback",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query_id: queryId,
        is_correct: isCorrect,
        comment,
      }),
    },
    15000,
  );
}
/** @returns {Promise<import("../types").EvalResult>} */
export const runEval = () => request("/eval", { method: "POST" }, 900000);
