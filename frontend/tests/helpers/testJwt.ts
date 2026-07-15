// TEST-ONLY HELPER — never import this from src/
// Generates unsigned JWTs for Playwright tests. The signature is not validated
// in the test environment (mocked auth). Do NOT use in production code.
//
// Roles after PR #110 (backend roles v3): 'cocinero' | 'owner' | 'admin'
// 'operator' is kept as an alias for 'cocinero' so pre-existing tests that
// haven't been updated yet continue to compile without changes.
export type TestRole = 'cocinero' | 'owner' | 'admin' | 'operator'

export function makeTestJwt(
  role: TestRole,
  ttlSeconds = 3600,
  sub = 'test-user-id',
): string {
  // Normalize legacy 'operator' alias to the current backend value 'cocinero'
  const normalizedRole = role === 'operator' ? 'cocinero' : role
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(
    JSON.stringify({
      sub,
      role: normalizedRole,
      exp: Math.floor(Date.now() / 1000) + ttlSeconds,
      iat: Math.floor(Date.now() / 1000),
    }),
  )
  return `${header}.${payload}.test-signature`
}
