/** A failed API request, with the status and the message the API sent. */
export class ApiRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

/** Read the message of an error response: FastAPI's `detail`, or the status text. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };

    if (typeof body.detail === "string") {
      return body.detail;
    }

    return JSON.stringify(body.detail ?? body);
  } catch {
    return `The request failed with status ${response.status}.`;
  }
}

/** Throw an `ApiRequestError` when a response is not successful. */
export async function checkResponse(response: Response): Promise<Response> {
  if (!response.ok) {
    throw new ApiRequestError(response.status, await errorMessage(response));
  }

  return response;
}

/** Send a request with an optional JSON body and decode the JSON response. */
export async function requestJson<Result>(
  path: string,
  {
    method = "GET",
    body,
    signal,
  }: { method?: string; body?: unknown; signal?: AbortSignal } = {},
): Promise<Result> {
  const request = new Request(new URL(path, window.location.origin), {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? null : JSON.stringify(body),
  });
  // The signal goes with the call rather than the request, which test environments
  // with their own `AbortSignal` would reject.
  const response = await checkResponse(await globalThis.fetch(request, { signal }));

  return (await response.json()) as Result;
}
