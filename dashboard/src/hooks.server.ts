import { createServerClient, type CookieOptions } from '@supabase/ssr';
import { env } from '$env/dynamic/public';
import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
	event.locals.supabase = createServerClient(
		env.PUBLIC_SUPABASE_URL ?? '',
		env.PUBLIC_SUPABASE_ANON_KEY ?? '',
		{
			cookies: {
				getAll: () => event.cookies.getAll(),
				setAll: (
					cookies: { name: string; value: string; options: CookieOptions }[]
				) => {
					cookies.forEach(({ name, value, options }) => {
						event.cookies.set(name, value, { ...options, path: '/' });
					});
				}
			}
		}
	);

	// getUser() validates the JWT against the auth server; never trust the
	// cookie session alone.
	event.locals.safeGetSession = async () => {
		const {
			data: { user }
		} = await event.locals.supabase.auth.getUser();
		if (!user) return { session: null, user: null };
		const {
			data: { session }
		} = await event.locals.supabase.auth.getSession();
		return { session, user };
	};

	const { session, user } = await event.locals.safeGetSession();
	event.locals.session = session;
	event.locals.user = user;

	return resolve(event, {
		filterSerializedResponseHeaders: (name) => name === 'content-range' || name === 'x-supabase-api-version'
	});
};
