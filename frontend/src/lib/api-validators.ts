/**
 * Lightweight runtime type checker for API responses.
 * Validates required fields exist and logs warnings for unexpected shapes.
 */
export function validateApiResponse<T>(
  data: unknown,
  requiredFields: string[],
  context: string,
): T {
  if (typeof data !== "object" || data === null) {
    console.warn(`[API] Invalid response shape for ${context}:`, data);
    return data as T;
  }
  for (const field of requiredFields) {
    if (!(field in data)) {
      console.warn(`[API] Missing field "${field}" in ${context} response`);
    }
  }
  return data as T;
}
