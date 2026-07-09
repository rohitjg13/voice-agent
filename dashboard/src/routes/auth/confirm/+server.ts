import { redirect } from '@sveltejs/kit';
import type { EmailOtpType } from '@supabase/supabase-js';
import type { RequestHandler } from './$types';

/** Email-confirmation landing: exchanges the token_hash for a session. */
export const GET: RequestHandler = async ({ url, locals }) => {
	const token_hash = url.searchParams.get('token_hash');
	const type = url.searchParams.get('type') as EmailOtpType | null;

	if (token_hash && type) {
		const { error } = await locals.supabase.auth.verifyOtp({ token_hash, type });
		if (!error) redirect(303, '/onboarding');
	}
	redirect(303, '/login');
};
