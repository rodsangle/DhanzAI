export class HttpError extends Error {
  /** `data` is merged into the JSON error body (e.g. the latest version on a 409 save conflict). */
  constructor(public status: number, message: string, public data?: Record<string, unknown>) {
    super(message);
  }
}
