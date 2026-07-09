import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ locals }) => {
	if (locals.session) redirect(303, '/dashboard');
};

export const actions: Actions = {
	default: async ({ request, locals, url }) => {
		const form = await request.formData();
		const email = String(form.get('email') ?? '').trim();
		const password = String(form.get('password') ?? '');
		const fullName = String(form.get('full_name') ?? '').trim();
		if (!email || password.length < 8) {
			return fail(400, { error: 'Valid email and a password of 8+ characters required', email });
		}

		const { data, error } = await locals.supabase.auth.signUp({
			email,
			password,
			options: {
				data: { full_name: fullName },
				emailRedirectTo: `${url.origin}/auth/confirm`
			}
		});
		if (error) return fail(400, { error: error.message, email });

		// Autoconfirm on: session exists → straight to onboarding.
		// Otherwise the user confirms via the emailed link.
		if (data.session) redirect(303, '/onboarding');
		return { confirm: true, email };
	}
};
