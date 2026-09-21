/** All authenticated requests use one explicitly configured service origin. */
export function serviceUrl(path: string): string {
  if (
    !path.startsWith('/api/v1/') ||
    new URL(path, window.location.origin).origin !== window.location.origin
  )
    throw new Error('Invalid service URL.');
  const origin = import.meta.env.VITE_API_ORIGIN?.trim() || '';
  if (origin) {
    const configured = new URL(origin);
    if (configured.protocol !== 'https:' || configured.origin !== origin)
      throw new Error('Invalid API origin configuration.');
  }
  return `${origin}${path}`;
}
