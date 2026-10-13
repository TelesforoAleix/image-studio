export async function api(path, method = "GET", body) {
  const multipart = body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    method,
    headers:
      body && !multipart ? { "Content-Type": "application/json" } : undefined,
    body: body ? (multipart ? body : JSON.stringify(body)) : undefined,
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The request failed");
  return result;
}
