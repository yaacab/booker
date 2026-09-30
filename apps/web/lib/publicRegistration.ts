/**
 * Server-side public registration gate.
 *
 * Only the documented exact opt-in opens registration. Missing, misspelled,
 * or loosely truthy values keep the public flow closed.
 */
export function isPublicRegistrationEnabled(
  value: string | undefined = process.env.BOOKER_PUBLIC_REGISTRATION_ENABLED,
): boolean {
  return value === "1";
}
