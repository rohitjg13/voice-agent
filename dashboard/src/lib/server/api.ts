import { env } from '$env/dynamic/private';
import { error, type RequestEvent } from '@sveltejs/kit';

/** Server-side fetch to the FastAPI backend, forwarding the Supabase JWT. */
export async function api(
	event: RequestEvent,
	path: string,
	init: RequestInit = {}
): Promise<Response> {
	const token = event.locals.session?.access_token;
	const headers = new Headers(init.headers);
	if (token) headers.set('Authorization', `Bearer ${token}`);
	return fetch(`${env.PRIVATE_API_URL ?? 'http://localhost:8000'}${path}`, {
		...init,
		headers
	});
}

/** GET that throws a SvelteKit error on failure and returns parsed JSON. */
export async function apiJson<T>(event: RequestEvent, path: string): Promise<T> {
	const res = await api(event, path);
	if (!res.ok) throw error(res.status, await safeDetail(res));
	return (await res.json()) as T;
}

export async function safeDetail(res: Response): Promise<string> {
	try {
		const body = await res.json();
		return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
	} catch {
		return res.statusText;
	}
}
