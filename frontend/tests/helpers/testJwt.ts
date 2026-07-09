// TEST-ONLY HELPER — never import this from src/
// Generates unsigned JWTs for Playwright tests. The signature is not validated
// in the test environment (mocked auth). Do NOT use in production code.
export function makeTestJwt(role: 'operator' | 'owner', ttlSeconds = 3600): string {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(
    JSON.stringify({
      sub: 'test-user-id',
      role,
      exp: Math.floor(Date.now() / 1000) + ttlSeconds,
      iat: Math.floor(Date.now() / 1000),
    }),
  )
  return `${header}.${payload}.test-signature`
}
