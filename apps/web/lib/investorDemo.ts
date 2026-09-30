/**
 * Server-only gate for the isolated investor-demo deployment.
 *
 * Keep the check strict: public deployments must stay closed for missing,
 * misspelled, or loosely truthy values. Access control belongs to the private
 * gateway in front of the isolated deployment, never to a URL token.
 */
export function isInvestorDemoEnabled(
  value: string | undefined = process.env.BOOKER_ENABLE_INVESTOR_DEMO,
): boolean {
  return value === "1";
}
