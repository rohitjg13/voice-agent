import { redirect } from '@sveltejs/kit';
import { apiJson } from '$lib/server/api';
import type { LayoutServerLoad } from './$types';

export type Me = {
	user: { id: string; email: string };
	org: { id: string; name: string; role: string } | null;
	subscription: {
		plan_id: string;
		plan_name: string;
		status: string;
		limits: Record<string, number>;
	} | null;
};

export const load: LayoutServerLoad = async (event) => {
	if (!event.locals.session) redirect(303, '/login');
	const me = await apiJson<Me>(event, '/api/v1/me');
	if (!me.org) redirect(303, '/onboarding');
	return { me };
};
