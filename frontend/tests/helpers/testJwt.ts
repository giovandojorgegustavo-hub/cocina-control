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
