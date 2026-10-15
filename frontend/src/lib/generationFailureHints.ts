const FAILURE_HINTS: Record<string, string> = {
  llm_schema_rejected:
    'The AI provider rejected the response format (often fixed in a server update). Restart the API and try again.',
  llm_validation: 'The AI response did not match the expected structure. Try again.',
  llm_rate_limit: 'Rate limit reached. Wait a minute and try again.',
  llm_error: 'The AI provider returned an error. Try again shortly.',
  generation_timeout: 'Generation took too long. Try again or use fewer features / shorter scope.',
  unexpected_error: 'An unexpected server error occurred. Check API logs and try again.',
}

export function generationFailureHint(code: string | null | undefined): string | null {
  if (!code) return null
  return FAILURE_HINTS[code] ?? null
}
